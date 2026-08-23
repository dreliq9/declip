const std = @import("std");
const c = @cImport({
    @cInclude("stdlib.h");
    @cInclude("libavformat/avformat.h");
});

const MK_OK: i32 = 0;
const MK_INVALID: i32 = 1;
const MK_NOT_FOUND: i32 = 2;
const MK_CONFLICT: i32 = 3;
const MK_BUFFER_TOO_SMALL: i32 = 4;
const MK_OVERFLOW: i32 = 5;

const Time = extern struct { num: i64, den: i64 };
const Asset = struct {
    id: [128]u8 = [_]u8{0} ** 128,
    id_len: usize = 0,
    duration: Time = .{ .num = 0, .den = 1 },
};
const Clip = struct {
    asset_index: usize = 0,
    source_in: Time = .{ .num = 0, .den = 1 },
    duration: Time = .{ .num = 0, .den = 1 },
    transition: Time = .{ .num = 0, .den = 1 },
};
const Proposal = struct {
    active: bool = false,
    id: u64 = 0,
    base_revision: u64 = 0,
    clip_index: usize = 0,
    new_duration: Time = .{ .num = 0, .den = 1 },
};
const Project = struct {
    revision: u64 = 0,
    next_proposal: u64 = 1,
    assets: [64]Asset = [_]Asset{.{}} ** 64,
    asset_count: usize = 0,
    clips: [256]Clip = [_]Clip{.{}} ** 256,
    clip_count: usize = 0,
    proposals: [64]Proposal = [_]Proposal{.{}} ** 64,
};

fn normalize128(n_in: i128, d_in: i128) ?Time {
    if (d_in == 0) return null;
    if (n_in == 0) return .{ .num = 0, .den = 1 };
    var n = n_in;
    var d = d_in;
    if (d < 0) { n = -n; d = -d; }
    var a: u128 = @intCast(if (n < 0) -n else n);
    var b: u128 = @intCast(d);
    while (b != 0) {
        const r = a % b;
        a = b;
        b = r;
    }
    const g: i128 = @intCast(a);
    n = @divTrunc(n, g);
    d = @divTrunc(d, g);
    if (n > std.math.maxInt(i64) or n < std.math.minInt(i64) or d > std.math.maxInt(i64)) return null;
    return .{ .num = @intCast(n), .den = @intCast(d) };
}
fn normalize(t: Time) ?Time { return normalize128(t.num, t.den); }
fn addTime(a_in: Time, b_in: Time) ?Time {
    const a = normalize(a_in) orelse return null;
    const b = normalize(b_in) orelse return null;
    return normalize128(@as(i128, a.num) * b.den + @as(i128, b.num) * a.den, @as(i128, a.den) * b.den);
}
fn compareTime(a_in: Time, b_in: Time) i32 {
    const a = normalize(a_in) orelse return 0;
    const b = normalize(b_in) orelse return 0;
    const l = @as(i128, a.num) * b.den;
    const r = @as(i128, b.num) * a.den;
    return if (l > r) 1 else if (l < r) -1 else 0;
}
fn positive(t: Time) bool { const n = normalize(t) orelse return false; return n.num > 0; }
fn cSlice(ptr: ?[*:0]const u8) ?[]const u8 { return if (ptr) |p| std.mem.span(p) else null; }
fn findAsset(p: *const Project, id: []const u8) ?usize {
    for (0..p.asset_count) |i| if (std.mem.eql(u8, p.assets[i].id[0..p.assets[i].id_len], id)) return i;
    return null;
}
fn validClip(p: *const Project, clip: Clip) bool {
    if (clip.asset_index >= p.asset_count or !positive(clip.duration)) return false;
    const end = addTime(clip.source_in, clip.duration) orelse return false;
    if (compareTime(clip.source_in, .{ .num = 0, .den = 1 }) < 0) return false;
    if (compareTime(end, p.assets[clip.asset_index].duration) > 0) return false;
    if (clip.transition.num != 0 and (!positive(clip.transition) or compareTime(clip.transition, clip.duration) >= 0)) return false;
    return true;
}
fn appendFmt(dst: []u8, pos: *usize, comptime fmt: []const u8, args: anytype) bool {
    const out = std.fmt.bufPrint(dst[pos.*..], fmt, args) catch return false;
    pos.* += out.len;
    return true;
}

export fn mk_time_normalize(input: Time, out: ?*Time) i32 {
    const ptr = out orelse return MK_INVALID;
    ptr.* = normalize(input) orelse return MK_INVALID;
    return MK_OK;
}
export fn mk_time_add(a: Time, b: Time, out: ?*Time) i32 {
    const ptr = out orelse return MK_INVALID;
    ptr.* = addTime(a, b) orelse return MK_OVERFLOW;
    return MK_OK;
}
export fn mk_time_compare(a: Time, b: Time) i32 { return compareTime(a, b); }

export fn mk_project_create() ?*Project {
    const raw = c.malloc(@sizeOf(Project)) orelse return null;
    const p: *Project = @ptrCast(@alignCast(raw));
    p.* = .{};
    return p;
}
export fn mk_project_destroy(p: ?*Project) void { if (p) |ptr| c.free(ptr); }
export fn mk_project_revision(p: ?*const Project) u64 { return if (p) |ptr| ptr.revision else 0; }

export fn mk_project_add_asset(p_opt: ?*Project, id_ptr: ?[*:0]const u8, duration_in: Time) i32 {
    const p = p_opt orelse return MK_INVALID;
    const id = cSlice(id_ptr) orelse return MK_INVALID;
    const duration = normalize(duration_in) orelse return MK_INVALID;
    if (id.len == 0 or id.len > 128 or !positive(duration) or p.asset_count >= p.assets.len) return MK_INVALID;
    if (findAsset(p, id) != null) return MK_CONFLICT;
    var asset = Asset{};
    @memcpy(asset.id[0..id.len], id);
    asset.id_len = id.len;
    asset.duration = duration;
    p.assets[p.asset_count] = asset;
    p.asset_count += 1;
    return MK_OK;
}

export fn mk_project_append_clip(p_opt: ?*Project, asset_ptr: ?[*:0]const u8, source_in_in: Time, duration_in: Time, transition_in: Time) i32 {
    const p = p_opt orelse return MK_INVALID;
    const asset = cSlice(asset_ptr) orelse return MK_INVALID;
    const asset_index = findAsset(p, asset) orelse return MK_INVALID;
    const source_in = normalize(source_in_in) orelse return MK_INVALID;
    const duration = normalize(duration_in) orelse return MK_INVALID;
    const transition = normalize(transition_in) orelse return MK_INVALID;
    if (p.clip_count >= p.clips.len) return MK_INVALID;
    const clip = Clip{ .asset_index = asset_index, .source_in = source_in, .duration = duration, .transition = transition };
    if (!validClip(p, clip) or (p.clip_count == 0 and transition.num != 0)) return MK_INVALID;
    p.clips[p.clip_count] = clip;
    p.clip_count += 1;
    return MK_OK;
}

export fn mk_project_propose_trim(p_opt: ?*Project, base_revision: u64, clip_index: usize, duration_in: Time, proposal_id: ?*u64) i32 {
    const p = p_opt orelse return MK_INVALID;
    const out = proposal_id orelse return MK_INVALID;
    if (base_revision != p.revision) return MK_CONFLICT;
    if (clip_index >= p.clip_count) return MK_INVALID;
    const duration = normalize(duration_in) orelse return MK_INVALID;
    if (!positive(duration)) return MK_INVALID;
    var candidate = p.clips[clip_index];
    candidate.duration = duration;
    if (!validClip(p, candidate)) return MK_INVALID;
    var slot: ?usize = null;
    for (0..p.proposals.len) |i| if (!p.proposals[i].active) { slot = i; break; };
    const i = slot orelse return MK_INVALID;
    const id = p.next_proposal;
    p.next_proposal += 1;
    p.proposals[i] = .{ .active = true, .id = id, .base_revision = base_revision, .clip_index = clip_index, .new_duration = duration };
    out.* = id;
    return MK_OK;
}

export fn mk_project_commit(p_opt: ?*Project, proposal_id: u64, new_revision: ?*u64) i32 {
    const p = p_opt orelse return MK_INVALID;
    const out = new_revision orelse return MK_INVALID;
    var found: ?Proposal = null;
    for (p.proposals) |proposal| if (proposal.active and proposal.id == proposal_id) { found = proposal; break; };
    const proposal = found orelse return MK_NOT_FOUND;
    if (proposal.base_revision != p.revision) return MK_CONFLICT;
    var candidate = p.clips[proposal.clip_index];
    candidate.duration = proposal.new_duration;
    if (!validClip(p, candidate)) return MK_INVALID;
    p.clips[proposal.clip_index] = candidate;
    p.revision += 1;
    for (&p.proposals) |*item| item.active = false;
    out.* = p.revision;
    return MK_OK;
}

export fn mk_project_lower_ffmpeg(p_opt: ?*const Project, buffer: ?[*]u8, capacity: usize, needed: ?*usize) i32 {
    const p = p_opt orelse return MK_INVALID;
    const needed_ptr = needed orelse return MK_INVALID;
    var text: [4096]u8 = undefined;
    var pos: usize = 0;
    if (!appendFmt(&text, &pos, "ffmpeg", .{})) return MK_OVERFLOW;
    for (0..p.clip_count) |i| {
        const asset = p.assets[p.clips[i].asset_index];
        if (!appendFmt(&text, &pos, " -i {s}", .{asset.id[0..asset.id_len]})) return MK_OVERFLOW;
    }
    if (!appendFmt(&text, &pos, " -filter_complex \"", .{})) return MK_OVERFLOW;
    for (0..p.clip_count) |i| {
        const clip = p.clips[i];
        if (i > 0 and !appendFmt(&text, &pos, ";", .{})) return MK_OVERFLOW;
        if (!appendFmt(&text, &pos, "[{d}:v]trim=start={d}/{d}:duration={d}/{d}[v{d}]", .{ i, clip.source_in.num, clip.source_in.den, clip.duration.num, clip.duration.den, i })) return MK_OVERFLOW;
    }
    for (1..p.clip_count) |i| {
        const clip = p.clips[i];
        if (clip.transition.num != 0 and !appendFmt(&text, &pos, ";[v{d}][v{d}]xfade=duration={d}/{d}[x{d}]", .{ i - 1, i, clip.transition.num, clip.transition.den, i })) return MK_OVERFLOW;
    }
    if (!appendFmt(&text, &pos, "\" out.mp4", .{})) return MK_OVERFLOW;
    needed_ptr.* = pos + 1;
    if (buffer == null or capacity < pos + 1) return MK_BUFFER_TOO_SMALL;
    const out = buffer.?;
    @memcpy(out[0..pos], text[0..pos]);
    out[pos] = 0;
    return MK_OK;
}

export fn mk_ffmpeg_version() u32 { return c.avformat_version(); }

export fn mk_benchmark(iterations: u64) u64 {
    var x = Time{ .num = 1001, .den = 30000 };
    const y = Time{ .num = 1, .den = 48000 };
    var sum: u64 = 0;
    var i: u64 = 0;
    while (i < iterations) : (i += 1) {
        const z = addTime(x, y) orelse break;
        sum ^= @as(u64, @bitCast(z.num)) +% @as(u64, @bitCast(z.den)) +% i;
        x = if ((i & 1) == 1) .{ .num = 1001, .den = 30000 } else .{ .num = 1, .den = 24 };
    }
    return sum;
}
