#include "include/media_kernel_abi_v0.h"
#include <stddef.h>
#include <stdio.h>

#define TYPE(T) printf("TYPE %s %zu %zu\n", #T, sizeof(T), _Alignof(T))
#define FIELD(T, F) printf("FIELD %s %s %zu\n", #T, #F, offsetof(T, F))

#ifdef __cplusplus
#undef TYPE
#define TYPE(T) printf("TYPE %s %zu %zu\n", #T, sizeof(T), alignof(T))
#endif

int main(void) {
    TYPE(mk_abi_version);
    TYPE(mk_struct_header);
    TYPE(mk_id128);
    TYPE(mk_content_hash);
    TYPE(mk_media_time);
    TYPE(mk_media_rate);
    TYPE(mk_time_range);
    TYPE(mk_wall_time);
    TYPE(mk_decimal64);
    TYPE(mk_money);
    TYPE(mk_bytes_view);
    TYPE(mk_string_view);
    TYPE(mk_resource_handle);
    TYPE(mk_extension);
    TYPE(mk_extension_view);
    TYPE(mk_object_ref);
    TYPE(mk_object_ref_view);
    TYPE(mk_color_descriptor);
    TYPE(mk_media_type);
    TYPE(mk_stream_descriptor);
    TYPE(mk_resource_budget);
    TYPE(mk_resource_usage);
    TYPE(mk_lowering_loss);
    TYPE(mk_lowering_loss_view);
    TYPE(mk_diagnostic_view);
    TYPE(mk_lowering_report);

    FIELD(mk_struct_header, struct_size);
    FIELD(mk_struct_header, type_version);
    FIELD(mk_object_ref, object_type);
    FIELD(mk_object_ref, object_id);
    FIELD(mk_object_ref, version_id);
    FIELD(mk_object_ref, content_hash);
    FIELD(mk_object_ref, ref_flags);
    FIELD(mk_object_ref, extensions);
    FIELD(mk_media_type, kind);
    FIELD(mk_media_type, format_name);
    FIELD(mk_media_type, color);
    FIELD(mk_media_type, sample_rate);
    FIELD(mk_media_type, sample_format_name);
    FIELD(mk_media_type, extensions);
    FIELD(mk_stream_descriptor, stream_id);
    FIELD(mk_stream_descriptor, media_type);
    FIELD(mk_stream_descriptor, nominal_rate);
    FIELD(mk_stream_descriptor, time_domain);
    FIELD(mk_resource_budget, valid_fields);
    FIELD(mk_resource_budget, wall_time_ns);
    FIELD(mk_resource_budget, external_cost);
    FIELD(mk_resource_budget, extensions);
    FIELD(mk_lowering_loss, status);
    FIELD(mk_lowering_loss, dimensions);
    FIELD(mk_lowering_loss, source);
    FIELD(mk_lowering_loss, target_operation);
    FIELD(mk_lowering_loss, extensions);
    FIELD(mk_lowering_report, overall_status);
    FIELD(mk_lowering_report, source_ir_hash);
    FIELD(mk_lowering_report, losses);
    FIELD(mk_lowering_report, diagnostics);
    FIELD(mk_lowering_report, extensions);

    return 0;
}
