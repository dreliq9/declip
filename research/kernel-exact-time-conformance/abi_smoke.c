#include "media_time.h"
#include <assert.h>
#include <stdio.h>

int main(void) {
    mk_media_time a = {0}, b = {0}, sum = {0};
    assert(sizeof(mk_media_time) == 16);
    assert(mk_time_make(1001, 24000, &a) == MK_TIME_OK);
    assert(mk_time_make(1, 48000, &b) == MK_TIME_OK);
    assert(mk_time_add(a, b, &sum) == MK_TIME_OK);
    assert(sum.value == 2003 && sum.scale == 48000);

    int64_t samples = 0;
    assert(mk_time_ticks_exact(a, 48000, &samples) == MK_TIME_OK);
    assert(samples == 2002);

    mk_media_time five_frames = {0};
    assert(mk_time_from_rate_index(5, 30000, 1001, &five_frames) == MK_TIME_OK);
    assert(mk_time_ticks_exact(five_frames, 48000, &samples) == MK_TIME_OK);
    assert(samples == 8008);

    int32_t contains = 0;
    assert(mk_time_range_contains((mk_media_time){0,1}, (mk_media_time){1,1}, (mk_media_time){1,1}, &contains) == MK_TIME_OK);
    assert(contains == 0); /* half-open [start,end) */

    puts("C_ABI_SMOKE_PASS");
    return 0;
}
