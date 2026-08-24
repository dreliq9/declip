# ADR-0006 — Semantic loss is a first-class lowering result

**Status:** Accepted  
**Date:** 2026-08-24

## Decision

Every consequential lowering produces a structured `LoweringReport`. The baseline status taxonomy is:

```text
EXACT
EXACT_WITH_INSERTED_CONVERSION
APPROXIMATED
BAKED_LOSS_OF_EDITABILITY
UNSUPPORTED
```

Providers cannot silently omit, approximate, bake, recolor, resample, or otherwise change consequential semantics behind a successful execution call.

## Rationale

Backend capability is not the definition of media correctness. Different targets/providers preserve different subsets of Editorial semantics, and application policy needs machine-readable consequences before deciding whether to proceed.

## Consequences

- inserted semantic conversions appear in Executable IR/plan and report;
- findings use stable codes/dimensions, not prose-only warnings;
- capability facts and caller/profile policy stay separate;
- preview may permit approximations that final/archive profiles forbid;
- baked editability loss remains distinct from visual approximation.

## Evidence

See `../media-kernel-lowering-contract.md` and `../media-kernel-ir-architecture.md`.
