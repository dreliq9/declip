package mk_arch_bakeoff_odin

import "base:runtime"
import c "core:c"

foreign import avformat "system:avformat"
foreign avformat {
    avformat_version :: proc() -> u32 ---
}

MK_OK        :: c.int(0)
MK_INVALID   :: c.int(1)
MK_NOT_FOUND :: c.int(2)
MK_CONFLICT  :: c.int(3)
MK_OVERFLOW  :: c.int(5)
MK_STALE     :: c.int(6)
MK_CYCLE     :: c.int(7)

MK_NODE_SOURCE    :: u32(1)
MK_NODE_TRANSFORM :: u32(2)
MK_NODE_SINK      :: u32(3)
MK_NO_RESOURCE_SLOT :: u32(0xffff_ffff)

MAX_ASSETS    :: 32
MAX_CLIPS     :: 64
MAX_PROPOSALS :: 64
MAX_RESOURCES :: 128
MAX_NODES     :: 64
MAX_DEPS      :: 4
MAX_ID_BYTES  :: 128

FNV_OFFSET :: u64(14695981039346656037)
FNV_PRIME  :: u64(1099511628211)

I64_MIN_I128 :: i128(-9223372036854775808)
I64_MAX_I128 :: i128( 9223372036854775807)

Time :: struct {
    num: i64,
    den: i64,
}

Resource_Handle :: struct {
    slot:       u32,
    generation: u32,
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
    active:        bool,
    id:            u64,
    base_revision: u64,
    clip_index:    int,
    new_duration:  Time,
}

Resource_Slot :: struct {
    generation: u32,
    refcount:   u32,
    size_bytes: u64,
    domain:     u32,
    active:     bool,
}

Plan_Node :: struct {
    id:        u32,
    kind:      u32,
    deps:      [MAX_DEPS]u32,
    dep_count: int,
    resource:  Resource_Handle,
}

Kernel :: struct {
    revision:      u64,
    next_proposal: u64,

    assets:      [MAX_ASSETS]Asset,
    asset_count: int,
    clips:       [MAX_CLIPS]Clip,
    clip_count:  int,
    proposals:   [MAX_PROPOSALS]Proposal,

    resources: [MAX_RESOURCES]Resource_Slot,

    nodes:      [MAX_NODES]Plan_Node,
    node_count: int,
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

find_asset :: proc(kernel: ^Kernel, id: cstring) -> int {
    if kernel == nil || id == nil {
        return -1
    }
    for i in 0..<kernel.asset_count {
        if asset_id_matches(&kernel.assets[i], id) {
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

valid_clip :: proc(kernel: ^Kernel, clip: Clip) -> bool {
    if kernel == nil || clip.asset_index < 0 || clip.asset_index >= kernel.asset_count || !positive(clip.duration) {
        return false
    }
    end: Time
    if !add_exact(clip.source_in, clip.duration, &end) {
        return false
    }
    if compare(clip.source_in, Time{0, 1}) < 0 || compare(end, kernel.assets[clip.asset_index].duration) > 0 {
        return false
    }
    if clip.transition.num != 0 && (!positive(clip.transition) || compare(clip.transition, clip.duration) >= 0) {
        return false
    }
    return true
}

valid_resource :: proc(kernel: ^Kernel, handle: Resource_Handle) -> bool {
    if kernel == nil || handle.slot >= MAX_RESOURCES {
        return false
    }
    slot := &kernel.resources[int(handle.slot)]
    return slot.active && slot.generation == handle.generation
}

find_node :: proc(kernel: ^Kernel, id: u32) -> int {
    if kernel == nil {
        return -1
    }
    for i in 0..<kernel.node_count {
        if kernel.nodes[i].id == id {
            return i
        }
    }
    return -1
}

hash_byte :: proc(h: u64, b: u8) -> u64 {
    return (h ~ u64(b)) * FNV_PRIME
}

hash_u32 :: proc(h_in: u64, value: u32) -> u64 {
    h := h_in
    for i in 0..<4 {
        shift := u32(i*8)
        h = hash_byte(h, u8((value >> shift) & 0xff))
    }
    return h
}

hash_u64 :: proc(h_in: u64, value: u64) -> u64 {
    h := h_in
    for i in 0..<8 {
        shift := u64(i*8)
        h = hash_byte(h, u8((value >> shift) & 0xff))
    }
    return h
}

hash_i64 :: proc(h: u64, value: i64) -> u64 {
    return hash_u64(h, u64(value))
}

@(export, link_name="mk_time_normalize")
mk_time_normalize :: proc "c" (input: Time, output: ^Time) -> c.int {
    context = runtime.default_context()
    return MK_OK if normalize(input, output) else MK_INVALID
}

@(export, link_name="mk_time_add")
mk_time_add :: proc "c" (a, b: Time, output: ^Time) -> c.int {
    context = runtime.default_context()
    if output == nil {
        return MK_INVALID
    }
    return MK_OK if add_exact(a, b, output) else MK_OVERFLOW
}

@(export, link_name="mk_time_compare")
mk_time_compare :: proc "c" (a, b: Time) -> c.int {
    context = runtime.default_context()
    return compare(a, b)
}

@(export, link_name="mk_kernel_create")
mk_kernel_create :: proc "c" () -> rawptr {
    context = runtime.default_context()
    kernel := new(Kernel)
    if kernel == nil {
        return nil
    }
    kernel.next_proposal = 1
    return rawptr(kernel)
}

@(export, link_name="mk_kernel_destroy")
mk_kernel_destroy :: proc "c" (handle: rawptr) {
    if handle == nil {
        return
    }
    context = runtime.default_context()
    free(cast(^Kernel)handle)
}

@(export, link_name="mk_kernel_revision")
mk_kernel_revision :: proc "c" (handle: rawptr) -> u64 {
    context = runtime.default_context()
    if handle == nil {
        return 0
    }
    kernel := cast(^Kernel)handle
    return kernel.revision
}

@(export, link_name="mk_kernel_add_asset")
mk_kernel_add_asset :: proc "c" (handle: rawptr, id: cstring, duration: Time) -> c.int {
    context = runtime.default_context()
    if handle == nil || id == nil || !positive(duration) {
        return MK_INVALID
    }
    kernel := cast(^Kernel)handle
    if find_asset(kernel, id) >= 0 {
        return MK_CONFLICT
    }
    if kernel.asset_count >= MAX_ASSETS {
        return MK_OVERFLOW
    }
    n: Time
    if !normalize(duration, &n) {
        return MK_INVALID
    }
    asset := &kernel.assets[kernel.asset_count]
    if !copy_asset_id(asset, id) {
        return MK_INVALID
    }
    asset.duration = n
    kernel.asset_count += 1
    return MK_OK
}

@(export, link_name="mk_kernel_append_clip")
mk_kernel_append_clip :: proc "c" (
    handle: rawptr,
    asset_id: cstring,
    source_in, duration, transition_in: Time,
) -> c.int {
    context = runtime.default_context()
    if handle == nil || asset_id == nil {
        return MK_INVALID
    }
    kernel := cast(^Kernel)handle
    if kernel.clip_count >= MAX_CLIPS {
        return MK_INVALID
    }
    asset_index := find_asset(kernel, asset_id)
    if asset_index < 0 {
        return MK_NOT_FOUND
    }
    ns, nd, nt: Time
    if !normalize(source_in, &ns) || !normalize(duration, &nd) || !normalize(transition_in, &nt) {
        return MK_INVALID
    }
    clip := Clip{asset_index, ns, nd, nt}
    if (kernel.clip_count == 0 && nt.num != 0) || !valid_clip(kernel, clip) {
        return MK_INVALID
    }
    kernel.clips[kernel.clip_count] = clip
    kernel.clip_count += 1
    return MK_OK
}

@(export, link_name="mk_kernel_propose_trim")
mk_kernel_propose_trim :: proc "c" (
    handle: rawptr,
    base_revision: u64,
    clip_index: uintptr,
    duration: Time,
    out_proposal: ^u64,
) -> c.int {
    context = runtime.default_context()
    if handle == nil || out_proposal == nil {
        return MK_INVALID
    }
    kernel := cast(^Kernel)handle
    if base_revision != kernel.revision {
        return MK_CONFLICT
    }
    if clip_index >= uintptr(kernel.clip_count) || !positive(duration) {
        return MK_INVALID
    }
    nd: Time
    if !normalize(duration, &nd) {
        return MK_INVALID
    }
    idx := int(clip_index)
    candidate := kernel.clips[idx]
    candidate.duration = nd
    if !valid_clip(kernel, candidate) {
        return MK_INVALID
    }
    proposal_index := -1
    for i in 0..<MAX_PROPOSALS {
        if !kernel.proposals[i].active {
            proposal_index = i
            break
        }
    }
    if proposal_index < 0 {
        return MK_OVERFLOW
    }
    id := kernel.next_proposal
    kernel.next_proposal += 1
    kernel.proposals[proposal_index] = Proposal{true, id, base_revision, idx, nd}
    out_proposal^ = id
    return MK_OK
}

@(export, link_name="mk_kernel_commit")
mk_kernel_commit :: proc "c" (handle: rawptr, proposal_id: u64, out_revision: ^u64) -> c.int {
    context = runtime.default_context()
    if handle == nil || out_revision == nil {
        return MK_INVALID
    }
    kernel := cast(^Kernel)handle
    proposal_index := -1
    for i in 0..<MAX_PROPOSALS {
        if kernel.proposals[i].active && kernel.proposals[i].id == proposal_id {
            proposal_index = i
            break
        }
    }
    if proposal_index < 0 {
        return MK_NOT_FOUND
    }
    proposal := kernel.proposals[proposal_index]
    if proposal.base_revision != kernel.revision {
        return MK_CONFLICT
    }
    candidate := kernel.clips[proposal.clip_index]
    candidate.duration = proposal.new_duration
    if !valid_clip(kernel, candidate) {
        return MK_INVALID
    }
    kernel.clips[proposal.clip_index] = candidate
    kernel.revision += 1
    for i in 0..<MAX_PROPOSALS {
        kernel.proposals[i].active = false
    }
    out_revision^ = kernel.revision
    return MK_OK
}

@(export, link_name="mk_kernel_state_hash")
mk_kernel_state_hash :: proc "c" (handle: rawptr) -> u64 {
    context = runtime.default_context()
    if handle == nil {
        return 0
    }
    kernel := cast(^Kernel)handle
    h := hash_u64(FNV_OFFSET, kernel.revision)
    h = hash_u64(h, u64(kernel.asset_count))
    for i in 0..<kernel.asset_count {
        asset := kernel.assets[i]
        h = hash_u64(h, u64(asset.id_len))
        for j in 0..<asset.id_len {
            h = hash_byte(h, asset.id[j])
        }
        h = hash_i64(h, asset.duration.num)
        h = hash_i64(h, asset.duration.den)
    }
    h = hash_u64(h, u64(kernel.clip_count))
    for i in 0..<kernel.clip_count {
        clip := kernel.clips[i]
        h = hash_u64(h, u64(clip.asset_index))
        h = hash_i64(h, clip.source_in.num)
        h = hash_i64(h, clip.source_in.den)
        h = hash_i64(h, clip.duration.num)
        h = hash_i64(h, clip.duration.den)
        h = hash_i64(h, clip.transition.num)
        h = hash_i64(h, clip.transition.den)
    }
    return h
}

@(export, link_name="mk_resource_alloc")
mk_resource_alloc :: proc "c" (
    handle: rawptr,
    size_bytes: u64,
    domain: u32,
    out_handle: ^Resource_Handle,
) -> c.int {
    context = runtime.default_context()
    if handle == nil || out_handle == nil || size_bytes == 0 || domain == 0 {
        return MK_INVALID
    }
    kernel := cast(^Kernel)handle
    for i in 0..<MAX_RESOURCES {
        slot := &kernel.resources[i]
        if !slot.active {
            if slot.generation == 0 {
                slot.generation = 1
            }
            slot.active = true
            slot.refcount = 1
            slot.size_bytes = size_bytes
            slot.domain = domain
            out_handle^ = Resource_Handle{u32(i), slot.generation}
            return MK_OK
        }
    }
    return MK_OVERFLOW
}

@(export, link_name="mk_resource_retain")
mk_resource_retain :: proc "c" (handle: rawptr, resource: Resource_Handle) -> c.int {
    context = runtime.default_context()
    if handle == nil {
        return MK_STALE
    }
    kernel := cast(^Kernel)handle
    if !valid_resource(kernel, resource) {
        return MK_STALE
    }
    slot := &kernel.resources[int(resource.slot)]
    if slot.refcount == 0xffff_ffff {
        return MK_OVERFLOW
    }
    slot.refcount += 1
    return MK_OK
}

@(export, link_name="mk_resource_release")
mk_resource_release :: proc "c" (handle: rawptr, resource: Resource_Handle) -> c.int {
    context = runtime.default_context()
    if handle == nil {
        return MK_STALE
    }
    kernel := cast(^Kernel)handle
    if !valid_resource(kernel, resource) {
        return MK_STALE
    }
    slot := &kernel.resources[int(resource.slot)]
    if slot.refcount == 0 {
        return MK_STALE
    }
    slot.refcount -= 1
    if slot.refcount == 0 {
        slot.active = false
        slot.size_bytes = 0
        slot.domain = 0
        slot.generation += 1
        if slot.generation == 0 {
            slot.generation = 1
        }
    }
    return MK_OK
}

@(export, link_name="mk_resource_touch")
mk_resource_touch :: proc "c" (handle: rawptr, resource: Resource_Handle) -> c.int {
    context = runtime.default_context()
    if handle == nil {
        return MK_STALE
    }
    kernel := cast(^Kernel)handle
    return MK_OK if valid_resource(kernel, resource) else MK_STALE
}

@(export, link_name="mk_resource_refcount")
mk_resource_refcount :: proc "c" (
    handle: rawptr,
    resource: Resource_Handle,
    out_refcount: ^u32,
) -> c.int {
    context = runtime.default_context()
    if handle == nil {
        return MK_STALE
    }
    if out_refcount == nil {
        return MK_INVALID
    }
    kernel := cast(^Kernel)handle
    if !valid_resource(kernel, resource) {
        return MK_STALE
    }
    out_refcount^ = kernel.resources[int(resource.slot)].refcount
    return MK_OK
}

@(export, link_name="mk_resource_hash")
mk_resource_hash :: proc "c" (handle: rawptr) -> u64 {
    context = runtime.default_context()
    if handle == nil {
        return 0
    }
    kernel := cast(^Kernel)handle
    h := FNV_OFFSET
    for i in 0..<MAX_RESOURCES {
        slot := kernel.resources[i]
        h = hash_u32(h, slot.generation)
        h = hash_u32(h, slot.refcount)
        h = hash_u64(h, slot.size_bytes)
        h = hash_u32(h, slot.domain)
        h = hash_byte(h, 1 if slot.active else 0)
    }
    return h
}

@(export, link_name="mk_plan_reset")
mk_plan_reset :: proc "c" (handle: rawptr) -> c.int {
    context = runtime.default_context()
    if handle == nil {
        return MK_INVALID
    }
    kernel := cast(^Kernel)handle
    kernel.node_count = 0
    return MK_OK
}

@(export, link_name="mk_plan_add_node")
mk_plan_add_node :: proc "c" (
    handle: rawptr,
    id, kind: u32,
    deps: [^]u32,
    dep_count: uintptr,
    resource: Resource_Handle,
) -> c.int {
    context = runtime.default_context()
    if handle == nil || id == 0 || dep_count > MAX_DEPS {
        return MK_INVALID
    }
    if kind < MK_NODE_SOURCE || kind > MK_NODE_SINK {
        return MK_INVALID
    }
    kernel := cast(^Kernel)handle
    if kernel.node_count >= MAX_NODES {
        return MK_INVALID
    }
    if find_node(kernel, id) >= 0 {
        return MK_CONFLICT
    }
    if dep_count > 0 && deps == nil {
        return MK_INVALID
    }
    node := Plan_Node{}
    node.id = id
    node.kind = kind
    node.dep_count = int(dep_count)
    node.resource = resource
    for i in 0..<int(dep_count) {
        node.deps[i] = deps[i]
    }
    kernel.nodes[kernel.node_count] = node
    kernel.node_count += 1
    return MK_OK
}

@(export, link_name="mk_plan_validate")
mk_plan_validate :: proc "c" (handle: rawptr) -> c.int {
    context = runtime.default_context()
    if handle == nil {
        return MK_INVALID
    }
    kernel := cast(^Kernel)handle
    if kernel.node_count == 0 {
        return MK_INVALID
    }
    indegree: [MAX_NODES]u32
    done: [MAX_NODES]bool
    for i in 0..<kernel.node_count {
        node := kernel.nodes[i]
        if node.kind == MK_NODE_SOURCE && node.dep_count != 0 {
            return MK_INVALID
        }
        if (node.kind == MK_NODE_TRANSFORM || node.kind == MK_NODE_SINK) && node.dep_count == 0 {
            return MK_INVALID
        }
        if node.resource.slot != MK_NO_RESOURCE_SLOT && !valid_resource(kernel, node.resource) {
            return MK_STALE
        }
        indegree[i] = u32(node.dep_count)
        for d in 0..<node.dep_count {
            if find_node(kernel, node.deps[d]) < 0 {
                return MK_INVALID
            }
        }
    }
    processed := 0
    for {
        selected := -1
        for i in 0..<kernel.node_count {
            if !done[i] && indegree[i] == 0 {
                selected = i
                break
            }
        }
        if selected < 0 {
            break
        }
        done[selected] = true
        processed += 1
        id := kernel.nodes[selected].id
        for i in 0..<kernel.node_count {
            if done[i] {
                continue
            }
            for d in 0..<kernel.nodes[i].dep_count {
                if kernel.nodes[i].deps[d] == id && indegree[i] > 0 {
                    indegree[i] -= 1
                }
            }
        }
    }
    return MK_OK if processed == kernel.node_count else MK_CYCLE
}

@(export, link_name="mk_plan_hash")
mk_plan_hash :: proc "c" (handle: rawptr) -> u64 {
    context = runtime.default_context()
    if handle == nil {
        return 0
    }
    kernel := cast(^Kernel)handle
    h := hash_u64(FNV_OFFSET, u64(kernel.node_count))
    for i in 0..<kernel.node_count {
        node := kernel.nodes[i]
        h = hash_u32(h, node.id)
        h = hash_u32(h, node.kind)
        h = hash_u64(h, u64(node.dep_count))
        for d in 0..<node.dep_count {
            h = hash_u32(h, node.deps[d])
        }
        h = hash_u32(h, node.resource.slot)
        h = hash_u32(h, node.resource.generation)
    }
    return h
}

@(export, link_name="mk_ffmpeg_version")
mk_ffmpeg_version :: proc "c" () -> u32 {
    context = runtime.default_context()
    return avformat_version()
}

@(export, link_name="mk_benchmark")
mk_benchmark :: proc "c" (iterations: u64) -> u64 {
    context = runtime.default_context()
    x := Time{1001, 30000}
    y := Time{1, 48000}
    z: Time
    sum: u64 = 0
    i: u64 = 0
    for i < iterations {
        if !add_exact(x, y, &z) {
            break
        }
        sum ~= u64(z.num) + u64(z.den) + i
        x = Time{1001, 30000} if (i & 1) != 0 else Time{1, 24}
        i += 1
    }
    return sum
}
