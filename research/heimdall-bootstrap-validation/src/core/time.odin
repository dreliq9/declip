package heimdall_core

Time_Status :: enum i32 {
    Ok       = 0,
    Invalid  = 1,
    Overflow = 2,
    Inexact  = 3,
}

Media_Time :: struct { value, scale: i64 }
Media_Rate :: struct { numerator, denominator: i64 }
Time_Range :: struct { start, duration: Media_Time }

I64_MIN_I128 :: i128(-9223372036854775808)
I64_MAX_I128 :: i128( 9223372036854775807)

gcd_u64 :: proc(a_in, b_in: u64) -> u64 {
    a := a_in; b := b_in
    for b != 0 { a, b = b, a % b }
    return a
}

normalize_wide :: proc(n_in, d_in: i128) -> (Media_Time, Time_Status) {
    if d_in <= 0 { return {}, .Invalid }
    if d_in > I64_MAX_I128 { return {}, .Overflow }
    if n_in == 0 { return Media_Time{0, 1}, .Ok }
    mag := n_in
    if mag < 0 { mag = -mag }
    g := gcd_u64(u64(mag % d_in), u64(d_in))
    n := n_in / i128(g)
    d := d_in / i128(g)
    if n < I64_MIN_I128 || n > I64_MAX_I128 || d <= 0 || d > I64_MAX_I128 { return {}, .Overflow }
    return Media_Time{i64(n), i64(d)}, .Ok
}

media_time_make :: proc(value, scale: i64) -> (Media_Time, Time_Status) {
    if scale <= 0 { return {}, .Invalid }
    return normalize_wide(i128(value), i128(scale))
}
media_time_normalize :: proc(input: Media_Time) -> (Media_Time, Time_Status) { return media_time_make(input.value, input.scale) }

media_time_add_internal :: proc(a, b: Media_Time, subtract: bool) -> (Media_Time, Time_Status) {
    na, sa := media_time_normalize(a); if sa != .Ok { return {}, sa }
    nb, sb := media_time_normalize(b); if sb != .Ok { return {}, sb }
    g := gcd_u64(u64(na.scale), u64(nb.scale))
    left_factor := nb.scale / i64(g); right_factor := na.scale / i64(g)
    left := i128(na.value) * i128(left_factor); right := i128(nb.value) * i128(right_factor)
    total := left + right; if subtract { total = left - right }
    mag := total; if mag < 0 { mag = -mag }
    g2 := gcd_u64(u64(mag % i128(g)), g)
    n := total / i128(g2)
    d := i128(na.scale / i64(g)) * i128(nb.scale / i64(g2))
    return normalize_wide(n, d)
}
media_time_add :: proc(a, b: Media_Time) -> (Media_Time, Time_Status) { return media_time_add_internal(a, b, false) }
media_time_sub :: proc(a, b: Media_Time) -> (Media_Time, Time_Status) { return media_time_add_internal(a, b, true) }

media_time_compare :: proc(a, b: Media_Time) -> (i32, Time_Status) {
    na, sa := media_time_normalize(a); if sa != .Ok { return 0, sa }
    nb, sb := media_time_normalize(b); if sb != .Ok { return 0, sb }
    left := i128(na.value) * i128(nb.scale); right := i128(nb.value) * i128(na.scale)
    if left < right { return -1, .Ok }
    if left > right { return 1, .Ok }
    return 0, .Ok
}

media_time_ticks_exact :: proc(input: Media_Time, target_scale: i64) -> (i64, Time_Status) {
    if target_scale <= 0 { return 0, .Invalid }
    n, status := media_time_normalize(input); if status != .Ok { return 0, status }
    product := i128(n.value) * i128(target_scale); divisor := i128(n.scale)
    if product % divisor != 0 { return 0, .Inexact }
    ticks := product / divisor
    if ticks < I64_MIN_I128 || ticks > I64_MAX_I128 { return 0, .Overflow }
    return i64(ticks), .Ok
}

media_time_from_rate_index :: proc(index: i64, rate: Media_Rate) -> (Media_Time, Time_Status) {
    if rate.numerator <= 0 || rate.denominator <= 0 { return {}, .Invalid }
    return normalize_wide(i128(index) * i128(rate.denominator), i128(rate.numerator))
}

time_range_make :: proc(start, duration: Media_Time) -> (Time_Range, Time_Status) {
    ns, ss := media_time_normalize(start); if ss != .Ok { return {}, ss }
    nd, sd := media_time_normalize(duration); if sd != .Ok { return {}, sd }
    if nd.value < 0 { return {}, .Invalid }
    return Time_Range{ns, nd}, .Ok
}
time_range_end :: proc(r: Time_Range) -> (Media_Time, Time_Status) {
    nr, status := time_range_make(r.start, r.duration); if status != .Ok { return {}, status }
    return media_time_add(nr.start, nr.duration)
}
time_range_contains :: proc(r: Time_Range, t: Media_Time) -> (bool, Time_Status) {
    nr, rs := time_range_make(r.start, r.duration); if rs != .Ok { return false, rs }
    nt, ts := media_time_normalize(t); if ts != .Ok { return false, ts }
    if nr.duration.value == 0 { return false, .Ok }
    end, es := time_range_end(nr); if es != .Ok { return false, es }
    cmp_start, cs := media_time_compare(nt, nr.start); if cs != .Ok { return false, cs }
    cmp_end, ce := media_time_compare(nt, end); if ce != .Ok { return false, ce }
    return cmp_start >= 0 && cmp_end < 0, .Ok
}
