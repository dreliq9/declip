package main

import "core:fmt"
import "core:os"
import hk "../../src/core"
import serial "../../src/serialization"
import state "../../src/state"

fail :: proc(message: string) {
    fmt.eprintln("FAIL", message)
    os.exit(1)
}

require :: proc(condition: bool, message: string) {
    if !condition { fail(message) }
}

main :: proc() {
    half, status := hk.media_time_make(2, 4)
    require(status == .Ok, "normalize status")
    require(half.value == 1 && half.scale == 2, "2/4 must normalize to 1/2")

    a, _ := hk.media_time_make(1001, 30000)
    b, _ := hk.media_time_make(1, 48000)
    sum, add_status := hk.media_time_add(a, b)
    require(add_status == .Ok, "exact add status")
    require(sum.value == 2671 && sum.scale == 80000, "mixed-grid exact addition")

    ticks, tick_status := hk.media_time_ticks_exact(half, 48000)
    require(tick_status == .Ok && ticks == 24000, "exact tick conversion")

    third, _ := hk.media_time_make(1, 3)
    _, inexact_status := hk.media_time_ticks_exact(third, 10)
    require(inexact_status == .Inexact, "inexact tick conversion must fail closed")

    r, range_status := hk.time_range_make(hk.Media_Time{0, 1}, hk.Media_Time{1, 1})
    require(range_status == .Ok, "range construction")
    inside, _ := hk.time_range_contains(r, hk.Media_Time{999, 1000})
    at_end, _ := hk.time_range_contains(r, hk.Media_Time{1, 1})
    require(inside && !at_end, "ranges must be half-open")

    buf, buf_status := serial.new_buffer(64)
    require(buf_status == .Ok, "CBOR buffer allocation")
    defer delete(buf)

    require(serial.emit_record_header(&buf, 3, "heimdall.test", 1) == .Ok, "record header")
    require(serial.emit_uint(&buf, 2) == .Ok, "record field key")
    require(serial.emit_media_time(&buf, sum.value, sum.scale) == .Ok, "MediaTime canonical encoding")

    expected := [28]u8{
        0xa3, 0x00, 0x6d, 0x68, 0x65, 0x69, 0x6d, 0x64,
        0x61, 0x6c, 0x6c, 0x2e, 0x74, 0x65, 0x73, 0x74,
        0x01, 0x01, 0x02, 0x82, 0x19, 0x0a, 0x6f, 0x1a,
        0x00, 0x01, 0x38, 0x80,
    }
    require(len(buf) == len(expected), "canonical CBOR byte length")
    for value, index in buf {
        if value != expected[index] { fail("canonical CBOR bytes differ") }
    }

    require(state.id128_is_zero(state.Id128{}), "zero durable ID sentinel")
    require(state.hash256_is_zero(state.Hash256{}), "zero hash sentinel")

    fmt.println("HEIMDALL_FOUNDATION_CONFORMANCE_PASS")
}
