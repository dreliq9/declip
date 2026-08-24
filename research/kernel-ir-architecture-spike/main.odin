package main

import "core:fmt"

MAX_ASSETS :: 4
MAX_CLIPS  :: 4
MAX_OPS    :: 16
MAX_ATTRS  :: 12
MAX_EXEC   :: 16

FNV_OFFSET :: u64(14695981039346656037)
FNV_PRIME  :: u64(1099511628211)

I64_MIN_I128 :: i128(-9223372036854775808)
I64_MAX_I128 :: i128( 9223372036854775807)

Time :: struct {
    value: i64,
    scale: i64,
}

Media_Kind :: enum u8 {
    Video,
    Audio,
}

Loss :: enum u8 {
    Exact,
    Baked_Loss_Of_Editability,
}

Target :: struct {
    supports_transition: bool,
}

normalize_time :: proc(input: Time, out: ^Time) -> bool {
    if out == nil || input.scale <= 0 {
        return false
    }
    n := i128(input.value)
    d := i128(input.scale)
    if n == 0 {
        out^ = Time{0, 1}
        return true
    }
    mag := n
    if mag < 0 { mag = -mag }
    a := u64(mag % d)
    b := u64(d)
    for b != 0 {
        a, b = b, a % b
    }
    g := i128(a)
    if g == 0 { g = 1 }
    n /= g
    d /= g
    if n < I64_MIN_I128 || n > I64_MAX_I128 || d <= 0 || d > I64_MAX_I128 {
        return false
    }
    out^ = Time{i64(n), i64(d)}
    return true
}

add_time :: proc(a, b: Time, out: ^Time) -> bool {
    na, nb: Time
    if !normalize_time(a, &na) || !normalize_time(b, &nb) || out == nil {
        return false
    }
    n := i128(na.value)*i128(nb.scale) + i128(nb.value)*i128(na.scale)
    d := i128(na.scale)*i128(nb.scale)
    if n < I64_MIN_I128 || n > I64_MAX_I128 || d <= 0 || d > I64_MAX_I128 {
        // The fixture uses small scales; production exact-time uses the reduced algorithm
        // frozen in docs/media-kernel-exact-time.md.
        return false
    }
    return normalize_time(Time{i64(n), i64(d)}, out)
}

sub_time :: proc(a, b: Time, out: ^Time) -> bool {
    return add_time(a, Time{-b.value, b.scale}, out)
}

cmp_time :: proc(a, b: Time) -> int {
    na, nb: Time
    if !normalize_time(a, &na) || !normalize_time(b, &nb) {
        return 0
    }
    left := i128(na.value)*i128(nb.scale)
    right := i128(nb.value)*i128(na.scale)
    if left < right { return -1 }
    if left > right { return 1 }
    return 0
}

positive_time :: proc(t: Time) -> bool {
    n: Time
    return normalize_time(t, &n) && n.value > 0
}

hash_byte :: proc(h: u64, b: u8) -> u64 {
    return (h ~ u64(b)) * FNV_PRIME
}

hash_u64 :: proc(h_in, value: u64) -> u64 {
    h := h_in
    v := value
    for _ in 0..<8 {
        h = hash_byte(h, u8(v & 0xff))
        v >>= 8
    }
    return h
}

hash_i64 :: proc(h: u64, value: i64) -> u64 {
    // Fixture semantic values are non-negative; IDs/scales are positive.
    return hash_u64(h, u64(value))
}

hash_time :: proc(h_in: u64, input: Time) -> u64 {
    n: Time
    if !normalize_time(input, &n) { return 0 }
    h := hash_i64(h_in, n.value)
    return hash_i64(h, n.scale)
}

// ----- Common semantic contract -----

Snap_Asset :: struct {
    id:       u32,
    kind:     Media_Kind,
    duration: Time,
}

Snap_Clip :: struct {
    id:             u32,
    asset_id:       u32,
    kind:           Media_Kind,
    timeline_start: Time,
    source_in:      Time,
    duration:       Time,
}

Snap_Transition :: struct {
    id:         u32,
    left_clip:  u32,
    right_clip: u32,
    duration:   Time,
}

Snap_Output :: struct {
    width:    i64,
    height:   i64,
    rate_num: i64,
    rate_den: i64,
    color:    i64,
}

Snapshot :: struct {
    assets:       [MAX_ASSETS]Snap_Asset,
    asset_count:  int,
    clips:        [MAX_CLIPS]Snap_Clip,
    clip_count:   int,
    transition:   Snap_Transition,
    output:       Snap_Output,
}

find_snap_asset :: proc(s: ^Snapshot, id: u32) -> ^Snap_Asset {
    if s == nil { return nil }
    for i in 0..<s.asset_count {
        if s.assets[i].id == id { return &s.assets[i] }
    }
    return nil
}

find_snap_clip :: proc(s: ^Snapshot, id: u32) -> ^Snap_Clip {
    if s == nil { return nil }
    for i in 0..<s.clip_count {
        if s.clips[i].id == id { return &s.clips[i] }
    }
    return nil
}

verify_snapshot :: proc(s: ^Snapshot) -> bool {
    if s == nil || s.asset_count != 3 || s.clip_count != 3 {
        return false
    }
    if s.output.width <= 0 || s.output.height <= 0 || s.output.rate_num <= 0 || s.output.rate_den <= 0 || s.output.color <= 0 {
        return false
    }
    for i in 0..<s.asset_count {
        if s.assets[i].id == 0 || !positive_time(s.assets[i].duration) {
            return false
        }
        for j in i+1..<s.asset_count {
            if s.assets[i].id == s.assets[j].id { return false }
        }
    }
    for i in 0..<s.clip_count {
        clip := &s.clips[i]
        asset := find_snap_asset(s, clip.asset_id)
        if clip.id == 0 || asset == nil || asset.kind != clip.kind || !positive_time(clip.duration) || cmp_time(clip.timeline_start, Time{0,1}) < 0 || cmp_time(clip.source_in, Time{0,1}) < 0 {
            return false
        }
        source_end: Time
        if !add_time(clip.source_in, clip.duration, &source_end) || cmp_time(source_end, asset.duration) > 0 {
            return false
        }
    }
    left := find_snap_clip(s, s.transition.left_clip)
    right := find_snap_clip(s, s.transition.right_clip)
    if s.transition.id == 0 || left == nil || right == nil || left.kind != .Video || right.kind != .Video || !positive_time(s.transition.duration) || cmp_time(s.transition.duration, left.duration) >= 0 || cmp_time(s.transition.duration, right.duration) >= 0 {
        return false
    }
    expected_right_start: Time
    left_end: Time
    if !add_time(left.timeline_start, left.duration, &left_end) || !sub_time(left_end, s.transition.duration, &expected_right_start) {
        return false
    }
    if cmp_time(expected_right_start, right.timeline_start) != 0 {
        return false
    }
    return true
}

snapshot_hash :: proc(s: ^Snapshot) -> u64 {
    if !verify_snapshot(s) { return 0 }
    h := FNV_OFFSET
    h = hash_u64(h, u64(s.asset_count))
    for i in 0..<s.asset_count {
        a := s.assets[i]
        h = hash_u64(h, u64(a.id))
        h = hash_u64(h, u64(a.kind))
        h = hash_time(h, a.duration)
    }
    h = hash_u64(h, u64(s.clip_count))
    for i in 0..<s.clip_count {
        c := s.clips[i]
        h = hash_u64(h, u64(c.id))
        h = hash_u64(h, u64(c.asset_id))
        h = hash_u64(h, u64(c.kind))
        h = hash_time(h, c.timeline_start)
        h = hash_time(h, c.source_in)
        h = hash_time(h, c.duration)
    }
    h = hash_u64(h, u64(s.transition.id))
    h = hash_u64(h, u64(s.transition.left_clip))
    h = hash_u64(h, u64(s.transition.right_clip))
    h = hash_time(h, s.transition.duration)
    h = hash_i64(h, s.output.width)
    h = hash_i64(h, s.output.height)
    h = hash_i64(h, s.output.rate_num)
    h = hash_i64(h, s.output.rate_den)
    h = hash_i64(h, s.output.color)
    return h
}

Exec_Kind :: enum u8 {
    Source_Video,
    Trim_Video,
    Transition_Video,
    Composite_Baked,
    Source_Audio,
    Trim_Audio,
    Gain_Audio,
    Encode_Video,
    Encode_Audio,
    Mux,
}

Exec_Op :: struct {
    id:       u32,
    kind:     Exec_Kind,
    input_a:  u32,
    input_b:  u32,
    source:   u32,
    start:    Time,
    duration: Time,
    scalar:   i64,
}

Exec_Plan :: struct {
    ops:      [MAX_EXEC]Exec_Op,
    count:    int,
    loss:     Loss,
    width:    i64,
    height:   i64,
    rate_num: i64,
    rate_den: i64,
    color:    i64,
}

plan_push :: proc(p: ^Exec_Plan, op: Exec_Op) -> bool {
    if p == nil || p.count >= MAX_EXEC { return false }
    p.ops[p.count] = op
    p.count += 1
    return true
}

lower_snapshot :: proc(s: ^Snapshot, target: Target, out: ^Exec_Plan) -> bool {
    if out == nil || !verify_snapshot(s) { return false }
    out^ = Exec_Plan{}
    out.width = s.output.width
    out.height = s.output.height
    out.rate_num = s.output.rate_num
    out.rate_den = s.output.rate_den
    out.color = s.output.color
    out.loss = .Exact

    c1 := find_snap_clip(s, 101)
    c2 := find_snap_clip(s, 102)
    ca := find_snap_clip(s, 201)
    if c1 == nil || c2 == nil || ca == nil { return false }

    if !plan_push(out, Exec_Op{1, .Source_Video, 0, 0, c1.asset_id, Time{}, Time{}, 0}) { return false }
    if !plan_push(out, Exec_Op{2, .Trim_Video, 1, 0, c1.id, c1.source_in, c1.duration, 0}) { return false }
    if !plan_push(out, Exec_Op{3, .Source_Video, 0, 0, c2.asset_id, Time{}, Time{}, 0}) { return false }
    if !plan_push(out, Exec_Op{4, .Trim_Video, 3, 0, c2.id, c2.source_in, c2.duration, 0}) { return false }
    if target.supports_transition {
        if !plan_push(out, Exec_Op{5, .Transition_Video, 2, 4, s.transition.id, c2.timeline_start, s.transition.duration, 0}) { return false }
    } else {
        out.loss = .Baked_Loss_Of_Editability
        if !plan_push(out, Exec_Op{5, .Composite_Baked, 2, 4, s.transition.id, c2.timeline_start, s.transition.duration, 0}) { return false }
    }
    if !plan_push(out, Exec_Op{6, .Source_Audio, 0, 0, ca.asset_id, Time{}, Time{}, 0}) { return false }
    if !plan_push(out, Exec_Op{7, .Trim_Audio, 6, 0, ca.id, ca.source_in, ca.duration, 0}) { return false }
    if !plan_push(out, Exec_Op{8, .Gain_Audio, 7, 0, ca.id, Time{}, Time{}, 0}) { return false }
    if !plan_push(out, Exec_Op{9, .Encode_Video, 5, 0, 0, Time{}, Time{}, 0}) { return false }
    if !plan_push(out, Exec_Op{10, .Encode_Audio, 8, 0, 0, Time{}, Time{}, 0}) { return false }
    if !plan_push(out, Exec_Op{11, .Mux, 9, 10, 0, Time{}, Time{}, 0}) { return false }
    return true
}

plan_hash :: proc(p: ^Exec_Plan) -> u64 {
    if p == nil || p.count <= 0 { return 0 }
    h := FNV_OFFSET
    h = hash_u64(h, u64(p.loss))
    h = hash_i64(h, p.width)
    h = hash_i64(h, p.height)
    h = hash_i64(h, p.rate_num)
    h = hash_i64(h, p.rate_den)
    h = hash_i64(h, p.color)
    h = hash_u64(h, u64(p.count))
    for i in 0..<p.count {
        op := p.ops[i]
        h = hash_u64(h, u64(op.id))
        h = hash_u64(h, u64(op.kind))
        h = hash_u64(h, u64(op.input_a))
        h = hash_u64(h, u64(op.input_b))
        h = hash_u64(h, u64(op.source))
        if op.start.scale > 0 { h = hash_time(h, op.start) }
        if op.duration.scale > 0 { h = hash_time(h, op.duration) }
        h = hash_i64(h, op.scalar)
    }
    return h
}

// BEGIN_TYPED_EDITORIAL

Typed_Asset :: struct {
    id:       u32,
    kind:     Media_Kind,
    duration: Time,
}

Typed_Clip :: struct {
    id:             u32,
    asset_id:       u32,
    kind:           Media_Kind,
    timeline_start: Time,
    source_in:      Time,
    duration:       Time,
}

Typed_Transition :: struct {
    id:         u32,
    left_clip:  u32,
    right_clip: u32,
    duration:   Time,
}

Typed_Output :: struct {
    width:    i64,
    height:   i64,
    rate_num: i64,
    rate_den: i64,
    color:    i64,
}

Typed_Project :: struct {
    assets:      [MAX_ASSETS]Typed_Asset,
    asset_count: int,
    clips:       [MAX_CLIPS]Typed_Clip,
    clip_count:  int,
    transition:  Typed_Transition,
    output:      Typed_Output,
}

build_typed :: proc() -> Typed_Project {
    p: Typed_Project
    p.assets[0] = Typed_Asset{1, .Video, Time{20,1}}
    p.assets[1] = Typed_Asset{2, .Video, Time{20,1}}
    p.assets[2] = Typed_Asset{3, .Audio, Time{60,1}}
    p.asset_count = 3

    p.clips[0] = Typed_Clip{101, 1, .Video, Time{0,1}, Time{0,1}, Time{5,1}}
    p.clips[1] = Typed_Clip{102, 2, .Video, Time{11499,2500}, Time{2,1}, Time{5,1}}
    p.clips[2] = Typed_Clip{201, 3, .Audio, Time{0,1}, Time{0,1}, Time{23999,2500}}
    p.clip_count = 3

    p.transition = Typed_Transition{301, 101, 102, Time{1001,2500}}
    p.output = Typed_Output{1920, 1080, 30000, 1001, 1}
    return p
}

typed_to_snapshot :: proc(p: ^Typed_Project, out: ^Snapshot) -> bool {
    if p == nil || out == nil || p.asset_count < 0 || p.asset_count > MAX_ASSETS || p.clip_count < 0 || p.clip_count > MAX_CLIPS {
        return false
    }
    out^ = Snapshot{}
    out.asset_count = p.asset_count
    out.clip_count = p.clip_count
    for i in 0..<p.asset_count {
        a := p.assets[i]
        out.assets[i] = Snap_Asset{a.id, a.kind, a.duration}
    }
    for i in 0..<p.clip_count {
        c := p.clips[i]
        out.clips[i] = Snap_Clip{c.id, c.asset_id, c.kind, c.timeline_start, c.source_in, c.duration}
    }
    out.transition = Snap_Transition{p.transition.id, p.transition.left_clip, p.transition.right_clip, p.transition.duration}
    out.output = Snap_Output{p.output.width, p.output.height, p.output.rate_num, p.output.rate_den, p.output.color}
    return true
}

verify_typed :: proc(p: ^Typed_Project) -> bool {
    s: Snapshot
    return typed_to_snapshot(p, &s) && verify_snapshot(&s)
}

// END_TYPED_EDITORIAL

// BEGIN_GENERIC_EDITORIAL

Generic_Kind :: enum u8 {
    Asset,
    Clip,
    Transition,
    Output,
}

Attr_Key :: enum u8 {
    Media_Kind,
    Duration,
    Asset_Ref,
    Timeline_Start,
    Source_In,
    Left_Clip,
    Right_Clip,
    Width,
    Height,
    Rate_Num,
    Rate_Den,
    Color,
}

Attr :: struct {
    key:    Attr_Key,
    scalar: i64,
    time:   Time,
}

Generic_Op :: struct {
    id:         u32,
    kind:       Generic_Kind,
    attrs:      [MAX_ATTRS]Attr,
    attr_count: int,
}

Generic_Project :: struct {
    ops:      [MAX_OPS]Generic_Op,
    op_count: int,
}

push_scalar :: proc(op: ^Generic_Op, key: Attr_Key, value: i64) -> bool {
    if op == nil || op.attr_count >= MAX_ATTRS { return false }
    op.attrs[op.attr_count] = Attr{key, value, Time{}}
    op.attr_count += 1
    return true
}

push_time :: proc(op: ^Generic_Op, key: Attr_Key, value: Time) -> bool {
    if op == nil || op.attr_count >= MAX_ATTRS { return false }
    op.attrs[op.attr_count] = Attr{key, 0, value}
    op.attr_count += 1
    return true
}

find_attr :: proc(op: ^Generic_Op, key: Attr_Key) -> ^Attr {
    if op == nil { return nil }
    for i in 0..<op.attr_count {
        if op.attrs[i].key == key { return &op.attrs[i] }
    }
    return nil
}

append_generic :: proc(p: ^Generic_Project, op: Generic_Op) -> bool {
    if p == nil || p.op_count >= MAX_OPS { return false }
    p.ops[p.op_count] = op
    p.op_count += 1
    return true
}

build_generic :: proc() -> Generic_Project {
    p: Generic_Project

    a1 := Generic_Op{id=1, kind=.Asset}
    push_scalar(&a1, .Media_Kind, i64(Media_Kind.Video))
    push_time(&a1, .Duration, Time{20,1})
    append_generic(&p, a1)

    a2 := Generic_Op{id=2, kind=.Asset}
    push_scalar(&a2, .Media_Kind, i64(Media_Kind.Video))
    push_time(&a2, .Duration, Time{20,1})
    append_generic(&p, a2)

    a3 := Generic_Op{id=3, kind=.Asset}
    push_scalar(&a3, .Media_Kind, i64(Media_Kind.Audio))
    push_time(&a3, .Duration, Time{60,1})
    append_generic(&p, a3)

    c1 := Generic_Op{id=101, kind=.Clip}
    push_scalar(&c1, .Media_Kind, i64(Media_Kind.Video))
    push_scalar(&c1, .Asset_Ref, 1)
    push_time(&c1, .Timeline_Start, Time{0,1})
    push_time(&c1, .Source_In, Time{0,1})
    push_time(&c1, .Duration, Time{5,1})
    append_generic(&p, c1)

    c2 := Generic_Op{id=102, kind=.Clip}
    push_scalar(&c2, .Media_Kind, i64(Media_Kind.Video))
    push_scalar(&c2, .Asset_Ref, 2)
    push_time(&c2, .Timeline_Start, Time{11499,2500})
    push_time(&c2, .Source_In, Time{2,1})
    push_time(&c2, .Duration, Time{5,1})
    append_generic(&p, c2)

    ca := Generic_Op{id=201, kind=.Clip}
    push_scalar(&ca, .Media_Kind, i64(Media_Kind.Audio))
    push_scalar(&ca, .Asset_Ref, 3)
    push_time(&ca, .Timeline_Start, Time{0,1})
    push_time(&ca, .Source_In, Time{0,1})
    push_time(&ca, .Duration, Time{23999,2500})
    append_generic(&p, ca)

    tr := Generic_Op{id=301, kind=.Transition}
    push_scalar(&tr, .Left_Clip, 101)
    push_scalar(&tr, .Right_Clip, 102)
    push_time(&tr, .Duration, Time{1001,2500})
    append_generic(&p, tr)

    output := Generic_Op{id=401, kind=.Output}
    push_scalar(&output, .Width, 1920)
    push_scalar(&output, .Height, 1080)
    push_scalar(&output, .Rate_Num, 30000)
    push_scalar(&output, .Rate_Den, 1001)
    push_scalar(&output, .Color, 1)
    append_generic(&p, output)

    return p
}

generic_to_snapshot :: proc(p: ^Generic_Project, out: ^Snapshot) -> bool {
    if p == nil || out == nil || p.op_count <= 0 || p.op_count > MAX_OPS { return false }
    out^ = Snapshot{}
    transition_seen := false
    output_seen := false

    for i in 0..<p.op_count {
        op := &p.ops[i]
        switch op.kind {
        case .Asset:
            mk := find_attr(op, .Media_Kind)
            dur := find_attr(op, .Duration)
            if mk == nil || dur == nil || out.asset_count >= MAX_ASSETS || op.id == 0 { return false }
            if mk.scalar < 0 || mk.scalar > i64(Media_Kind.Audio) { return false }
            out.assets[out.asset_count] = Snap_Asset{op.id, Media_Kind(mk.scalar), dur.time}
            out.asset_count += 1

        case .Clip:
            mk := find_attr(op, .Media_Kind)
            asset := find_attr(op, .Asset_Ref)
            start := find_attr(op, .Timeline_Start)
            source := find_attr(op, .Source_In)
            dur := find_attr(op, .Duration)
            if mk == nil || asset == nil || start == nil || source == nil || dur == nil || out.clip_count >= MAX_CLIPS || op.id == 0 { return false }
            if mk.scalar < 0 || mk.scalar > i64(Media_Kind.Audio) || asset.scalar <= 0 { return false }
            out.clips[out.clip_count] = Snap_Clip{op.id, u32(asset.scalar), Media_Kind(mk.scalar), start.time, source.time, dur.time}
            out.clip_count += 1

        case .Transition:
            if transition_seen { return false }
            left := find_attr(op, .Left_Clip)
            right := find_attr(op, .Right_Clip)
            dur := find_attr(op, .Duration)
            if left == nil || right == nil || dur == nil || op.id == 0 || left.scalar <= 0 || right.scalar <= 0 { return false }
            out.transition = Snap_Transition{op.id, u32(left.scalar), u32(right.scalar), dur.time}
            transition_seen = true

        case .Output:
            if output_seen { return false }
            width := find_attr(op, .Width)
            height := find_attr(op, .Height)
            rn := find_attr(op, .Rate_Num)
            rd := find_attr(op, .Rate_Den)
            color := find_attr(op, .Color)
            if width == nil || height == nil || rn == nil || rd == nil || color == nil { return false }
            out.output = Snap_Output{width.scalar, height.scalar, rn.scalar, rd.scalar, color.scalar}
            output_seen = true
        }
    }
    return transition_seen && output_seen
}

verify_generic :: proc(p: ^Generic_Project) -> bool {
    s: Snapshot
    return generic_to_snapshot(p, &s) && verify_snapshot(&s)
}

remove_attr :: proc(op: ^Generic_Op, key: Attr_Key) -> bool {
    if op == nil { return false }
    for i in 0..<op.attr_count {
        if op.attrs[i].key == key {
            for j in i..<op.attr_count-1 {
                op.attrs[j] = op.attrs[j+1]
            }
            op.attr_count -= 1
            return true
        }
    }
    return false
}

find_generic_op :: proc(p: ^Generic_Project, id: u32) -> ^Generic_Op {
    if p == nil { return nil }
    for i in 0..<p.op_count {
        if p.ops[i].id == id { return &p.ops[i] }
    }
    return nil
}

// END_GENERIC_EDITORIAL

bool_i :: proc(v: bool) -> int {
    if v { return 1 }
    return 0
}

main :: proc() {
    typed := build_typed()
    generic := build_generic()

    ts, gs: Snapshot
    typed_projection := typed_to_snapshot(&typed, &ts)
    generic_projection := generic_to_snapshot(&generic, &gs)
    typed_valid := typed_projection && verify_snapshot(&ts)
    generic_valid := generic_projection && verify_snapshot(&gs)

    typed_sem := snapshot_hash(&ts)
    generic_sem := snapshot_hash(&gs)

    tfull, gfull, tfallback, gfallback: Exec_Plan
    typed_full_ok := typed_valid && lower_snapshot(&ts, Target{true}, &tfull)
    generic_full_ok := generic_valid && lower_snapshot(&gs, Target{true}, &gfull)
    typed_fallback_ok := typed_valid && lower_snapshot(&ts, Target{false}, &tfallback)
    generic_fallback_ok := generic_valid && lower_snapshot(&gs, Target{false}, &gfallback)

    fmt.printf("RESULT typed_valid=%d generic_valid=%d typed_sem=%d generic_sem=%d typed_full_ok=%d generic_full_ok=%d typed_full_hash=%d generic_full_hash=%d typed_full_loss=%d generic_full_loss=%d typed_fallback_ok=%d generic_fallback_ok=%d typed_fallback_hash=%d generic_fallback_hash=%d typed_fallback_loss=%d generic_fallback_loss=%d exec_nodes_full=%d exec_nodes_fallback=%d\n",
        bool_i(typed_valid), bool_i(generic_valid), typed_sem, generic_sem,
        bool_i(typed_full_ok), bool_i(generic_full_ok), plan_hash(&tfull), plan_hash(&gfull), int(tfull.loss), int(gfull.loss),
        bool_i(typed_fallback_ok), bool_i(generic_fallback_ok), plan_hash(&tfallback), plan_hash(&gfallback), int(tfallback.loss), int(gfallback.loss),
        tfull.count, tfallback.count)

    typed_oob := typed
    typed_oob.clips[0].duration = Time{25,1}
    generic_oob := generic
    gop := find_generic_op(&generic_oob, 101)
    if gop != nil {
        a := find_attr(gop, .Duration)
        if a != nil { a.time = Time{25,1} }
    }

    typed_transition := typed
    typed_transition.transition.duration = Time{6,1}
    generic_transition := generic
    gtr := find_generic_op(&generic_transition, 301)
    if gtr != nil {
        a := find_attr(gtr, .Duration)
        if a != nil { a.time = Time{6,1} }
    }

    generic_missing := generic
    gm := find_generic_op(&generic_missing, 102)
    missing_removed := false
    if gm != nil { missing_removed = remove_attr(gm, .Duration) }

    fmt.printf("NEGATIVE typed_oob_rejected=%d generic_oob_rejected=%d typed_transition_rejected=%d generic_transition_rejected=%d generic_missing_removed=%d generic_missing_rejected=%d typed_missing_attr_structurally_impossible=1\n",
        bool_i(!verify_typed(&typed_oob)), bool_i(!verify_generic(&generic_oob)),
        bool_i(!verify_typed(&typed_transition)), bool_i(!verify_generic(&generic_transition)),
        bool_i(missing_removed), bool_i(!verify_generic(&generic_missing)))
}
