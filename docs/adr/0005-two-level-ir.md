# ADR-0005 — Typed Editorial IR lowers to operation-oriented Executable IR

**Status:** Accepted  
**Date:** 2026-08-24

## Decision

The kernel uses two distinct semantic representations:

```text
Typed/versioned media-shaped Editorial IR
        ↓ controlled Transformation
Operation/dialect-oriented Executable Media IR
```

Persistent user/media state is not a universal generic op/attribute graph.

## Rationale

The Phase 0 spike showed both strategies could encode/lower the same semantics, but generalized editorial ops introduced repeated dynamic attribute/schema machinery and made missing core fields representable without buying enough at the durable State boundary.

Compiler-style ops/dialects/traits are strongest in Transformation and Executable IR, where extensibility, analysis, rewriting, target legality, and lowering are primary concerns.

## Consequences

- Editorial objects have explicit typed core schemas and durable IDs;
- edit operations/candidate deltas are separate from resulting durable objects;
- Executable IR can freely use transient node/value IDs, dialects, traits, and passes;
- OTIO is an adapter target; MLIR concepts are adopted selectively without requiring MLIR itself.

## Evidence

See `../media-kernel-ir-architecture.md`.
