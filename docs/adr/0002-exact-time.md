# ADR-0002 — Exact rational media time

**Status:** Accepted  
**Date:** 2026-08-24

## Decision

Canonical finite media time is:

```text
MediaTime {
    value: i64
    scale: i64  // > 0
}
```

Values are GCD-reduced, zero is `0/1`, arithmetic is exact-or-fail, and semantic operations never round implicitly.

`MediaRate` is a separate positive rational. `TimeRange` is half-open `[start, start + duration)` with nonnegative duration. Drop-frame timecode is presentation only. VFR uses exact timestamps.

## Rationale

The positive signed-i64 scale provides far more resolution than practical media systems require while allowing comparison/reduced arithmetic to use a provable signed-i128 widened domain without arbitrary-precision arithmetic in the hot path.

## Consequences

- no binary-float seconds in canonical State/IR;
- rate/grid provenance is not stored by inflating `MediaTime` identity;
- requested tick-grid conversion returns INEXACT rather than rounding;
- backend timebase conversion is explicit lowering.

## Evidence

See `../media-kernel-exact-time.md`. Conformance included arbitrary-precision oracle comparison, 24,300 near-limit cases, mixed frame/audio rates, VFR, long timelines, C ABI smoke, and ASan.
