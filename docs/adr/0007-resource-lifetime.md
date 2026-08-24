# ADR-0007 — Generational resource handles and explicit asynchronous lifetime

**Status:** Accepted  
**Date:** 2026-08-24

## Decision

Ephemeral CPU/GPU/provider resources use centralized resource stores and generation-bearing handles:

```text
ResourceHandle {
    store
    slot
    generation
}
```

Asynchronous resources remain retained until explicit completion, cancellation, or provider-loss accounting. GPU/provider reclamation is fence/submission-state driven, never inferred solely from lexical scope.

Queues are bounded and backpressure is a first-class condition.

## Rationale

GPU and hardware-media lifetimes outlive ordinary function/lexical ownership. The explicit domain model works across C ABI boundaries and was validated under concurrency in all language candidates.

## Consequences

- stale slot reuse is detectable;
- resource handles are not durable media-object IDs;
- provider/device loss has an explicit cleanup state machine;
- scheduler/resource tests include ASan/TSan/stress and accounting invariants;
- memory domain remains an Execution property, not canonical `MediaType`.

## Evidence

See `../media-kernel-final-language-gate.md` and `../media-kernel-media-type-contract.md`.
