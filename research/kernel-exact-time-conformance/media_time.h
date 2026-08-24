#ifndef MEDIA_KERNEL_EXACT_TIME_H
#define MEDIA_KERNEL_EXACT_TIME_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct mk_media_time {
    int64_t value;
    int64_t scale;
} mk_media_time;

enum {
    MK_TIME_OK = 0,
    MK_TIME_INVALID = 1,
    MK_TIME_OVERFLOW = 2,
    MK_TIME_INEXACT = 3
};

int mk_time_make(int64_t value, int64_t scale, mk_media_time *out);
int mk_time_add(mk_media_time a, mk_media_time b, mk_media_time *out);
int mk_time_sub(mk_media_time a, mk_media_time b, mk_media_time *out);
int mk_time_compare(mk_media_time a, mk_media_time b, int32_t *out_cmp);
int mk_time_ticks_exact(mk_media_time t, int64_t target_scale, int64_t *out_ticks);
int mk_time_from_rate_index(int64_t index, int64_t rate_num, int64_t rate_den, mk_media_time *out);
int mk_time_range_end(mk_media_time start, mk_media_time duration, mk_media_time *out_end);
int mk_time_range_contains(mk_media_time start, mk_media_time duration, mk_media_time t, int32_t *out_contains);

#ifdef __cplusplus
}
#endif

#endif
