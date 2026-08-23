const std = @import("std");
const c = @cImport({
    @cInclude("stdlib.h");
    @cInclude("libavformat/avformat.h");
});

const MK_OK: i32 = 0;
const MK_INVALID: i32 = 1;
const MK_NOT_FOUND: i32 = 2;
const MK_CONFLICT: i32 = 3;
const MK_OVERFLOW: i32 = 5;
const MK_STALE: i32 = 6;
const MK_CYCLE: i32 = 7;

const MK_NODE_SOURCE: u32 = 1;
const MK_NODE_TRANSFORM: u32 = 2;
const MK_NODE_SINK: u32 = 3;
const MK_NO_RESOURCE_SLOT: u32 = std.math.maxInt(u32);

const MAX_ASSETS = 32;
const MAX_CLIPS = 64;
const MAX_PROPOSALS = 64;
const MAX_RESOURCES = 128;
const MAX_NODES = 64;
const MAX_DEPS = 4;
const MAX_ID = 128;
const FNV_OFFSET: u64 = 14695981039346656037;
const FNV_PRIME: u64 = 1099511628211;

const Time = extern struct {
    num: i64,
    den: i64,
};

const ResourceHandle = extern struct {
    slot: u32,
    generation: u32,
};

const Asset = struct {
    id: [MAX_ID]u8 = [_]u8{0} ** MAX_ID,
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

const ResourceSlot = struct {
    generation: u32 = 0,
    refcount: u32 = 0,
    size_bytes: u64 = 0,
    domain: u32 = 0,
    active: bool = false,
};

const PlanNode = struct {
    id: u32 = 0,
    kind: u32 = 0,
    deps: [MAX_DEPS]u32 = [_]u32{0} ** MAX_DEPS,
    dep_count: usize = 0,
    resource: ResourceHandle = .{ .slot = MK_NO_RESOURCE_SLOT, .generation = 0 },
};

const Kernel = struct {
    revision: u64 = 0,
    next_proposal: u64 = 1,
    assets: [MAX_ASSETS]Asset = [_]Asset{.{}} ** MAX_ASSETS,
    asset_count: usize = 0,
    clips: [MAX_CLIPS]Clip = [_]Clip{.{}} ** MAX_CLIPS,
    clip_count: usize = 0,
    proposals: [MAX_PROPOSALS]Proposal = [_]Proposal{.{}} ** MAX_PROPOSALS,
    resources: [MAX_RESOURCES]ResourceSlot = [_]ResourceSlot{.{}} ** MAX_RESOURCES,
    nodes: [MAX_NODES]PlanNode = [_]PlanNode{.{}} ** MAX_NODES,
    node_count: usize = 0,
};

fn normalize128(n_in: i128, d_in: i128) ?Time {
    if (d_in == 0) return null;
    if (n_in == 0) return .{ .num = 0, .den = 1 };
    var n = n_in;
    var d = d_in;
    if (d < 0) {
        n = -n;
        d = -d;
    }
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
    if (n > std.math.maxInt(i64) or n < std.math.minInt(i64) or d <= 0 or d > std.math.maxInt(i64)) return null;
    return .{ .num = @intCast(n), .den = @intCast(d) };
}

fn normalize(t: Time) ?Time {
    return normalize128(t.num, t.den);
}

fn addTime(a_in: Time, b_in: Time) ?Time {
    const a = normalize(a_in) orelse return null;
    const b = normalize(b_in) orelse return null;
    return normalize128(
        @as(i128, a.num) * b.den + @as(i128, b.num) * a.den,
        @as(i128, a.den) * b.den,
    );
}

fn compareTime(a_in: Time, b_in: Time) i32 {
    const a = normalize(a_in) orelse return 0;
    const b = normalize(b_in) orelse return 0;
    const left = @as(i128, a.num) * b.den;
    const right = @as(i128, b.num) * a.den;
    return if (left > right) 1 else if (left < right) -1 else 0;
}

fn positive(t: Time) bool {
    const n = normalize(t) orelse return false;
    return n.num > 0;
}

fn cSlice(ptr: ?[*:0]const u8) ?[]const u8 {
    return if (ptr) |p| std.mem.span(p) else null;
}

fn findAsset(k: *const Kernel, id: []const u8) ?usize {
    for (0..k.asset_count) |i| {
        if (std.mem.eql(u8, k.assets[i].id[0..k.assets[i].id_len], id)) return i;
    }
    return null;
}

fn validClip(k: *const Kernel, clip: Clip) bool {
    if (clip.asset_index >= k.asset_count or !positive(clip.duration)) return false;
    const end = addTime(clip.source_in, clip.duration) orelse return false;
    if (compareTime(clip.source_in, .{ .num = 0, .den = 1 }) < 0) return false;
    if (compareTime(end, k.assets[clip.asset_index].duration) > 0) return false;
    if (clip.transition.num != 0 and (!positive(clip.transition) or compareTime(clip.transition, clip.duration) >= 0)) return false;
    return true;
}

fn validResource(k: *const Kernel, handle: ResourceHandle) bool {
    if (handle.slot >= MAX_RESOURCES) return false;
    const slot = k.resources[handle.slot];
    return slot.active and slot.generation == handle.generation;
}

fn findNode(k: *const Kernel, id: u32) ?usize {
    for (0..k.node_count) |i| if (k.nodes[i].id == id) return i;
    return null;
}

fn hashByte(h: u64, b: u8) u64 {
    return (h ^ @as(u64, b)) *% FNV_PRIME;
}

fn hashU32(h_in: u64, value: u32) u64 {
    var h = h_in;
    for (0..4) |i| h = hashByte(h, @truncate(value >> @intCast(i * 8)));
    return h;
}

fn hashU64(h_in: u64, value: u64) u64 {
    var h = h_in;
    for (0..8) |i| h = hashByte(h, @truncate(value >> @intCast(i * 8)));
    return h;
}

fn hashI64(h: u64, value: i64) u64 {
    return hashU64(h, @bitCast(value));
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

export fn mk_time_compare(a: Time, b: Time) i32 {
    return compareTime(a, b);
}

export fn mk_kernel_create() ?*Kernel {
    const raw = c.malloc(@sizeOf(Kernel)) orelse return null;
    const k: *Kernel = @ptrCast(@alignCast(raw));
    k.* = .{};
    return k;
}

export fn mk_kernel_destroy(k: ?*Kernel) void {
    if (k) |ptr| c.free(ptr);
}

export fn mk_kernel_revision(k: ?*const Kernel) u64 {
    return if (k) |ptr| ptr.revision else 0;
}

export fn mk_kernel_add_asset(k_opt: ?*Kernel, id_ptr: ?[*:0]const u8, duration_in: Time) i32 {
    const k = k_opt orelse return MK_INVALID;
    const id = cSlice(id_ptr) orelse return MK_INVALID;
    const duration = normalize(duration_in) orelse return MK_INVALID;
    if (id.len == 0 or id.len >= MAX_ID or !positive(duration)) return MK_INVALID;
    if (findAsset(k, id) != null) return MK_CONFLICT;
    if (k.asset_count >= MAX_ASSETS) return MK_OVERFLOW;
    var asset = Asset{};
    @memcpy(asset.id[0..id.len], id);
    asset.id_len = id.len;
    asset.duration = duration;
    k.assets[k.asset_count] = asset;
    k.asset_count += 1;
    return MK_OK;
}

export fn mk_kernel_append_clip(
    k_opt: ?*Kernel,
    asset_ptr: ?[*:0]const u8,
    source_in_in: Time,
    duration_in: Time,
    transition_in: Time,
) i32 {
    const k = k_opt orelse return MK_INVALID;
    const asset = cSlice(asset_ptr) orelse return MK_INVALID;
    const asset_index = findAsset(k, asset) orelse return MK_NOT_FOUND;
    if (k.clip_count >= MAX_CLIPS) return MK_INVALID;
    const source_in = normalize(source_in_in) orelse return MK_INVALID;
    const duration = normalize(duration_in) orelse return MK_INVALID;
    const transition = normalize(transition_in) orelse return MK_INVALID;
    const clip = Clip{
        .asset_index = asset_index,
        .source_in = source_in,
        .duration = duration,
        .transition = transition,
    };
    if ((k.clip_count == 0 and transition.num != 0) or !validClip(k, clip)) return MK_INVALID;
    k.clips[k.clip_count] = clip;
    k.clip_count += 1;
    return MK_OK;
}

export fn mk_kernel_propose_trim(
    k_opt: ?*Kernel,
    base_revision: u64,
    clip_index: usize,
    duration_in: Time,
    proposal_id: ?*u64,
) i32 {
    const k = k_opt orelse return MK_INVALID;
    const out = proposal_id orelse return MK_INVALID;
    if (base_revision != k.revision) return MK_CONFLICT;
    if (clip_index >= k.clip_count or !positive(duration_in)) return MK_INVALID;
    const duration = normalize(duration_in) orelse return MK_INVALID;
    var candidate = k.clips[clip_index];
    candidate.duration = duration;
    if (!validClip(k, candidate)) return MK_INVALID;
    var slot_index: ?usize = null;
    for (0..MAX_PROPOSALS) |i| if (!k.proposals[i].active) {
        slot_index = i;
        break;
    };
    const slot = slot_index orelse return MK_OVERFLOW;
    const id = k.next_proposal;
    k.next_proposal += 1;
    k.proposals[slot] = .{
        .active = true,
        .id = id,
        .base_revision = base_revision,
        .clip_index = clip_index,
        .new_duration = duration,
    };
    out.* = id;
    return MK_OK;
}

export fn mk_kernel_commit(k_opt: ?*Kernel, proposal_id: u64, new_revision: ?*u64) i32 {
    const k = k_opt orelse return MK_INVALID;
    const out = new_revision orelse return MK_INVALID;
    var proposal_opt: ?Proposal = null;
    for (k.proposals) |proposal| if (proposal.active and proposal.id == proposal_id) {
        proposal_opt = proposal;
        break;
    };
    const proposal = proposal_opt orelse return MK_NOT_FOUND;
    if (proposal.base_revision != k.revision) return MK_CONFLICT;
    var candidate = k.clips[proposal.clip_index];
    candidate.duration = proposal.new_duration;
    if (!validClip(k, candidate)) return MK_INVALID;
    k.clips[proposal.clip_index] = candidate;
    k.revision += 1;
    for (&k.proposals) |*item| item.active = false;
    out.* = k.revision;
    return MK_OK;
}

export fn mk_kernel_state_hash(k_opt: ?*const Kernel) u64 {
    const k = k_opt orelse return 0;
    var h = hashU64(FNV_OFFSET, k.revision);
    h = hashU64(h, k.asset_count);
    for (0..k.asset_count) |i| {
        const asset = k.assets[i];
        h = hashU64(h, asset.id_len);
        for (asset.id[0..asset.id_len]) |b| h = hashByte(h, b);
        h = hashI64(h, asset.duration.num);
        h = hashI64(h, asset.duration.den);
    }
    h = hashU64(h, k.clip_count);
    for (0..k.clip_count) |i| {
        const clip = k.clips[i];
        h = hashU64(h, clip.asset_index);
        h = hashI64(h, clip.source_in.num);
        h = hashI64(h, clip.source_in.den);
        h = hashI64(h, clip.duration.num);
        h = hashI64(h, clip.duration.den);
        h = hashI64(h, clip.transition.num);
        h = hashI64(h, clip.transition.den);
    }
    return h;
}

export fn mk_resource_alloc(k_opt: ?*Kernel, size_bytes: u64, domain: u32, out_opt: ?*ResourceHandle) i32 {
    const k = k_opt orelse return MK_INVALID;
    const out = out_opt orelse return MK_INVALID;
    if (size_bytes == 0 or domain == 0) return MK_INVALID;
    for (0..MAX_RESOURCES) |i| {
        if (!k.resources[i].active) {
            if (k.resources[i].generation == 0) k.resources[i].generation = 1;
            k.resources[i].active = true;
            k.resources[i].refcount = 1;
            k.resources[i].size_bytes = size_bytes;
            k.resources[i].domain = domain;
            out.* = .{ .slot = @intCast(i), .generation = k.resources[i].generation };
            return MK_OK;
        }
    }
    return MK_OVERFLOW;
}

export fn mk_resource_retain(k_opt: ?*Kernel, handle: ResourceHandle) i32 {
    const k = k_opt orelse return MK_STALE;
    if (!validResource(k, handle)) return MK_STALE;
    const slot = &k.resources[handle.slot];
    if (slot.refcount == std.math.maxInt(u32)) return MK_OVERFLOW;
    slot.refcount += 1;
    return MK_OK;
}

export fn mk_resource_release(k_opt: ?*Kernel, handle: ResourceHandle) i32 {
    const k = k_opt orelse return MK_STALE;
    if (!validResource(k, handle)) return MK_STALE;
    const slot = &k.resources[handle.slot];
    if (slot.refcount == 0) return MK_STALE;
    slot.refcount -= 1;
    if (slot.refcount == 0) {
        slot.active = false;
        slot.size_bytes = 0;
        slot.domain = 0;
        slot.generation +%= 1;
        if (slot.generation == 0) slot.generation = 1;
    }
    return MK_OK;
}

export fn mk_resource_touch(k_opt: ?*const Kernel, handle: ResourceHandle) i32 {
    const k = k_opt orelse return MK_STALE;
    return if (validResource(k, handle)) MK_OK else MK_STALE;
}

export fn mk_resource_refcount(k_opt: ?*const Kernel, handle: ResourceHandle, out_opt: ?*u32) i32 {
    const k = k_opt orelse return MK_STALE;
    const out = out_opt orelse return MK_INVALID;
    if (!validResource(k, handle)) return MK_STALE;
    out.* = k.resources[handle.slot].refcount;
    return MK_OK;
}

export fn mk_resource_hash(k_opt: ?*const Kernel) u64 {
    const k = k_opt orelse return 0;
    var h = FNV_OFFSET;
    for (k.resources) |slot| {
        h = hashU32(h, slot.generation);
        h = hashU32(h, slot.refcount);
        h = hashU64(h, slot.size_bytes);
        h = hashU32(h, slot.domain);
        h = hashByte(h, if (slot.active) 1 else 0);
    }
    return h;
}

export fn mk_plan_reset(k_opt: ?*Kernel) i32 {
    const k = k_opt orelse return MK_INVALID;
    k.node_count = 0;
    return MK_OK;
}

export fn mk_plan_add_node(
    k_opt: ?*Kernel,
    id: u32,
    kind: u32,
    deps_ptr: ?[*]const u32,
    dep_count: usize,
    resource: ResourceHandle,
) i32 {
    const k = k_opt orelse return MK_INVALID;
    if (id == 0 or dep_count > MAX_DEPS or k.node_count >= MAX_NODES) return MK_INVALID;
    if (kind < MK_NODE_SOURCE or kind > MK_NODE_SINK) return MK_INVALID;
    if (dep_count > 0 and deps_ptr == null) return MK_INVALID;
    if (findNode(k, id) != null) return MK_CONFLICT;
    var node = PlanNode{ .id = id, .kind = kind, .dep_count = dep_count, .resource = resource };
    if (dep_count > 0) {
        const deps = deps_ptr.?;
        for (0..dep_count) |i| node.deps[i] = deps[i];
    }
    k.nodes[k.node_count] = node;
    k.node_count += 1;
    return MK_OK;
}

export fn mk_plan_validate(k_opt: ?*const Kernel) i32 {
    const k = k_opt orelse return MK_INVALID;
    if (k.node_count == 0) return MK_INVALID;
    var indegree = [_]u32{0} ** MAX_NODES;
    var done = [_]bool{false} ** MAX_NODES;
    for (0..k.node_count) |i| {
        const node = k.nodes[i];
        if (node.kind == MK_NODE_SOURCE and node.dep_count != 0) return MK_INVALID;
        if ((node.kind == MK_NODE_TRANSFORM or node.kind == MK_NODE_SINK) and node.dep_count == 0) return MK_INVALID;
        if (node.resource.slot != MK_NO_RESOURCE_SLOT and !validResource(k, node.resource)) return MK_STALE;
        indegree[i] = @intCast(node.dep_count);
        for (0..node.dep_count) |d| if (findNode(k, node.deps[d]) == null) return MK_INVALID;
    }
    var processed: usize = 0;
    while (true) {
        var selected: ?usize = null;
        for (0..k.node_count) |i| {
            if (!done[i] and indegree[i] == 0) {
                selected = i;
                break;
            }
        }
        const s = selected orelse break;
        done[s] = true;
        processed += 1;
        const id = k.nodes[s].id;
        for (0..k.node_count) |i| {
            if (done[i]) continue;
            for (0..k.nodes[i].dep_count) |d| {
                if (k.nodes[i].deps[d] == id and indegree[i] > 0) indegree[i] -= 1;
            }
        }
    }
    return if (processed == k.node_count) MK_OK else MK_CYCLE;
}

export fn mk_plan_hash(k_opt: ?*const Kernel) u64 {
    const k = k_opt orelse return 0;
    var h = hashU64(FNV_OFFSET, k.node_count);
    for (0..k.node_count) |i| {
        const node = k.nodes[i];
        h = hashU32(h, node.id);
        h = hashU32(h, node.kind);
        h = hashU64(h, node.dep_count);
        for (0..node.dep_count) |d| h = hashU32(h, node.deps[d]);
        h = hashU32(h, node.resource.slot);
        h = hashU32(h, node.resource.generation);
    }
    return h;
}

export fn mk_ffmpeg_version() u32 {
    return c.avformat_version();
}

export fn mk_benchmark(iterations: u64) u64 {
    var x = Time{ .num = 1001, .den = 30000 };
    const y = Time{ .num = 1, .den = 48000 };
    var sum: u64 = 0;
    var i: u64 = 0;
    while (i < iterations) : (i += 1) {
        const z = addTime(x, y) orelse break;
        sum ^= @as(u64, @bitCast(z.num)) +% @as(u64, @bitCast(z.den)) +% i;
        x = if ((i & 1) == 1)
            .{ .num = 1001, .den = 30000 }
        else
            .{ .num = 1, .den = 24 };
    }
    return sum;
}
