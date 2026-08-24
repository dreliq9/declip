#include "include/media_kernel_abi_v0.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int sv_eq(mk_string_view a, const char *literal) {
    size_t n = strlen(literal);
    return a.size == n && (n == 0 || (a.data != NULL && memcmp(a.data, literal, n) == 0));
}

static mk_status read_media_kind_v1(const mk_media_type *m, uint32_t *out_kind) {
    const size_t required = offsetof(mk_media_type, kind) + sizeof(m->kind);
    if (m == NULL || out_kind == NULL) return MK_STATUS_INVALID_ARGUMENT;
    if (m->header.type_version != MK_TYPE_VERSION_1) return MK_STATUS_UNSUPPORTED_ABI;
    if (m->header.struct_size < required) return MK_STATUS_BUFFER_TOO_SMALL;
    *out_kind = m->kind;
    return MK_STATUS_OK;
}

static mk_status read_stream_media_kind_v1(const mk_stream_descriptor *s, uint32_t *out_kind) {
    const size_t required = offsetof(mk_stream_descriptor, media_type) + sizeof(s->media_type);
    if (s == NULL || out_kind == NULL) return MK_STATUS_INVALID_ARGUMENT;
    if (s->header.type_version != MK_TYPE_VERSION_1) return MK_STATUS_UNSUPPORTED_ABI;
    if (s->header.struct_size < required) return MK_STATUS_BUFFER_TOO_SMALL;
    return read_media_kind_v1(s->media_type, out_kind);
}

static mk_status inspect_extensions(mk_extension_view view) {
    for (uint64_t i = 0; i < view.count; ++i) {
        const mk_extension *ext = view.data[i];
        if (ext == NULL) return MK_STATUS_INVALID_ARGUMENT;
        if (sv_eq(ext->type_name, "media.core.known")) continue;
        if ((ext->extension_flags & MK_EXTENSION_FLAG_CRITICAL) != 0) {
            return MK_STATUS_UNSUPPORTED;
        }
    }
    return MK_STATUS_OK;
}

struct future_media_type {
    mk_media_type v1;
    uint64_t future_field_a;
    uint64_t future_field_b;
};

struct future_object_ref {
    mk_object_ref v1;
    uint8_t future_bytes[64];
};

int main(void) {
    assert(MK_ABI_MAJOR == 0u && MK_ABI_MINOR == 2u);
    assert(sizeof(mk_media_time) == 16u);
    assert(sizeof(mk_media_rate) == 16u);
    assert(sizeof(mk_ratio) == 16u);
    assert(sizeof(mk_time_range) == 32u);
    assert(sizeof(mk_id128) == 16u);
    assert(sizeof(mk_resource_handle) == 16u);

    /* Standalone append-only descriptor growth remains readable by an old prefix reader. */
    struct future_media_type future;
    memset(&future, 0, sizeof(future));
    future.v1.header.struct_size = (uint32_t)sizeof(future);
    future.v1.header.type_version = MK_TYPE_VERSION_1;
    future.v1.kind = MK_MEDIA_KIND_VIDEO;
    future.v1.video_flags = MK_VIDEO_FLAG_HAS_SAMPLE_ASPECT_RATIO;
    future.v1.sample_aspect_ratio = (mk_ratio){1, 1};
    future.future_field_a = UINT64_C(0xfeedfacecafebeef);
    future.future_field_b = UINT64_C(0x0123456789abcdef);

    uint32_t kind = 0;
    assert(read_media_kind_v1(&future.v1, &kind) == MK_STATUS_OK);
    assert(kind == MK_MEDIA_KIND_VIDEO);
    assert(sizeof(future) > sizeof(mk_media_type));

    future.v1.header.struct_size = (uint32_t)offsetof(mk_media_type, kind);
    assert(read_media_kind_v1(&future.v1, &kind) == MK_STATUS_BUFFER_TOO_SMALL);
    future.v1.header.struct_size = (uint32_t)sizeof(future);

    /*
     * Critical nested-evolution test: stream_descriptor points to MediaType.
     * Growing MediaType therefore cannot shift stream_descriptor's later offsets.
     */
    mk_stream_descriptor stream;
    memset(&stream, 0, sizeof(stream));
    stream.header.struct_size = (uint32_t)sizeof(stream);
    stream.header.type_version = MK_TYPE_VERSION_1;
    stream.media_type = &future.v1;
    stream.nominal_rate = (mk_media_rate){30000, 1001};
    stream.time_domain = MK_TIME_DOMAIN_PRESENTATION;
    assert(read_stream_media_kind_v1(&stream, &kind) == MK_STATUS_OK);
    assert(kind == MK_MEDIA_KIND_VIDEO);

    /* Arrays of growable descriptors are pointer arrays, not old-size contiguous strides. */
    mk_extension optional_ext;
    mk_extension critical_ext;
    memset(&optional_ext, 0, sizeof(optional_ext));
    memset(&critical_ext, 0, sizeof(critical_ext));

    const char optional_name[] = "example.future.optional";
    optional_ext.header.struct_size = (uint32_t)sizeof(optional_ext);
    optional_ext.header.type_version = MK_TYPE_VERSION_1;
    optional_ext.type_name.data = optional_name;
    optional_ext.type_name.size = sizeof(optional_name) - 1;
    optional_ext.extension_version = 1;

    const mk_extension *extension_ptrs[2] = {&optional_ext, NULL};
    mk_extension_view view = {extension_ptrs, 1};
    assert(inspect_extensions(view) == MK_STATUS_OK);

    const char critical_name[] = "example.future.critical";
    critical_ext = optional_ext;
    critical_ext.type_name.data = critical_name;
    critical_ext.type_name.size = sizeof(critical_name) - 1;
    critical_ext.extension_flags = MK_EXTENSION_FLAG_CRITICAL;
    extension_ptrs[1] = &critical_ext;
    view.count = 2;
    assert(inspect_extensions(view) == MK_STATUS_UNSUPPORTED);

    /* Nested object refs follow the same pointer rule. */
    struct future_object_ref future_ref;
    memset(&future_ref, 0, sizeof(future_ref));
    future_ref.v1.header.struct_size = (uint32_t)sizeof(future_ref);
    future_ref.v1.header.type_version = MK_TYPE_VERSION_1;

    mk_diagnostic diagnostic;
    memset(&diagnostic, 0, sizeof(diagnostic));
    diagnostic.header.struct_size = (uint32_t)sizeof(diagnostic);
    diagnostic.header.type_version = MK_TYPE_VERSION_1;
    diagnostic.subject = &future_ref.v1;
    assert(diagnostic.subject->header.struct_size == sizeof(future_ref));

    /* Media semantics added before Phase 1. */
    mk_channel_position left;
    mk_channel_position right;
    memset(&left, 0, sizeof(left));
    memset(&right, 0, sizeof(right));
    left.header.struct_size = (uint32_t)sizeof(left);
    left.header.type_version = MK_TYPE_VERSION_1;
    right = left;
    const char left_name[] = "media.channel.front_left";
    const char right_name[] = "media.channel.front_right";
    left.position_name = (mk_string_view){left_name, sizeof(left_name)-1};
    right.position_name = (mk_string_view){right_name, sizeof(right_name)-1};
    const mk_channel_position *positions[2] = {&left, &right};
    future.v1.channel_count = 2;
    future.v1.channel_order = MK_CHANNEL_ORDER_CUSTOM;
    future.v1.channel_positions = (mk_channel_position_view){positions, 2};
    assert(future.v1.channel_positions.count == 2);

    mk_media_time t = {1001, 24000};
    assert(t.scale > 0);
    mk_time_range r = {{0, 1}, {5, 1}};
    assert(r.duration.value >= 0 && r.duration.scale > 0);

    puts("CORE_ABI_COMPAT_PASS");
    return 0;
}
