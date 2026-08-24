package exact_time

import "base:runtime"
import c "core:c"

MK_TIME_OK       :: c.int(0)
MK_TIME_INVALID  :: c.int(1)
MK_TIME_OVERFLOW :: c.int(2)
MK_TIME_INEXACT  :: c.int(3)

I64_MIN_I128 :: i128(-9223372036854775808)
I64_MAX_I128 :: i128( 9223372036854775807)

Media_Time :: struct {
    value: i64,
    scale: i64,
}

gcd_u64 :: proc(a_in, b_in: u64) -> u64 {
    a := a_in
    b := b_in
    for b != 0 {
        a, b = b, a % b
    }
    return a
}

normalize_wide :: proc(n_in, d_in: i128, out: ^Media_Time) -> c.int {
    if out == nil || d_in <= 0 {
        return MK_TIME_INVALID
    }
    if d_in > I64_MAX_I128 {
        return MK_TIME_OVERFLOW
    }
    if n_in == 0 {
        out^ = Media_Time{0, 1}
        return MK_TIME_OK
    }

    mag := n_in
    if mag < 0 {
        mag = -mag
    }
    d_u64 := u64(d_in)
    rem := u64(mag % d_in)
    g := gcd_u64(rem, d_u64)
    n := n_in / i128(g)
    d := d_in / i128(g)

    if n < I64_MIN_I128 || n > I64_MAX_I128 || d <= 0 || d > I64_MAX_I128 {
        return MK_TIME_OVERFLOW
    }
    out^ = Media_Time{i64(n), i64(d)}
    return MK_TIME_OK
}

normalize :: proc(input: Media_Time, out: ^Media_Time) -> c.int {
    if input.scale <= 0 {
        return MK_TIME_INVALID
    }
    return normalize_wide(i128(input.value), i128(input.scale), out)
}

add_internal :: proc(a, b: Media_Time, subtract: bool, out: ^Media_Time) -> c.int {
    if out == nil {
        return MK_TIME_INVALID
    }
    na, nb: Media_Time
    sa := normalize(a, &na)
    if sa != MK_TIME_OK {
        return sa
    }
    sb := normalize(b, &nb)
    if sb != MK_TIME_OK {
        return sb
    }

    g := gcd_u64(u64(na.scale), u64(nb.scale))
    left_factor  := nb.scale / i64(g)
    right_factor := na.scale / i64(g)

    left  := i128(na.value) * i128(left_factor)
    right := i128(nb.value) * i128(right_factor)
    t := left + right
    if subtract {
        t = left - right
    }

    mag := t
    if mag < 0 {
        mag = -mag
    }
    rem := u64(mag % i128(g))
    g2 := gcd_u64(rem, g)

    n := t / i128(g2)
    d := i128(na.scale / i64(g)) * i128(nb.scale / i64(g2))
    return normalize_wide(n, d, out)
}

compare_internal :: proc(a, b: Media_Time, out_cmp: ^i32) -> c.int {
    if out_cmp == nil {
        return MK_TIME_INVALID
    }
    na, nb: Media_Time
    sa := normalize(a, &na)
    if sa != MK_TIME_OK {
        return sa
    }
    sb := normalize(b, &nb)
    if sb != MK_TIME_OK {
        return sb
    }
    left  := i128(na.value) * i128(nb.scale)
    right := i128(nb.value) * i128(na.scale)
    if left < right {
        out_cmp^ = -1
    } else if left > right {
        out_cmp^ = 1
    } else {
        out_cmp^ = 0
    }
    return MK_TIME_OK
}

@(export, link_name="mk_time_make")
mk_time_make :: proc "c" (value, scale: i64, out: ^Media_Time) -> c.int {
    context = runtime.default_context()
    if scale <= 0 {
        return MK_TIME_INVALID
    }
    return normalize_wide(i128(value), i128(scale), out)
}

@(export, link_name="mk_time_add")
mk_time_add :: proc "c" (a, b: Media_Time, out: ^Media_Time) -> c.int {
    context = runtime.default_context()
    return add_internal(a, b, false, out)
}

@(export, link_name="mk_time_sub")
mk_time_sub :: proc "c" (a, b: Media_Time, out: ^Media_Time) -> c.int {
    context = runtime.default_context()
    return add_internal(a, b, true, out)
}

@(export, link_name="mk_time_compare")
mk_time_compare :: proc "c" (a, b: Media_Time, out_cmp: ^i32) -> c.int {
    context = runtime.default_context()
    return compare_internal(a, b, out_cmp)
}

@(export, link_name="mk_time_ticks_exact")
mk_time_ticks_exact :: proc "c" (input: Media_Time, target_scale: i64, out_ticks: ^i64) -> c.int {
    context = runtime.default_context()
    if out_ticks == nil || target_scale <= 0 {
        return MK_TIME_INVALID
    }
    n: Media_Time
    status := normalize(input, &n)
    if status != MK_TIME_OK {
        return status
    }
    product := i128(n.value) * i128(target_scale)
    divisor := i128(n.scale)
    if product % divisor != 0 {
        return MK_TIME_INEXACT
    }
    ticks := product / divisor
    if ticks < I64_MIN_I128 || ticks > I64_MAX_I128 {
        return MK_TIME_OVERFLOW
    }
    out_ticks^ = i64(ticks)
    return MK_TIME_OK
}

@(export, link_name="mk_time_from_rate_index")
mk_time_from_rate_index :: proc "c" (
    index, rate_num, rate_den: i64,
    out: ^Media_Time,
) -> c.int {
    context = runtime.default_context()
    if out == nil || rate_num <= 0 || rate_den <= 0 {
        return MK_TIME_INVALID
    }
    n := i128(index) * i128(rate_den)
    return normalize_wide(n, i128(rate_num), out)
}

@(export, link_name="mk_time_range_end")
mk_time_range_end :: proc "c" (start, duration: Media_Time, out_end: ^Media_Time) -> c.int {
    context = runtime.default_context()
    if out_end == nil {
        return MK_TIME_INVALID
    }
    nd: Media_Time
    status := normalize(duration, &nd)
    if status != MK_TIME_OK {
        return status
    }
    if nd.value < 0 {
        return MK_TIME_INVALID
    }
    return add_internal(start, nd, false, out_end)
}

@(export, link_name="mk_time_range_contains")
mk_time_range_contains :: proc "c" (
    start, duration, t: Media_Time,
    out_contains: ^i32,
) -> c.int {
    context = runtime.default_context()
    if out_contains == nil {
        return MK_TIME_INVALID
    }
    ns, nd, nt: Media_Time
    status := normalize(start, &ns)
    if status != MK_TIME_OK { return status }
    status = normalize(duration, &nd)
    if status != MK_TIME_OK { return status }
    status = normalize(t, &nt)
    if status != MK_TIME_OK { return status }
    if nd.value < 0 {
        return MK_TIME_INVALID
    }
    if nd.value == 0 {
        out_contains^ = 0
        return MK_TIME_OK
    }
    end: Media_Time
    status = add_internal(ns, nd, false, &end)
    if status != MK_TIME_OK {
        return status
    }
    cmp_start, cmp_end: i32
    status = compare_internal(nt, ns, &cmp_start)
    if status != MK_TIME_OK { return status }
    status = compare_internal(nt, end, &cmp_end)
    if status != MK_TIME_OK { return status }
    out_contains^ = 0
    if cmp_start >= 0 && cmp_end < 0 {
        out_contains^ = 1
    }
    return MK_TIME_OK
}
