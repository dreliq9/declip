package mk_bakeoff_odin

import "base:runtime"
import c "core:c"

foreign import avformat "system:avformat"
foreign avformat {
    avformat_version :: proc() -> u32 ---
}

MK_OK               :: c.int(0)
MK_INVALID          :: c.int(1)
MK_NOT_FOUND        :: c.int(2)
MK_CONFLICT         :: c.int(3)
MK_BUFFER_TOO_SMALL :: c.int(4)
MK_OVERFLOW         :: c.int(5)

MAX_ASSETS    :: 16
MAX_CLIPS     :: 16
MAX_PROPOSALS :: 16
MAX_ID_BYTES  :: 128
MAX_COMMAND   :: 4096

I64_MIN_I128 :: i128(-9223372036854775808)
I64_MAX_I128 :: i128( 9223372036854775807)

Time :: struct {
    num: i64,
    den: i64,
}

Asset :: struct {
    id:       [MAX_ID_BYTES]u8,
    id_len:   int,
    duration: Time,
}

Clip :: struct {
    asset_index: int,
    source_in:   Time,
    duration:    Time,
    transition:  Time,
}

Proposal :: struct {
    id:            u64,
    base_revision: u64,
    clip_index:    int,
    new_duration:  Time,
}

Project :: struct {
    revision:       u64,
    next_proposal:  u64,
    assets:         [MAX_ASSETS]Asset,
    asset_count:    int,
    clips:          [MAX_CLIPS]Clip,
    clip_count:     int,
    proposals:      [MAX_PROPOSALS]Proposal,
    proposal_count: int,
}

gcd_u64 :: proc(a_in, b_in: u64) -> u64 {
    a := a_in
    b := b_in
    for b != 0 {
        a, b = b, a % b
    }
    return a
}

normalize :: proc(input: Time, output: ^Time) -> bool {
    if output == nil || input.den == 0 {
        return false
    }

    n := i128(input.num)
    d := i128(input.den)
    if n == 0 {
        output^ = Time{0, 1}
        return true
    }
    if d < 0 {
        n = -n
        d = -d
    }
    if n < I64_MIN_I128 || n > I64_MAX_I128 || d <= 0 || d > I64_MAX_I128 {
        return false
    }

    mag_n := u64(n)
    if n < 0 {
        mag_n = u64(-n)
    }
    g := gcd_u64(mag_n, u64(d))
    output^ = Time{i64(n / i128(g)), i64(d / i128(g))}
    return true
}

positive :: proc(t: Time) -> bool {
    n: Time
    return normalize(t, &n) && n.num > 0
}

compare :: proc(a, b: Time) -> c.int {
    na, nb: Time
    if !normalize(a, &na) || !normalize(b, &nb) {
        return 0
    }
    left  := i128(na.num) * i128(nb.den)
    right := i128(nb.num) * i128(na.den)
    if left < right { return -1 }
    if left > right { return  1 }
    return 0
}

add_exact :: proc(a, b: Time, output: ^Time) -> bool {
    if output == nil {
        return false
    }
    na, nb: Time
    if !normalize(a, &na) || !normalize(b, &nb) {
        return false
    }
    n := i128(na.num)*i128(nb.den) + i128(nb.num)*i128(na.den)
    d := i128(na.den)*i128(nb.den)
    if n < I64_MIN_I128 || n > I64_MAX_I128 || d <= 0 || d > I64_MAX_I128 {
        return false
    }
    return normalize(Time{i64(n), i64(d)}, output)
}

asset_id_matches :: proc(asset: ^Asset, id: cstring) -> bool {
    if asset == nil || id == nil {
        return false
    }
    s := string(id)
    if len(s) != asset.id_len {
        return false
    }
    for i in 0..<asset.id_len {
        if asset.id[i] != s[i] {
            return false
        }
    }
    return true
}

find_asset :: proc(project: ^Project, id: cstring) -> int {
    if project == nil || id == nil {
        return -1
    }
    for i in 0..<project.asset_count {
        if asset_id_matches(&project.assets[i], id) {
            return i
        }
    }
    return -1
}

copy_asset_id :: proc(asset: ^Asset, id: cstring) -> bool {
    if asset == nil || id == nil {
        return false
    }
    s := string(id)
    if len(s) <= 0 || len(s) >= MAX_ID_BYTES {
        return false
    }
    for i in 0..<len(s) {
        asset.id[i] = s[i]
    }
    asset.id_len = len(s)
    return true
}

valid_clip :: proc(project: ^Project, clip: Clip) -> bool {
    if project == nil || clip.asset_index < 0 || clip.asset_index >= project.asset_count || !positive(clip.duration) {
        return false
    }
    end: Time
    if !add_exact(clip.source_in, clip.duration, &end) {
        return false
    }
    if compare(clip.source_in, Time{0, 1}) < 0 || compare(end, project.assets[clip.asset_index].duration) > 0 {
        return false
    }
    if clip.transition.num != 0 && (!positive(clip.transition) || compare(clip.transition, clip.duration) >= 0) {
        return false
    }
    return true
}

append_string :: proc(dst: []u8, pos: ^int, s: string) -> bool {
    if pos == nil || pos^ < 0 || pos^ + len(s) > len(dst) {
        return false
    }
    for i in 0..<len(s) {
        dst[pos^ + i] = s[i]
    }
    pos^ += len(s)
    return true
}

append_asset_id :: proc(dst: []u8, pos: ^int, asset: ^Asset) -> bool {
    if asset == nil || pos == nil || pos^ + asset.id_len > len(dst) {
        return false
    }
    for i in 0..<asset.id_len {
        dst[pos^ + i] = asset.id[i]
    }
    pos^ += asset.id_len
    return true
}

append_u64 :: proc(dst: []u8, pos: ^int, value: u64) -> bool {
    if pos == nil {
        return false
    }
    if value == 0 {
        return append_string(dst, pos, "0")
    }
    v := value
    digits: [32]u8
    n := 0
    for v > 0 {
        digits[n] = u8('0') + u8(v % 10)
        n += 1
        v /= 10
    }
    if pos^ + n > len(dst) {
        return false
    }
    for i in 0..<n {
        dst[pos^ + i] = digits[n-1-i]
    }
    pos^ += n
    return true
}

append_i64 :: proc(dst: []u8, pos: ^int, value: i64) -> bool {
    if value < 0 {
        if !append_string(dst, pos, "-") {
            return false
        }
        return append_u64(dst, pos, u64(-i128(value)))
    }
    return append_u64(dst, pos, u64(value))
}

append_time :: proc(dst: []u8, pos: ^int, value: Time) -> bool {
    n: Time
    if !normalize(value, &n) {
        return false
    }
    return append_i64(dst, pos, n.num) && append_string(dst, pos, "/") && append_i64(dst, pos, n.den)
}

@(export, link_name="mk_time_normalize")
mk_time_normalize :: proc "c" (input: Time, output: ^Time) -> c.int {
    return MK_OK if normalize(input, output) else MK_INVALID
}

@(export, link_name="mk_time_add")
mk_time_add :: proc "c" (a, b: Time, output: ^Time) -> c.int {
    if output == nil {
        return MK_INVALID
    }
    return MK_OK if add_exact(a, b, output) else MK_OVERFLOW
}

@(export, link_name="mk_time_compare")
mk_time_compare :: proc "c" (a, b: Time) -> c.int {
    return compare(a, b)
}

@(export, link_name="mk_project_create")
mk_project_create :: proc "c" () -> rawptr {
    context = runtime.default_context()
    project := new(Project)
    if project == nil {
        return nil
    }
    project.next_proposal = 1
    return rawptr(project)
}

@(export, link_name="mk_project_destroy")
mk_project_destroy :: proc "c" (handle: rawptr) {
    if handle == nil {
        return
    }
    context = runtime.default_context()
    free(cast(^Project)handle)
}

@(export, link_name="mk_project_revision")
mk_project_revision :: proc "c" (handle: rawptr) -> u64 {
    if handle == nil {
        return 0
    }
    return cast(^Project)handle.revision
}

@(export, link_name="mk_project_add_asset")
mk_project_add_asset :: proc "c" (handle: rawptr, id: cstring, duration: Time) -> c.int {
    if handle == nil || id == nil || !positive(duration) {
        return MK_INVALID
    }
    project := cast(^Project)handle
    if find_asset(project, id) >= 0 {
        return MK_CONFLICT
    }
    if project.asset_count >= MAX_ASSETS {
        return MK_INVALID
    }
    n: Time
    if !normalize(duration, &n) {
        return MK_INVALID
    }
    asset := &project.assets[project.asset_count]
    if !copy_asset_id(asset, id) {
        return MK_INVALID
    }
    asset.duration = n
    project.asset_count += 1
    return MK_OK
}

@(export, link_name="mk_project_append_clip")
mk_project_append_clip :: proc "c" (handle: rawptr, asset_id: cstring, source_in, duration, transition_in: Time) -> c.int {
    if handle == nil || asset_id == nil {
        return MK_INVALID
    }
    project := cast(^Project)handle
    if project.clip_count >= MAX_CLIPS {
        return MK_INVALID
    }
    asset_index := find_asset(project, asset_id)
    if asset_index < 0 {
        return MK_INVALID
    }
    ns, nd, nt: Time
    if !normalize(source_in, &ns) || !normalize(duration, &nd) || !normalize(transition_in, &nt) {
        return MK_INVALID
    }
    clip := Clip{asset_index, ns, nd, nt}
    if !valid_clip(project, clip) || (project.clip_count == 0 && nt.num != 0) {
        return MK_INVALID
    }
    project.clips[project.clip_count] = clip
    project.clip_count += 1
    return MK_OK
}

@(export, link_name="mk_project_propose_trim")
mk_project_propose_trim :: proc "c" (handle: rawptr, base_revision: u64, clip_index: uintptr, duration: Time, out_proposal: ^u64) -> c.int {
    if handle == nil || out_proposal == nil {
        return MK_INVALID
    }
    project := cast(^Project)handle
    if base_revision != project.revision {
        return MK_CONFLICT
    }
    if clip_index >= uintptr(project.clip_count) || !positive(duration) || project.proposal_count >= MAX_PROPOSALS {
        return MK_INVALID
    }
    nd: Time
    if !normalize(duration, &nd) {
        return MK_INVALID
    }
    idx := int(clip_index)
    candidate := project.clips[idx]
    candidate.duration = nd
    if !valid_clip(project, candidate) {
        return MK_INVALID
    }
    id := project.next_proposal
    project.next_proposal += 1
    project.proposals[project.proposal_count] = Proposal{id, base_revision, idx, nd}
    project.proposal_count += 1
    out_proposal^ = id
    return MK_OK
}

@(export, link_name="mk_project_commit")
mk_project_commit :: proc "c" (handle: rawptr, proposal_id: u64, out_revision: ^u64) -> c.int {
    if handle == nil || out_revision == nil {
        return MK_INVALID
    }
    project := cast(^Project)handle
    proposal_index := -1
    for i in 0..<project.proposal_count {
        if project.proposals[i].id == proposal_id {
            proposal_index = i
            break
        }
    }
    if proposal_index < 0 {
        return MK_NOT_FOUND
    }
    proposal := project.proposals[proposal_index]
    if proposal.base_revision != project.revision {
        return MK_CONFLICT
    }
    candidate := project.clips[proposal.clip_index]
    candidate.duration = proposal.new_duration
    if !valid_clip(project, candidate) {
        return MK_INVALID
    }
    project.clips[proposal.clip_index] = candidate
    project.revision += 1
    project.proposal_count = 0
    out_revision^ = project.revision
    return MK_OK
}

@(export, link_name="mk_project_lower_ffmpeg")
mk_project_lower_ffmpeg :: proc "c" (handle: rawptr, buffer: rawptr, capacity: uintptr, needed: ^uintptr) -> c.int {
    if handle == nil || needed == nil {
        return MK_INVALID
    }
    project := cast(^Project)handle
    command: [MAX_COMMAND]u8
    pos := 0

    if !append_string(command[:], &pos, "ffmpeg") {
        return MK_OVERFLOW
    }
    for i in 0..<project.clip_count {
        if !append_string(command[:], &pos, " -i ") || !append_asset_id(command[:], &pos, &project.assets[project.clips[i].asset_index]) {
            return MK_OVERFLOW
        }
    }
    if !append_string(command[:], &pos, " -filter_complex \"") {
        return MK_OVERFLOW
    }
    for i in 0..<project.clip_count {
        clip := project.clips[i]
        if i > 0 && !append_string(command[:], &pos, ";") { return MK_OVERFLOW }
        if !append_string(command[:], &pos, "[") || !append_u64(command[:], &pos, u64(i)) || !append_string(command[:], &pos, ":v]trim=start=") ||
           !append_time(command[:], &pos, clip.source_in) || !append_string(command[:], &pos, ":duration=") || !append_time(command[:], &pos, clip.duration) ||
           !append_string(command[:], &pos, "[v") || !append_u64(command[:], &pos, u64(i)) || !append_string(command[:], &pos, "]") {
            return MK_OVERFLOW
        }
    }
    for i in 1..<project.clip_count {
        clip := project.clips[i]
        if clip.transition.num != 0 {
            if !append_string(command[:], &pos, ";[v") || !append_u64(command[:], &pos, u64(i-1)) || !append_string(command[:], &pos, "][v") ||
               !append_u64(command[:], &pos, u64(i)) || !append_string(command[:], &pos, "]xfade=duration=") || !append_time(command[:], &pos, clip.transition) ||
               !append_string(command[:], &pos, "[x") || !append_u64(command[:], &pos, u64(i)) || !append_string(command[:], &pos, "]") {
                return MK_OVERFLOW
            }
        }
    }
    if !append_string(command[:], &pos, "\" out.mp4") {
        return MK_OVERFLOW
    }

    required := uintptr(pos + 1)
    needed^ = required
    if buffer == nil || capacity < required {
        return MK_BUFFER_TOO_SMALL
    }
    out := cast([^]u8)buffer
    for i in 0..<pos {
        out[i] = command[i]
    }
    out[pos] = 0
    return MK_OK
}

@(export, link_name="mk_ffmpeg_version")
mk_ffmpeg_version :: proc "c" () -> u32 {
    return avformat_version()
}

@(export, link_name="mk_benchmark")
mk_benchmark :: proc "c" (iterations: u64) -> u64 {
    x := Time{1001, 30000}
    y := Time{1, 48000}
    z: Time
    sum: u64 = 0
    i: u64 = 0
    for i < iterations {
        if !add_exact(x, y, &z) {
            break
        }
        sum ^= u64(z.num) + u64(z.den) + i
        x = Time{1001, 30000} if (i & 1) != 0 else Time{1, 24}
        i += 1
    }
    return sum
}
