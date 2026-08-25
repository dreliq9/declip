package heimdall_serialization

Canonical_Status :: enum i32 { Ok = 0, Invalid = 1, Overflow = 2 }

append_byte :: proc(buf: ^[dynamic]u8, value: u8) -> Canonical_Status {
    _, err := append(buf, value)
    if err != nil { return .Overflow }
    return .Ok
}
append_bytes :: proc(buf: ^[dynamic]u8, values: []u8) -> Canonical_Status {
    for value in values { if append_byte(buf, value) != .Ok { return .Overflow } }
    return .Ok
}
emit_major_value :: proc(buf: ^[dynamic]u8, major: u8, value: u64) -> Canonical_Status {
    prefix := major << 5
    if value < 24 { return append_byte(buf, prefix | u8(value)) }
    if value <= 0xff {
        if append_byte(buf, prefix | 24) != .Ok { return .Overflow }
        return append_byte(buf, u8(value))
    }
    if value <= 0xffff {
        if append_byte(buf, prefix | 25) != .Ok { return .Overflow }
        if append_byte(buf, u8(value >> 8)) != .Ok { return .Overflow }
        return append_byte(buf, u8(value))
    }
    if value <= 0xffff_ffff {
        if append_byte(buf, prefix | 26) != .Ok { return .Overflow }
        for shift in [4]u64{24,16,8,0} { if append_byte(buf, u8(value >> shift)) != .Ok { return .Overflow } }
        return .Ok
    }
    if append_byte(buf, prefix | 27) != .Ok { return .Overflow }
    for shift in [8]u64{56,48,40,32,24,16,8,0} { if append_byte(buf, u8(value >> shift)) != .Ok { return .Overflow } }
    return .Ok
}
emit_uint :: proc(buf: ^[dynamic]u8, value: u64) -> Canonical_Status { return emit_major_value(buf, 0, value) }
emit_int :: proc(buf: ^[dynamic]u8, value: i64) -> Canonical_Status {
    if value >= 0 { return emit_uint(buf, u64(value)) }
    return emit_major_value(buf, 1, u64(-(i128(value)+1)))
}
emit_bytes :: proc(buf: ^[dynamic]u8, values: []u8) -> Canonical_Status {
    if emit_major_value(buf, 2, u64(len(values))) != .Ok { return .Overflow }
    return append_bytes(buf, values)
}
emit_text :: proc(buf: ^[dynamic]u8, value: string) -> Canonical_Status {
    if emit_major_value(buf, 3, u64(len(value))) != .Ok { return .Overflow }
    for b in transmute([]u8)value { if append_byte(buf, b) != .Ok { return .Overflow } }
    return .Ok
}
emit_array_header :: proc(buf: ^[dynamic]u8, count: u64) -> Canonical_Status { return emit_major_value(buf, 4, count) }
emit_map_header :: proc(buf: ^[dynamic]u8, count: u64) -> Canonical_Status { return emit_major_value(buf, 5, count) }
emit_bool :: proc(buf: ^[dynamic]u8, value: bool) -> Canonical_Status { if value { return append_byte(buf, 0xf5) }; return append_byte(buf, 0xf4) }
emit_null :: proc(buf: ^[dynamic]u8) -> Canonical_Status { return append_byte(buf, 0xf6) }
emit_id128 :: proc(buf: ^[dynamic]u8, high, low: u64) -> Canonical_Status {
    bytes: [16]u8
    for i in 0..<8 { shift := u64((7-i)*8); bytes[i] = u8(high >> shift); bytes[8+i] = u8(low >> shift) }
    return emit_bytes(buf, bytes[:])
}
emit_media_time :: proc(buf: ^[dynamic]u8, value, scale: i64) -> Canonical_Status {
    if scale <= 0 { return .Invalid }
    if emit_array_header(buf, 2) != .Ok { return .Overflow }
    if emit_int(buf, value) != .Ok { return .Overflow }
    return emit_int(buf, scale)
}
emit_record_header :: proc(buf: ^[dynamic]u8, field_count: u64, type_name: string, schema_version: u64) -> Canonical_Status {
    if field_count < 2 { return .Invalid }
    if emit_map_header(buf, field_count) != .Ok { return .Overflow }
    if emit_uint(buf, 0) != .Ok { return .Overflow }
    if emit_text(buf, type_name) != .Ok { return .Overflow }
    if emit_uint(buf, 1) != .Ok { return .Overflow }
    return emit_uint(buf, schema_version)
}
new_buffer :: proc(capacity: int = 256) -> ([dynamic]u8, Canonical_Status) {
    buf, err := make([dynamic]u8, 0, capacity)
    if err != nil { return {}, .Overflow }
    return buf, .Ok
}
