# Media Kernel Exact-Time Conformance Spike

This is the Phase 0 validation spike for the foundational media kernel's exact temporal primitive. It is not a competing-language bakeoff.

## Candidate representation

```text
MediaTime {
    value: i64
    scale: i64  // strictly positive
}

seconds = value / scale
```

Canonical finite values are reduced by GCD. Zero is always `0/1`. `scale <= 0` is invalid. Canonical semantic state never stores binary floating-point seconds.

The signed `i64` scale is intentional. With both values and positive scales bounded by `i64`, cross-products for comparison and reduced rational addition fit in signed `i128`, which gives the Odin implementation a provable widened-intermediate domain without arbitrary-precision arithmetic. The maximum scale still permits roughly 1e19 ticks/second, far beyond nanosecond grids and normal media/container time bases.

`MediaTime` is a pure temporal quantity, not a remembered source grid. Therefore `2/48` canonicalizes to `1/24`. Frame, sample, timecode, wall-clock, ingest, and revision grids are separate concepts.

## Rate model

A media rate is a positive rational:

```text
MediaRate {
    numerator
    denominator
}
```

For an integer index `i`, the exact corresponding time is:

```text
i * denominator / numerator seconds
```

Examples:

```text
24 fps          -> frame n = n/24
24000/1001 fps  -> frame n = n*1001/24000
48 kHz audio    -> sample n = n/48000
```

The implementation exposes `mk_time_from_rate_index` for this operation.

## Conversion policy

Semantic conversion is fail-closed. `mk_time_ticks_exact(t, target_scale)` succeeds only when the exact time lies on the requested tick grid. It returns `MK_TIME_INEXACT` rather than rounding.

Explicit floor/ceil/nearest-even rounding belongs in a separate conversion API with a declared policy. No canonical operation may silently invoke it.

## Range semantics

`TimeRange` is defined as:

```text
start:    MediaTime
duration: MediaTime >= 0
```

Ranges are half-open: `[start, start + duration)`. Zero duration is empty. Negative duration is invalid.

## Drop-frame timecode

SMPTE drop-frame is a presentation/labeling convention, not the media clock. The conformance oracle validates the known 29.97/59.94 numbering behavior, but drop-frame state is not stored in `MediaTime`.

## VFR

Variable-frame-rate media is represented by exact per-sample/per-frame timestamps. A project or stream rate may describe intent or a nominal cadence, but does not replace exact PTS values.

## Conformance coverage

The Python `Fraction` oracle drives the Odin shared library through the C ABI and checks:

- canonical normalization;
- positive/negative exact arithmetic;
- comparison across unrelated scales;
- numerator and denominator overflow;
- exact tick-grid conversion with explicit `INEXACT` failure;
- 24/25/30 and 24000/1001, 30000/1001, 60000/1001 video rates;
- 44.1/48/96 kHz audio rates;
- exact video/audio alignment periods;
- repeated 23.976-frame accumulation with zero drift;
- seven-day sample timelines;
- negative time;
- half-open ranges;
- VFR nanosecond PTS;
- mixing nanosecond external grids with 44.1 kHz sample time;
- drop-frame presentation vectors;
- randomized arithmetic against Python arbitrary-precision rationals;
- a compiled C ABI smoke consumer.

The spike deliberately includes large coprime scales so exact results that cannot fit the ABI representation must return `MK_TIME_OVERFLOW` instead of truncating or approximating.

## Decision rule

Freeze this representation if the Odin implementation matches the arbitrary-precision oracle across all conformance cases and the C ABI consumer passes.

If a failure exposes an architectural limitation rather than an implementation bug, revise the representation before the canonical-IR spike.
