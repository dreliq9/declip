#ifndef MEDIA_KERNEL_ARCH_BAKEOFF_H
#define MEDIA_KERNEL_ARCH_BAKEOFF_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct mk_kernel mk_kernel_t;

typedef struct {
    int64_t num;
    int64_t den;
} mk_time_t;

typedef struct {
    uint32_t slot;
    uint32_t generation;
} mk_resource_handle_t;

typedef enum {
    MK_OK = 0,
    MK_INVALID = 1,
    MK_NOT_FOUND = 2,
    MK_CONFLICT = 3,
    MK_BUFFER_TOO_SMALL = 4,
    MK_OVERFLOW = 5,
    MK_STALE = 6,
    MK_CYCLE = 7
} mk_status_t;

typedef enum {
    MK_NODE_SOURCE = 1,
    MK_NODE_TRANSFORM = 2,
    MK_NODE_SINK = 3
} mk_node_kind_t;

#define MK_NO_RESOURCE_SLOT UINT32_MAX

mk_status_t mk_time_normalize(mk_time_t in, mk_time_t *out);
mk_status_t mk_time_add(mk_time_t a, mk_time_t b, mk_time_t *out);
int mk_time_compare(mk_time_t a, mk_time_t b);

mk_kernel_t *mk_kernel_create(void);
void mk_kernel_destroy(mk_kernel_t *kernel);
uint64_t mk_kernel_revision(const mk_kernel_t *kernel);
mk_status_t mk_kernel_add_asset(mk_kernel_t *kernel, const char *id, mk_time_t duration);
mk_status_t mk_kernel_append_clip(
    mk_kernel_t *kernel,
    const char *asset_id,
    mk_time_t source_in,
    mk_time_t duration,
    mk_time_t transition_in);
mk_status_t mk_kernel_propose_trim(
    mk_kernel_t *kernel,
    uint64_t base_revision,
    size_t clip_index,
    mk_time_t new_duration,
    uint64_t *proposal_id);
mk_status_t mk_kernel_commit(
    mk_kernel_t *kernel,
    uint64_t proposal_id,
    uint64_t *new_revision);
uint64_t mk_kernel_state_hash(const mk_kernel_t *kernel);

mk_status_t mk_resource_alloc(
    mk_kernel_t *kernel,
    uint64_t size_bytes,
    uint32_t domain,
    mk_resource_handle_t *out);
mk_status_t mk_resource_retain(mk_kernel_t *kernel, mk_resource_handle_t handle);
mk_status_t mk_resource_release(mk_kernel_t *kernel, mk_resource_handle_t handle);
mk_status_t mk_resource_touch(const mk_kernel_t *kernel, mk_resource_handle_t handle);
mk_status_t mk_resource_refcount(
    const mk_kernel_t *kernel,
    mk_resource_handle_t handle,
    uint32_t *out_refcount);
uint64_t mk_resource_hash(const mk_kernel_t *kernel);

mk_status_t mk_plan_reset(mk_kernel_t *kernel);
mk_status_t mk_plan_add_node(
    mk_kernel_t *kernel,
    uint32_t id,
    uint32_t kind,
    const uint32_t *deps,
    size_t dep_count,
    mk_resource_handle_t resource);
mk_status_t mk_plan_validate(const mk_kernel_t *kernel);
uint64_t mk_plan_hash(const mk_kernel_t *kernel);

uint32_t mk_ffmpeg_version(void);
uint64_t mk_benchmark(uint64_t iterations);

#ifdef __cplusplus
}
#endif

#endif
