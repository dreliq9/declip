#include "include/media_kernel_abi_v0.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>

static int sv_eq(mk_string_view a, const char *literal) {
    size_t n = strlen(literal);
    return a.size == n && (n == 0 || (a.data != NULL && memcmp(a.data, literal, n) == 0));
}

/* Simulate an old receiver reading the known prefix of a future append-only struct. */
static mk_status read_media_kind_v1(const void *p, uint32_t *out_kind) {
    const mk_media_type *m = (const mk_media_type *)p;
    const size_t required = offsetof(mk_media_type, kind) + sizeof(m->kind);
    if (p == NULL || out_kind == NULL) return MK_STATUS_INVALID_ARGUMENT;
    if (m->header.type_version != MK_TYPE_VERSION_1) return MK_STATUS_UNSUPPORTED_ABI;
    if (m->header.struct_size < required) return MK_STATUS_BUFFER_TOO_SMALL;
    *out_kind = m->kind;
    return MK_STATUS_OK;
}

/* Unknown noncritical extensions are preservable/pass-through; unknown critical extensions reject. */
static mk_status inspect_extensions(mk_extension_view view) {
    for (uint64_t i = 0; i < view.count; ++i) {
        const mk_extension *ext = &view.data[i];
        if (sv_eq(ext->type_name, "media.core.known")) continue;
        if ((ext->extension_flags & MK_EXTENSION_FLAG_CRITICAL) != 0) {
            return MK_STATUS_UNSUPPORTED;
        }
    }
    return MK_STATUS_OK;
}

struct future_media_type {
    mk_media_type v1;
    uint64_t future_field;
};

int main(void) {
    assert(MK_ABI_MAJOR == 0u && MK_ABI_MINOR == 1u);
    assert(sizeof(mk_media_time) == 16u);
    assert(sizeof(mk_media_rate) == 16u);
    assert(sizeof(mk_time_range) == 32u);
    assert(sizeof(mk_id128) == 16u);
    assert(sizeof(mk_resource_handle) == 16u);

    struct future_media_type future;
    memset(&future, 0, sizeof(future));
    future.v1.header.struct_size = (uint32_t)sizeof(future);
    future.v1.header.type_version = MK_TYPE_VERSION_1;
    future.v1.kind = MK_MEDIA_KIND_VIDEO;
    future.future_field = UINT64_C(0xfeedfacecafebeef);

    uint32_t kind = 0;
    assert(read_media_kind_v1(&future, &kind) == MK_STATUS_OK);
    assert(kind == MK_MEDIA_KIND_VIDEO);

    future.v1.header.struct_size = (uint32_t)offsetof(mk_media_type, kind);
    assert(read_media_kind_v1(&future, &kind) == MK_STATUS_BUFFER_TOO_SMALL);
    future.v1.header.struct_size = (uint32_t)sizeof(future);

    mk_extension extensions[2];
    memset(extensions, 0, sizeof(extensions));
    const char unknown_name[] = "example.future.optional";
    extensions[0].header.struct_size = (uint32_t)sizeof(mk_extension);
    extensions[0].header.type_version = MK_TYPE_VERSION_1;
    extensions[0].type_name.data = unknown_name;
    extensions[0].type_name.size = sizeof(unknown_name) - 1;
    extensions[0].extension_version = 1;
    extensions[0].extension_flags = 0;

    mk_extension_view view = {extensions, 1};
    assert(inspect_extensions(view) == MK_STATUS_OK);

    const char critical_name[] = "example.future.critical";
    extensions[1] = extensions[0];
    extensions[1].type_name.data = critical_name;
    extensions[1].type_name.size = sizeof(critical_name) - 1;
    extensions[1].extension_flags = MK_EXTENSION_FLAG_CRITICAL;
    view.count = 2;
    assert(inspect_extensions(view) == MK_STATUS_UNSUPPORTED);

    mk_media_time t = {1001, 24000};
    assert(t.scale > 0);
    mk_time_range r = {{0, 1}, {5, 1}};
    assert(r.duration.value >= 0 && r.duration.scale > 0);

    mk_object_ref ref;
    memset(&ref, 0, sizeof(ref));
    ref.header.struct_size = (uint32_t)sizeof(ref);
    ref.header.type_version = MK_TYPE_VERSION_1;
    assert((ref.ref_flags & (MK_OBJECT_REF_HAS_VERSION | MK_OBJECT_REF_HAS_HASH)) == 0);

    puts("CORE_ABI_COMPAT_PASS");
    return 0;
}
