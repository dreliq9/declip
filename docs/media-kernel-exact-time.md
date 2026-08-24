# Media Kernel Exact-Time Contract

**Status:** Phase 0 decision — frozen for Phase 1  
**Date:** 2026-08-24  
**Primary implementation:** Odin  
**Durable ABI:** C-compatible 16-byte finite time value

## Decision

Canonical finite media time is represented as an exact reduced rational:

```text
MediaTime {
    value: i64
    scale: i64   // strictly positive
}

seconds = value / scale
```

Rules:

- `scale <= 0` is invalid;
- values are reduced by GCD before entering canonical state;
- zero is always canonicalized to `0/1`;
- canonical semantic state never stores binary floating-point seconds;
- arithmetic is exact or fails explicitly;
- no operation silently rounds to a requested frame/sample/tick grid;
- overflow is an explicit result, not wrapping or saturation.

This representation is a temporal quantity, not a remembered source grid. `2/48` and `1/24` are the same `MediaTime`. Frame rate, sample rate, timecode, wall-clock time, ingest time, and revision time are separate concepts.

## Why signed i64 scale

The earlier working sketch used `u64` for the scale. Conformance work refined that to a strictly positive signed `i64` domain.

That restriction is useful rather than limiting:

- maximum scale remains approximately `9.22e18` ticks/second, vastly above nanosecond resolution and normal media/container time bases;
- with `value` and `scale` both bounded by signed i64, cross-products used for comparison and reduced rational addition fit inside signed `i128`;
- the implementation therefore has a simple, provable widened-intermediate domain without arbitrary-precision arithmetic in the kernel hot path;
- C ABI layout remains two 64-bit integers.

Large exact results whose reduced numerator or denominator cannot fit this domain return `OVERFLOW`.

## MediaRate

A frame/sample cadence is a distinct positive rational:

```text
MediaRate {
    numerator:   positive integer
    denominator: positive integer
}
```

For integer index `i`:

```text
time(i) = i * denominator / numerator
```

Examples:

```text
24 fps          -> frame n = n/24
24000/1001 fps  -> frame n = n*1001/24000
30000/1001 fps  -> frame n = n*1001/30000
48 kHz audio    -> sample n = n/48000
```

The rate is not baked into the resulting canonical time after conversion.

## Exact grid conversion

Conversion from a `MediaTime` onto a target tick grid is fail-closed:

```text
ticks_exact(time, target_scale)
```

It succeeds only if:

```text
time * target_scale
```

is an exact integer within signed i64.

Otherwise the result is either:

```text
INEXACT
OVERFLOW
```

Explicit rounding modes such as floor, ceil, toward-zero, or nearest-even must be separate APIs with declared policy. Canonical semantic operations may not invoke them implicitly.

## TimeRange

The first range contract is:

```text
TimeRange {
    start:    MediaTime
    duration: MediaTime  // >= 0
}
```

Ranges are half-open:

```text
[start, start + duration)
```

Consequences:

- zero duration is empty;
- negative duration is invalid;
- adjacent ranges do not overlap merely because one ends where another begins;
- range end is computed through exact time arithmetic.

## Variable frame rate

VFR media is represented by exact per-frame/per-sample timestamps.

A project or stream may have a nominal/declared rate, but exact PTS/DTS values remain authoritative for sample placement. The time primitive therefore does not assume that every frame lies on one global fixed frame grid.

## Drop-frame timecode

SMPTE drop-frame is a presentation/numbering convention, not the underlying clock.

The exact-time conformance suite validates known 29.97 and 59.94 drop-frame numbering behavior, but `MediaTime` contains no drop-frame flag and never changes its arithmetic to accommodate timecode labels.

Timecode belongs in a separate labeling/presentation contract that maps exact time/sample indexes to human-readable labels.

## Multiple time axes

This decision covers semantic media/presentation time. It does not collapse the other time axes identified in the kernel research.

Future contracts may include distinct types for:

```text
SourceTime
PresentationTime
SequenceTime
SampleTime
WallClockTime
IngestTime
RevisionTime
ExternalTimecode
```

They may reuse `MediaTime` as their exact finite scalar while retaining type-level/domain distinctions.

## C ABI v0 shape

The conformance spike used:

```c
typedef struct mk_media_time {
    int64_t value;
    int64_t scale;
} mk_media_time;
```

with status-bearing operations equivalent to:

```text
make
add
subtract
compare
ticks_exact
from_rate_index
range_end
range_contains
```

This is a candidate for the Core ABI v0 passive time contract. Exact function naming/versioning remains part of the ABI-freeze step.

## Verification evidence

The Phase 0 research implementation was built as an Odin shared library and driven through the C ABI by a Python arbitrary-precision `Fraction` oracle.

Coverage included:

- normalization and canonical zero;
- positive and negative arithmetic;
- comparison across unrelated scales;
- numerator overflow;
- denominator overflow from large coprime scales;
- exact tick conversion and explicit `INEXACT` failure;
- 24/25/30 fps;
- 24000/1001, 30000/1001, 60000/1001 fps;
- 44.1/48/96 kHz audio;
- exact video/audio alignment periods;
- 20,000 repeated 24000/1001 frame additions with no drift relative to direct indexing;
- seven-day 48 kHz sample timelines;
- negative time;
- half-open range behavior;
- VFR nanosecond PTS;
- exact mixing of nanosecond timestamps and 44.1 kHz sample time;
- 29.97/59.94 drop-frame presentation vectors;
- randomized arithmetic against arbitrary-precision rational math;
- 24,300 near-i64/near-max-scale arithmetic and comparison cases;
- a compiled C ABI consumer;
- an AddressSanitizer-instrumented C ABI smoke consumer.

Final hosted result:

```text
EXACT_TIME_CONFORMANCE_PASS
EXTREME_DOMAIN_PASS cases=24300
C_ABI_SMOKE_PASS
ASAN C_ABI_SMOKE_PASS
```

The stripped research shared library was 26,528 bytes; size is not a selection criterion but confirms the primitive does not require a heavyweight arithmetic runtime.

## Implementation requirements

Phase 1 must preserve these invariants:

1. canonical finite time is always reduced;
2. zero is `0/1`;
3. scale is strictly positive signed i64;
4. widened arithmetic uses checked/proven-safe i128 intermediates;
5. any unrepresentable exact result returns overflow;
6. implicit rounding is forbidden;
7. frame/sample rates remain separate from time values;
8. drop-frame remains presentation-only;
9. ranges are half-open and reject negative duration;
10. serialization/hashing operates on canonical form only.

## Reconsideration triggers

Do not reopen this decision for convenience or backend-specific timestamp formats. Reconsider only if production evidence shows that a required media semantic value cannot be represented exactly within the signed-i64 scale domain without pathological behavior, or if a required cross-platform C ABI cannot preserve this contract.

Backend adapters with narrower or different time bases must lower explicitly and report any inexact conversion rather than changing canonical kernel time.
