#ifndef MEDIA_KERNEL_BAKEOFF_H
#define MEDIA_KERNEL_BAKEOFF_H
#include <stddef.h>
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif

typedef struct mk_project mk_project_t;
typedef struct { int64_t num; int64_t den; } mk_time_t;
typedef enum {
  MK_OK = 0,
  MK_INVALID = 1,
  MK_NOT_FOUND = 2,
  MK_CONFLICT = 3,
  MK_BUFFER_TOO_SMALL = 4,
  MK_OVERFLOW = 5
} mk_status_t;

mk_status_t mk_time_normalize(mk_time_t in, mk_time_t* out);
mk_status_t mk_time_add(mk_time_t a, mk_time_t b, mk_time_t* out);
int mk_time_compare(mk_time_t a, mk_time_t b);

mk_project_t* mk_project_create(void);
void mk_project_destroy(mk_project_t* project);
uint64_t mk_project_revision(const mk_project_t* project);
mk_status_t mk_project_add_asset(mk_project_t* project, const char* id, mk_time_t duration);
mk_status_t mk_project_append_clip(mk_project_t* project, const char* asset_id, mk_time_t source_in, mk_time_t duration, mk_time_t transition_in);
mk_status_t mk_project_propose_trim(mk_project_t* project, uint64_t base_revision, size_t clip_index, mk_time_t new_duration, uint64_t* proposal_id);
mk_status_t mk_project_commit(mk_project_t* project, uint64_t proposal_id, uint64_t* new_revision);
mk_status_t mk_project_lower_ffmpeg(const mk_project_t* project, char* buffer, size_t capacity, size_t* needed);
uint32_t mk_ffmpeg_version(void);
uint64_t mk_benchmark(uint64_t iterations);

#ifdef __cplusplus
}
#endif
#endif
