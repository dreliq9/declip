package main

import "core:fmt"

emit_byte :: proc(buf: ^[]u8, b: u8) {
    append(buf, b)
}

emit_be16 :: proc(buf: ^[]u8, v: u16) {
    emit_byte(buf, u8(v >> 8))
    emit_byte(buf, u8(v))
}

emit_be32 :: proc(buf: ^[]u8, v: u32) {
    emit_byte(buf, u8(v >> 24))
    emit_byte(buf, u8(v >> 16))
    emit_byte(buf, u8(v >> 8))
    emit_byte(buf, u8(v))
}

emit_be64 :: proc(buf: ^[]u8, v: u64) {
    emit_byte(buf, u8(v >> 56))
    emit_byte(buf, u8(v >> 48))
    emit_byte(buf, u8(v >> 40))
    emit_byte(buf, u8(v >> 32))
    emit_byte(buf, u8(v >> 24))
    emit_byte(buf, u8(v >> 16))
    emit_byte(buf, u8(v >> 8))
    emit_byte(buf, u8(v))
}

emit_head :: proc(buf: ^[]u8, major: u8, n: u64) {
    prefix := major << 5
    if n < 24 {
        emit_byte(buf, prefix | u8(n))
    } else if n <= 0xff {
        emit_byte(buf, prefix | 24)
        emit_byte(buf, u8(n))
    } else if n <= 0xffff {
        emit_byte(buf, prefix | 25)
        emit_be16(buf, u16(n))
    } else if n <= 0xffffffff {
        emit_byte(buf, prefix | 26)
        emit_be32(buf, u32(n))
    } else {
        emit_byte(buf, prefix | 27)
        emit_be64(buf, n)
    }
}

emit_int :: proc(buf: ^[]u8, value: i64) {
    if value >= 0 {
        emit_head(buf, 0, u64(value))
    } else {
        emit_head(buf, 1, u64(-1 - value))
    }
}

emit_bytes :: proc(buf: ^[]u8, data: []u8) {
    emit_head(buf, 2, u64(len(data)))
    for b in data {
        emit_byte(buf, b)
    }
}

emit_text :: proc(buf: ^[]u8, s: string) {
    emit_head(buf, 3, u64(len(s)))
    for i in 0..<len(s) {
        emit_byte(buf, s[i])
    }
}

emit_array :: proc(buf: ^[]u8, count: u64) { emit_head(buf, 4, count) }
emit_map :: proc(buf: ^[]u8, count: u64) { emit_head(buf, 5, count) }
emit_key :: proc(buf: ^[]u8, key: u64) { emit_head(buf, 0, key) }

emit_time :: proc(buf: ^[]u8, value, scale: i64) {
    emit_array(buf, 2)
    emit_int(buf, value)
    emit_int(buf, scale)
}

id_from :: proc(start: u8) -> [16]u8 {
    out: [16]u8
    for i in 0..<16 {
        out[i] = start + u8(i)
    }
    return out
}

emit_id :: proc(buf: ^[]u8, id: ^[16]u8) {
    emit_bytes(buf, id[:])
}

emit_clip_a :: proc(buf: ^[]u8) {
    clip_id := id_from(0x10)
    asset_id := id_from(0x30)
    emit_map(buf, 8)
    emit_key(buf, 0); emit_text(buf, "media.editorial.clip")
    emit_key(buf, 1); emit_int(buf, 1)
    emit_key(buf, 2); emit_id(buf, &clip_id)
    emit_key(buf, 3); emit_id(buf, &asset_id)
    emit_key(buf, 4); emit_time(buf, 0, 1)
    emit_key(buf, 5); emit_time(buf, 0, 1)
    emit_key(buf, 6); emit_time(buf, 5, 1)
    emit_key(buf, 99); emit_text(buf, "future-a")
}

emit_clip_b :: proc(buf: ^[]u8) {
    clip_id := id_from(0x20)
    asset_id := id_from(0x40)
    emit_map(buf, 8)
    emit_key(buf, 0); emit_text(buf, "media.editorial.clip")
    emit_key(buf, 1); emit_int(buf, 1)
    emit_key(buf, 2); emit_id(buf, &clip_id)
    emit_key(buf, 3); emit_id(buf, &asset_id)
    emit_key(buf, 4); emit_time(buf, 11499, 2500)
    emit_key(buf, 5); emit_time(buf, 2, 1)
    emit_key(buf, 6); emit_time(buf, 5, 1)
    emit_key(buf, 99); emit_text(buf, "future-b")
}

main :: proc() {
    buf := make([]u8, 0, 512)
    defer delete(buf)

    project_id := id_from(0x00)

    emit_map(&buf, 4)
    emit_key(&buf, 0); emit_text(&buf, "media.state.snapshot")
    emit_key(&buf, 1); emit_int(&buf, 1)
    emit_key(&buf, 2); emit_id(&buf, &project_id)
    emit_key(&buf, 3)
    emit_array(&buf, 2)
    // Object-table ordering is by 16-byte ObjectId, so clip A precedes clip B.
    emit_clip_a(&buf)
    emit_clip_b(&buf)

    fmt.print("ODIN_HEX ")
    for b in buf {
        fmt.printf("%02x", b)
    }
    fmt.println()
}
