package main

import "core:fmt"

Abi_Version :: struct { major, minor: u16, reserved: u32 }
Struct_Header :: struct { struct_size: u32, type_version, flags: u16 }
Id128 :: struct { high, low: u64 }
Content_Hash :: struct { algorithm, byte_count: u32, bytes: [32]u8 }
Media_Time :: struct { value, scale: i64 }
Media_Rate :: struct { numerator, denominator: i64 }
Ratio :: struct { numerator, denominator: i64 }
Time_Range :: struct { start, duration: Media_Time }
Wall_Time :: struct { unix_seconds: i64, nanoseconds, flags: u32 }
Decimal64 :: struct { coefficient: i64, exponent10: i32, flags: u32 }
Money :: struct { amount: Decimal64, currency: [4]u8, reserved: u32 }
Bytes_View :: struct { data: rawptr, size: u64 }
String_View :: struct { data: rawptr, size: u64 }
Resource_Handle :: struct { store: u64, slot, generation: u32 }
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

// All descriptor-array views are pointer-array + count in the C ABI.
Extension_View :: struct { data: rawptr, count: u64 }
Object_Ref_View :: struct { data: rawptr, count: u64 }
Channel_Position_View :: struct { data: rawptr, count: u64 }
Diagnostic_View :: struct { data: rawptr, count: u64 }
Dependency_View :: struct { data: rawptr, count: u64 }
Effect_View :: struct { data: rawptr, count: u64 }
Lowering_Loss_View :: struct { data: rawptr, count: u64 }

Extension :: struct {
    header: Struct_Header,
    type_name: String_View,
    extension_version, extension_flags: u32,
    payload: Bytes_View,
}

Object_Ref :: struct {
    header: Struct_Header,
    object_type: String_View,
    object_id: Id128,
    version_id: Id128,
    content_hash: Content_Hash,
    ref_flags, reserved: u32,
    extensions: Extension_View,
}

Channel_Position :: struct {
    header: Struct_Header,
    position_name: String_View,
    position_flags, reserved: u32,
    extensions: Extension_View,
}

Media_Type :: struct {
    header: Struct_Header,
    kind, media_flags: u32,
    format_name: String_View,
    width, height: u32,
    sample_aspect_ratio: Ratio,
    field_order, video_flags: u32,
    color: Color_Descriptor,
    sample_rate, channel_count, channel_order, audio_flags: u32,
    sample_format_name: String_View,
    channel_layout_name: String_View,
    channel_positions: Channel_Position_View,
    extensions: Extension_View,
}

Stream_Descriptor :: struct {
    header: Struct_Header,
    stream_id: Id128,
    media_type: rawptr,
    nominal_rate: Media_Rate,
    time_domain, stream_flags: u32,
    extensions: Extension_View,
}

Diagnostic :: struct {
    header: Struct_Header,
    diagnostic_id: Id128,
    severity, diagnostic_flags: u32,
    code: String_View,
    message: String_View,
    subject: rawptr,
    media_range: Time_Range,
    location_flags, reserved: u32,
    extensions: Extension_View,
}

Dependency_Descriptor :: struct {
    header: Struct_Header,
    dependency_id: Id128,
    dependent: rawptr,
    dependency: rawptr,
    dependency_kind: String_View,
    strength, dependency_flags: u32,
    affected_range: Time_Range,
    range_flags, reserved: u32,
    extensions: Extension_View,
}

Invalidation_Descriptor :: struct {
    header: Struct_Header,
    subject: rawptr,
    invalidation_kind: String_View,
    affected_range: Time_Range,
    invalidation_flags, reserved: u32,
    extensions: Extension_View,
}

Provenance_Event :: struct {
    header: Struct_Header,
    event_id: Id128,
    event_type: String_View,
    subject: rawptr,
    actor: rawptr,
    invocation_id: Id128,
    occurred_at: Wall_Time,
    payload_hash: Content_Hash,
    provenance_flags, reserved: u32,
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

Effect_Descriptor :: struct {
    header: Struct_Header,
    effect_id: Id128,
    effect_class: String_View,
    target: rawptr,
    idempotency_key: String_View,
    reversibility, risk_class: u32,
    authority_refs: Object_Ref_View,
    input_hash: Content_Hash,
    effect_flags, reserved: u32,
    extensions: Extension_View,
}

Lowering_Loss :: struct {
    header: Struct_Header,
    status, loss_flags: u32,
    dimensions: u64,
    source: rawptr,
    target_operation: String_View,
    code: String_View,
    description: String_View,
    extensions: Extension_View,
}

Lowering_Report :: struct {
    header: Struct_Header,
    overall_status, report_flags: u32,
    source_ir_hash: Content_Hash,
    target_plan_hash: Content_Hash,
    losses: Lowering_Loss_View,
    diagnostics: Diagnostic_View,
    extensions: Extension_View,
}

Kernel_Invocation :: struct {
    header: Struct_Header,
    abi_version: Abi_Version,
    invocation_id: Id128,
    caller_kernel: String_View,
    target_kernel: String_View,
    operation: String_View,
    actor: rawptr,
    snapshot: rawptr,
    resource_budget: rawptr,
    input_refs: Object_Ref_View,
    payload_type: String_View,
    payload: Bytes_View,
    requested_at: Wall_Time,
    deadline: Wall_Time,
    context_flags, time_flags: u32,
    trace_id: String_View,
    extensions: Extension_View,
}

Kernel_Result :: struct {
    header: Struct_Header,
    abi_version: Abi_Version,
    invocation_id: Id128,
    producing_kernel: String_View,
    status, result_flags: u32,
    output_refs: Object_Ref_View,
    payload_type: String_View,
    payload: Bytes_View,
    diagnostics: Diagnostic_View,
    dependencies: Dependency_View,
    effects_requested: Effect_View,
    resource_usage: rawptr,
    completed_at: Wall_Time,
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
    print_type("mk_ratio", Ratio)
    print_type("mk_time_range", Time_Range)
    print_type("mk_wall_time", Wall_Time)
    print_type("mk_decimal64", Decimal64)
    print_type("mk_money", Money)
    print_type("mk_bytes_view", Bytes_View)
    print_type("mk_string_view", String_View)
    print_type("mk_resource_handle", Resource_Handle)
    print_type("mk_color_descriptor", Color_Descriptor)
    print_type("mk_extension", Extension)
    print_type("mk_extension_view", Extension_View)
    print_type("mk_object_ref", Object_Ref)
    print_type("mk_object_ref_view", Object_Ref_View)
    print_type("mk_channel_position", Channel_Position)
    print_type("mk_channel_position_view", Channel_Position_View)
    print_type("mk_media_type", Media_Type)
    print_type("mk_stream_descriptor", Stream_Descriptor)
    print_type("mk_diagnostic", Diagnostic)
    print_type("mk_diagnostic_view", Diagnostic_View)
    print_type("mk_dependency_descriptor", Dependency_Descriptor)
    print_type("mk_dependency_view", Dependency_View)
    print_type("mk_invalidation_descriptor", Invalidation_Descriptor)
    print_type("mk_provenance_event", Provenance_Event)
    print_type("mk_resource_budget", Resource_Budget)
    print_type("mk_resource_usage", Resource_Usage)
    print_type("mk_effect_descriptor", Effect_Descriptor)
    print_type("mk_effect_view", Effect_View)
    print_type("mk_lowering_loss", Lowering_Loss)
    print_type("mk_lowering_loss_view", Lowering_Loss_View)
    print_type("mk_lowering_report", Lowering_Report)
    print_type("mk_kernel_invocation", Kernel_Invocation)
    print_type("mk_kernel_result", Kernel_Result)

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
    print_field("mk_media_type", "sample_aspect_ratio", offset_of(Media_Type, sample_aspect_ratio))
    print_field("mk_media_type", "field_order", offset_of(Media_Type, field_order))
    print_field("mk_media_type", "color", offset_of(Media_Type, color))
    print_field("mk_media_type", "sample_rate", offset_of(Media_Type, sample_rate))
    print_field("mk_media_type", "channel_order", offset_of(Media_Type, channel_order))
    print_field("mk_media_type", "sample_format_name", offset_of(Media_Type, sample_format_name))
    print_field("mk_media_type", "channel_positions", offset_of(Media_Type, channel_positions))
    print_field("mk_media_type", "extensions", offset_of(Media_Type, extensions))

    print_field("mk_stream_descriptor", "stream_id", offset_of(Stream_Descriptor, stream_id))
    print_field("mk_stream_descriptor", "media_type", offset_of(Stream_Descriptor, media_type))
    print_field("mk_stream_descriptor", "nominal_rate", offset_of(Stream_Descriptor, nominal_rate))
    print_field("mk_stream_descriptor", "time_domain", offset_of(Stream_Descriptor, time_domain))
    print_field("mk_stream_descriptor", "extensions", offset_of(Stream_Descriptor, extensions))

    print_field("mk_diagnostic", "subject", offset_of(Diagnostic, subject))
    print_field("mk_dependency_descriptor", "dependent", offset_of(Dependency_Descriptor, dependent))
    print_field("mk_dependency_descriptor", "dependency", offset_of(Dependency_Descriptor, dependency))
    print_field("mk_provenance_event", "subject", offset_of(Provenance_Event, subject))
    print_field("mk_provenance_event", "actor", offset_of(Provenance_Event, actor))

    print_field("mk_resource_budget", "valid_fields", offset_of(Resource_Budget, valid_fields))
    print_field("mk_resource_budget", "wall_time_ns", offset_of(Resource_Budget, wall_time_ns))
    print_field("mk_resource_budget", "external_cost", offset_of(Resource_Budget, external_cost))
    print_field("mk_resource_budget", "extensions", offset_of(Resource_Budget, extensions))

    print_field("mk_effect_descriptor", "target", offset_of(Effect_Descriptor, target))
    print_field("mk_effect_descriptor", "authority_refs", offset_of(Effect_Descriptor, authority_refs))

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

    print_field("mk_kernel_invocation", "actor", offset_of(Kernel_Invocation, actor))
    print_field("mk_kernel_invocation", "snapshot", offset_of(Kernel_Invocation, snapshot))
    print_field("mk_kernel_invocation", "resource_budget", offset_of(Kernel_Invocation, resource_budget))
    print_field("mk_kernel_result", "resource_usage", offset_of(Kernel_Result, resource_usage))
}
