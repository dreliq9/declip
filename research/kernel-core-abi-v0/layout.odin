package main

import "core:fmt"

Abi_Version :: struct {
    major: u16,
    minor: u16,
    reserved: u32,
}

Struct_Header :: struct {
    struct_size: u32,
    type_version: u16,
    flags: u16,
}

Id128 :: struct { high, low: u64 }
Content_Hash :: struct { algorithm, byte_count: u32, bytes: [32]u8 }
Media_Time :: struct { value, scale: i64 }
Media_Rate :: struct { numerator, denominator: i64 }
Time_Range :: struct { start, duration: Media_Time }
Wall_Time :: struct { unix_seconds: i64, nanoseconds, flags: u32 }
Decimal64 :: struct { coefficient: i64, exponent10: i32, flags: u32 }
Money :: struct { amount: Decimal64, currency: [4]u8, reserved: u32 }
Bytes_View :: struct { data: rawptr, size: u64 }
String_View :: struct { data: rawptr, size: u64 }
Resource_Handle :: struct { store: u64, slot, generation: u32 }

Extension :: struct {
    header: Struct_Header,
    type_name: String_View,
    extension_version: u32,
    extension_flags: u32,
    payload: Bytes_View,
}
Extension_View :: struct { data: rawptr, count: u64 }

Object_Ref :: struct {
    header: Struct_Header,
    object_type: String_View,
    object_id: Id128,
    version_id: Id128,
    content_hash: Content_Hash,
    ref_flags: u32,
    reserved: u32,
    extensions: Extension_View,
}
Object_Ref_View :: struct { data: rawptr, count: u64 }

Color_Descriptor :: struct {
    primaries: u32,
    transfer: u32,
    matrix_coefficients: u32,
    color_range: u32,
    chroma_location: u32,
    alpha_mode: u32,
    bit_depth: u32,
    flags: u32,
}

Media_Type :: struct {
    header: Struct_Header,
    kind: u32,
    media_flags: u32,
    format_name: String_View,
    width, height: u32,
    color: Color_Descriptor,
    sample_rate, channel_count: u32,
    sample_format_name: String_View,
    channel_layout_name: String_View,
    extensions: Extension_View,
}

Stream_Descriptor :: struct {
    header: Struct_Header,
    stream_id: Id128,
    media_type: Media_Type,
    nominal_rate: Media_Rate,
    time_domain: u32,
    stream_flags: u32,
    extensions: Extension_View,
}

Resource_Budget :: struct {
    header: Struct_Header,
    valid_fields: u64,
    wall_time_ns, cpu_time_ns, gpu_time_ns: u64,
    ram_bytes, vram_bytes, storage_bytes, network_bytes: u64,
    model_calls, tool_calls: u64,
    external_cost: Money,
    extensions: Extension_View,
}

Resource_Usage :: struct {
    header: Struct_Header,
    valid_fields: u64,
    wall_time_ns, cpu_time_ns, gpu_time_ns: u64,
    peak_ram_bytes, peak_vram_bytes, storage_bytes, network_bytes: u64,
    model_calls, tool_calls: u64,
    external_cost: Money,
    extensions: Extension_View,
}

Lowering_Loss :: struct {
    header: Struct_Header,
    status, loss_flags: u32,
    dimensions: u64,
    source: Object_Ref,
    target_operation: String_View,
    code: String_View,
    description: String_View,
    extensions: Extension_View,
}
Lowering_Loss_View :: struct { data: rawptr, count: u64 }
Diagnostic_View :: struct { data: rawptr, count: u64 }

Lowering_Report :: struct {
    header: Struct_Header,
    overall_status, report_flags: u32,
    source_ir_hash: Content_Hash,
    target_plan_hash: Content_Hash,
    losses: Lowering_Loss_View,
    diagnostics: Diagnostic_View,
    extensions: Extension_View,
}

print_type :: proc(name: string, $T: typeid) {
    fmt.printf("TYPE %s %d %d\n", name, size_of(T), align_of(T))
}

print_field :: proc(name, field: string, offset: uintptr) {
    fmt.printf("FIELD %s %s %d\n", name, field, offset)
}

main :: proc() {
    print_type("mk_abi_version", Abi_Version)
    print_type("mk_struct_header", Struct_Header)
    print_type("mk_id128", Id128)
    print_type("mk_content_hash", Content_Hash)
    print_type("mk_media_time", Media_Time)
    print_type("mk_media_rate", Media_Rate)
    print_type("mk_time_range", Time_Range)
    print_type("mk_wall_time", Wall_Time)
    print_type("mk_decimal64", Decimal64)
    print_type("mk_money", Money)
    print_type("mk_bytes_view", Bytes_View)
    print_type("mk_string_view", String_View)
    print_type("mk_resource_handle", Resource_Handle)
    print_type("mk_extension", Extension)
    print_type("mk_extension_view", Extension_View)
    print_type("mk_object_ref", Object_Ref)
    print_type("mk_object_ref_view", Object_Ref_View)
    print_type("mk_color_descriptor", Color_Descriptor)
    print_type("mk_media_type", Media_Type)
    print_type("mk_stream_descriptor", Stream_Descriptor)
    print_type("mk_resource_budget", Resource_Budget)
    print_type("mk_resource_usage", Resource_Usage)
    print_type("mk_lowering_loss", Lowering_Loss)
    print_type("mk_lowering_loss_view", Lowering_Loss_View)
    print_type("mk_diagnostic_view", Diagnostic_View)
    print_type("mk_lowering_report", Lowering_Report)

    print_field("mk_struct_header", "struct_size", offset_of(Struct_Header, struct_size))
    print_field("mk_struct_header", "type_version", offset_of(Struct_Header, type_version))
    print_field("mk_object_ref", "object_type", offset_of(Object_Ref, object_type))
    print_field("mk_object_ref", "object_id", offset_of(Object_Ref, object_id))
    print_field("mk_object_ref", "version_id", offset_of(Object_Ref, version_id))
    print_field("mk_object_ref", "content_hash", offset_of(Object_Ref, content_hash))
    print_field("mk_object_ref", "ref_flags", offset_of(Object_Ref, ref_flags))
    print_field("mk_object_ref", "extensions", offset_of(Object_Ref, extensions))
    print_field("mk_media_type", "kind", offset_of(Media_Type, kind))
    print_field("mk_media_type", "format_name", offset_of(Media_Type, format_name))
    print_field("mk_media_type", "color", offset_of(Media_Type, color))
    print_field("mk_media_type", "sample_rate", offset_of(Media_Type, sample_rate))
    print_field("mk_media_type", "sample_format_name", offset_of(Media_Type, sample_format_name))
    print_field("mk_media_type", "extensions", offset_of(Media_Type, extensions))
    print_field("mk_stream_descriptor", "stream_id", offset_of(Stream_Descriptor, stream_id))
    print_field("mk_stream_descriptor", "media_type", offset_of(Stream_Descriptor, media_type))
    print_field("mk_stream_descriptor", "nominal_rate", offset_of(Stream_Descriptor, nominal_rate))
    print_field("mk_stream_descriptor", "time_domain", offset_of(Stream_Descriptor, time_domain))
    print_field("mk_resource_budget", "valid_fields", offset_of(Resource_Budget, valid_fields))
    print_field("mk_resource_budget", "wall_time_ns", offset_of(Resource_Budget, wall_time_ns))
    print_field("mk_resource_budget", "external_cost", offset_of(Resource_Budget, external_cost))
    print_field("mk_resource_budget", "extensions", offset_of(Resource_Budget, extensions))
    print_field("mk_lowering_loss", "status", offset_of(Lowering_Loss, status))
    print_field("mk_lowering_loss", "dimensions", offset_of(Lowering_Loss, dimensions))
    print_field("mk_lowering_loss", "source", offset_of(Lowering_Loss, source))
    print_field("mk_lowering_loss", "target_operation", offset_of(Lowering_Loss, target_operation))
    print_field("mk_lowering_loss", "extensions", offset_of(Lowering_Loss, extensions))
    print_field("mk_lowering_report", "overall_status", offset_of(Lowering_Report, overall_status))
    print_field("mk_lowering_report", "source_ir_hash", offset_of(Lowering_Report, source_ir_hash))
    print_field("mk_lowering_report", "losses", offset_of(Lowering_Report, losses))
    print_field("mk_lowering_report", "diagnostics", offset_of(Lowering_Report, diagnostics))
    print_field("mk_lowering_report", "extensions", offset_of(Lowering_Report, extensions))
}
