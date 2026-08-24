#ifndef MEDIA_KERNEL_ABI_V0_H
#define MEDIA_KERNEL_ABI_V0_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/*
 * Media Kernel Core ABI v0
 *
 * This header defines passive interoperability contracts. It does not grant
 * authority, commit State, validate Editorial IR, select providers, execute
 * effects, or issue Admission decisions.
 *
 * Raw struct bytes are NOT a persistence/wire format. Pointer-bearing views
 * are valid only for their documented call/result lifetime.
 */

#define MK_ABI_MAJOR 0u
#define MK_ABI_MINOR 1u

#define MK_TYPE_VERSION_1 1u

#define MK_STRUCT_FLAG_NONE 0u
#define MK_EXTENSION_FLAG_CRITICAL 0x00000001u

#define MK_OBJECT_REF_HAS_VERSION 0x00000001u
#define MK_OBJECT_REF_HAS_HASH    0x00000002u

#define MK_MEDIA_KIND_UNKNOWN 0u
#define MK_MEDIA_KIND_VIDEO   1u
#define MK_MEDIA_KIND_AUDIO   2u
#define MK_MEDIA_KIND_DATA    3u
#define MK_MEDIA_TYPE_FLAG_NONE 0u

#define MK_TIME_DOMAIN_UNSPECIFIED  0u
#define MK_TIME_DOMAIN_SOURCE       1u
#define MK_TIME_DOMAIN_PRESENTATION 2u
#define MK_TIME_DOMAIN_SEQUENCE     3u
#define MK_TIME_DOMAIN_SAMPLE       4u
#define MK_TIME_DOMAIN_WALL_CLOCK   5u
#define MK_TIME_DOMAIN_INGEST       6u
#define MK_TIME_DOMAIN_REVISION     7u
#define MK_TIME_DOMAIN_TIMECODE     8u

#define MK_DIAGNOSTIC_NOTE    1u
#define MK_DIAGNOSTIC_WARNING 2u
#define MK_DIAGNOSTIC_ERROR   3u
#define MK_DIAGNOSTIC_FATAL   4u

#define MK_DEPENDENCY_HARD     1u
#define MK_DEPENDENCY_SOFT     2u
#define MK_DEPENDENCY_ADVISORY 3u

#define MK_RESULT_SUCCESS   1u
#define MK_RESULT_FAILURE   2u
#define MK_RESULT_PARTIAL   3u
#define MK_RESULT_BLOCKED   4u
#define MK_RESULT_CANCELLED 5u

#define MK_LOWERING_EXACT                           1u
#define MK_LOWERING_EXACT_WITH_INSERTED_CONVERSION 2u
#define MK_LOWERING_APPROXIMATED                    3u
#define MK_LOWERING_BAKED_LOSS_OF_EDITABILITY      4u
#define MK_LOWERING_UNSUPPORTED                     5u

#define MK_LOSS_DIM_PRECISION          (UINT64_C(1) << 0)
#define MK_LOSS_DIM_UNCERTAINTY        (UINT64_C(1) << 1)
#define MK_LOSS_DIM_PROVENANCE_DETAIL (UINT64_C(1) << 2)
#define MK_LOSS_DIM_REVERSIBILITY      (UINT64_C(1) << 3)
#define MK_LOSS_DIM_EDITABILITY        (UINT64_C(1) << 4)
#define MK_LOSS_DIM_TIME               (UINT64_C(1) << 5)
#define MK_LOSS_DIM_COLOR              (UINT64_C(1) << 6)
#define MK_LOSS_DIM_AUDIO              (UINT64_C(1) << 7)
#define MK_LOSS_DIM_MEDIA_TYPE         (UINT64_C(1) << 8)

#define MK_RESOURCE_WALL_TIME_NS  (UINT64_C(1) << 0)
#define MK_RESOURCE_CPU_TIME_NS   (UINT64_C(1) << 1)
#define MK_RESOURCE_GPU_TIME_NS   (UINT64_C(1) << 2)
#define MK_RESOURCE_RAM_BYTES     (UINT64_C(1) << 3)
#define MK_RESOURCE_VRAM_BYTES    (UINT64_C(1) << 4)
#define MK_RESOURCE_STORAGE_BYTES (UINT64_C(1) << 5)
#define MK_RESOURCE_NETWORK_BYTES (UINT64_C(1) << 6)
#define MK_RESOURCE_MODEL_CALLS   (UINT64_C(1) << 7)
#define MK_RESOURCE_TOOL_CALLS    (UINT64_C(1) << 8)
#define MK_RESOURCE_EXTERNAL_COST (UINT64_C(1) << 9)

#define MK_EFFECT_REVERSIBILITY_UNKNOWN 0u
#define MK_EFFECT_REVERSIBLE            1u
#define MK_EFFECT_COMPENSATABLE         2u
#define MK_EFFECT_IRREVERSIBLE          3u

typedef uint32_t mk_status;
#define MK_STATUS_OK               0u
#define MK_STATUS_INVALID_ARGUMENT 1u
#define MK_STATUS_UNSUPPORTED_ABI  2u
#define MK_STATUS_BUFFER_TOO_SMALL 3u
#define MK_STATUS_NOT_FOUND        4u
#define MK_STATUS_CONFLICT         5u
#define MK_STATUS_UNSUPPORTED      6u
#define MK_STATUS_INTERNAL         7u

typedef struct mk_abi_version {
    uint16_t major;
    uint16_t minor;
    uint32_t reserved;
} mk_abi_version;

typedef struct mk_struct_header {
    uint32_t struct_size;
    uint16_t type_version;
    uint16_t flags;
} mk_struct_header;

typedef struct mk_id128 {
    uint64_t high;
    uint64_t low;
} mk_id128;

typedef struct mk_content_hash {
    uint32_t algorithm;
    uint32_t byte_count;
    uint8_t bytes[32];
} mk_content_hash;

typedef struct mk_media_time {
    int64_t value;
    int64_t scale;
} mk_media_time;

typedef struct mk_media_rate {
    int64_t numerator;
    int64_t denominator;
} mk_media_rate;

typedef struct mk_time_range {
    mk_media_time start;
    mk_media_time duration;
} mk_time_range;

typedef struct mk_wall_time {
    int64_t unix_seconds;
    uint32_t nanoseconds;
    uint32_t flags;
} mk_wall_time;

typedef struct mk_decimal64 {
    int64_t coefficient;
    int32_t exponent10;
    uint32_t flags;
} mk_decimal64;

typedef struct mk_money {
    mk_decimal64 amount;
    char currency[4];
    uint32_t reserved;
} mk_money;

typedef struct mk_bytes_view {
    const uint8_t *data;
    uint64_t size;
} mk_bytes_view;

typedef struct mk_string_view {
    const char *data;
    uint64_t size;
} mk_string_view;

typedef struct mk_resource_handle {
    uint64_t store;
    uint32_t slot;
    uint32_t generation;
} mk_resource_handle;

typedef struct mk_extension {
    mk_struct_header header;
    mk_string_view type_name;
    uint32_t extension_version;
    uint32_t extension_flags;
    mk_bytes_view payload;
} mk_extension;

typedef struct mk_extension_view {
    const mk_extension *data;
    uint64_t count;
} mk_extension_view;

typedef struct mk_object_ref {
    mk_struct_header header;
    mk_string_view object_type;
    mk_id128 object_id;
    mk_id128 version_id;
    mk_content_hash content_hash;
    uint32_t ref_flags;
    uint32_t reserved;
    mk_extension_view extensions;
} mk_object_ref;

typedef mk_object_ref mk_artifact_ref;
typedef mk_object_ref mk_snapshot_ref;
typedef mk_object_ref mk_revision_ref;
typedef mk_object_ref mk_capability_ref;
typedef mk_object_ref mk_acceptance_ref;

typedef struct mk_object_ref_view {
    const mk_object_ref *data;
    uint64_t count;
} mk_object_ref_view;

typedef struct mk_color_descriptor {
    uint32_t primaries;
    uint32_t transfer;
    uint32_t matrix;
    uint32_t range;
    uint32_t chroma_location;
    uint32_t alpha_mode;
    uint32_t bit_depth;
    uint32_t flags;
} mk_color_descriptor;

typedef struct mk_media_type {
    mk_struct_header header;
    uint32_t kind;
    uint32_t media_flags;
    mk_string_view format_name;
    uint32_t width;
    uint32_t height;
    mk_color_descriptor color;
    uint32_t sample_rate;
    uint32_t channel_count;
    mk_string_view sample_format_name;
    mk_string_view channel_layout_name;
    mk_extension_view extensions;
} mk_media_type;

typedef struct mk_stream_descriptor {
    mk_struct_header header;
    mk_id128 stream_id;
    mk_media_type media_type;
    mk_media_rate nominal_rate;
    uint32_t time_domain;
    uint32_t stream_flags;
    mk_extension_view extensions;
} mk_stream_descriptor;

typedef struct mk_diagnostic {
    mk_struct_header header;
    mk_id128 diagnostic_id;
    uint32_t severity;
    uint32_t diagnostic_flags;
    mk_string_view code;
    mk_string_view message;
    mk_object_ref subject;
    mk_time_range media_range;
    uint32_t location_flags;
    uint32_t reserved;
    mk_extension_view extensions;
} mk_diagnostic;

typedef struct mk_diagnostic_view {
    const mk_diagnostic *data;
    uint64_t count;
} mk_diagnostic_view;

typedef struct mk_dependency_descriptor {
    mk_struct_header header;
    mk_id128 dependency_id;
    mk_object_ref dependent;
    mk_object_ref dependency;
    mk_string_view dependency_kind;
    uint32_t strength;
    uint32_t dependency_flags;
    mk_time_range affected_range;
    uint32_t range_flags;
    uint32_t reserved;
    mk_extension_view extensions;
} mk_dependency_descriptor;

typedef struct mk_dependency_view {
    const mk_dependency_descriptor *data;
    uint64_t count;
} mk_dependency_view;

typedef struct mk_invalidation_descriptor {
    mk_struct_header header;
    mk_object_ref subject;
    mk_string_view invalidation_kind;
    mk_time_range affected_range;
    uint32_t invalidation_flags;
    uint32_t reserved;
    mk_extension_view extensions;
} mk_invalidation_descriptor;

typedef struct mk_provenance_event {
    mk_struct_header header;
    mk_id128 event_id;
    mk_string_view event_type;
    mk_object_ref subject;
    mk_object_ref actor;
    mk_id128 invocation_id;
    mk_wall_time occurred_at;
    mk_content_hash payload_hash;
    uint32_t provenance_flags;
    uint32_t reserved;
    mk_extension_view extensions;
} mk_provenance_event;

typedef struct mk_resource_budget {
    mk_struct_header header;
    uint64_t valid_fields;
    uint64_t wall_time_ns;
    uint64_t cpu_time_ns;
    uint64_t gpu_time_ns;
    uint64_t ram_bytes;
    uint64_t vram_bytes;
    uint64_t storage_bytes;
    uint64_t network_bytes;
    uint64_t model_calls;
    uint64_t tool_calls;
    mk_money external_cost;
    mk_extension_view extensions;
} mk_resource_budget;

typedef struct mk_resource_usage {
    mk_struct_header header;
    uint64_t valid_fields;
    uint64_t wall_time_ns;
    uint64_t cpu_time_ns;
    uint64_t gpu_time_ns;
    uint64_t peak_ram_bytes;
    uint64_t peak_vram_bytes;
    uint64_t storage_bytes;
    uint64_t network_bytes;
    uint64_t model_calls;
    uint64_t tool_calls;
    mk_money external_cost;
    mk_extension_view extensions;
} mk_resource_usage;

typedef struct mk_effect_descriptor {
    mk_struct_header header;
    mk_id128 effect_id;
    mk_string_view effect_class;
    mk_object_ref target;
    mk_string_view idempotency_key;
    uint32_t reversibility;
    uint32_t risk_class;
    mk_object_ref_view authority_refs;
    mk_content_hash input_hash;
    uint32_t effect_flags;
    uint32_t reserved;
    mk_extension_view extensions;
} mk_effect_descriptor;

typedef struct mk_effect_view {
    const mk_effect_descriptor *data;
    uint64_t count;
} mk_effect_view;

typedef struct mk_lowering_loss {
    mk_struct_header header;
    uint32_t status;
    uint32_t loss_flags;
    uint64_t dimensions;
    mk_object_ref source;
    mk_string_view target_operation;
    mk_string_view code;
    mk_string_view description;
    mk_extension_view extensions;
} mk_lowering_loss;

typedef struct mk_lowering_loss_view {
    const mk_lowering_loss *data;
    uint64_t count;
} mk_lowering_loss_view;

typedef struct mk_lowering_report {
    mk_struct_header header;
    uint32_t overall_status;
    uint32_t report_flags;
    mk_content_hash source_ir_hash;
    mk_content_hash target_plan_hash;
    mk_lowering_loss_view losses;
    mk_diagnostic_view diagnostics;
    mk_extension_view extensions;
} mk_lowering_report;

typedef struct mk_kernel_invocation {
    mk_struct_header header;
    mk_abi_version abi_version;
    mk_id128 invocation_id;
    mk_string_view caller_kernel;
    mk_string_view target_kernel;
    mk_string_view operation;
    mk_object_ref actor;
    mk_snapshot_ref snapshot;
    uint32_t context_flags;
    uint32_t reserved0;
    mk_resource_budget resource_budget;
    mk_object_ref_view input_refs;
    mk_string_view payload_type;
    mk_bytes_view payload;
    mk_wall_time requested_at;
    mk_wall_time deadline;
    uint32_t time_flags;
    uint32_t reserved1;
    mk_string_view trace_id;
    mk_extension_view extensions;
} mk_kernel_invocation;

typedef struct mk_kernel_result {
    mk_struct_header header;
    mk_abi_version abi_version;
    mk_id128 invocation_id;
    mk_string_view producing_kernel;
    uint32_t status;
    uint32_t result_flags;
    mk_object_ref_view output_refs;
    mk_string_view payload_type;
    mk_bytes_view payload;
    mk_diagnostic_view diagnostics;
    mk_dependency_view dependencies;
    mk_effect_view effects_requested;
    mk_resource_usage resource_usage;
    mk_wall_time completed_at;
    mk_extension_view extensions;
} mk_kernel_result;

typedef struct mk_kernel_handle mk_kernel_handle;
typedef struct mk_result_handle mk_result_handle;

#ifdef __cplusplus
}
#endif

#endif
