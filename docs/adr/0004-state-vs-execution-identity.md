# ADR-0004 — Persistent State identity is separate from execution identity

**Status:** Accepted  
**Date:** 2026-08-24

## Decision

Durable media/project objects and transient computation/resources use separate identity systems.

```text
ProjectId / ClipId / TransitionId / RevisionId
    persistent semantic identity

ExecutableNodeId / ResourceHandle / provider object
    transient computation/resource identity
```

A durable ID may be referenced as provenance/source scope by an executable node, but it is never the executable node ID.

## Rationale

Executable graphs are optimized, fused, duplicated, lowered, rescheduled, and reconstructed. Persistent State must survive those changes unchanged.

The separation also prevents provider/native objects from leaking into project serialization and lets State/Execution evolve independently.

## Consequences

- committed State uses stable opaque IDs and immutable snapshots/revisions;
- resource lifetime uses generation handles rather than durable object identity;
- cache/computation identity is derived from exact semantic/dependency bindings, not reused Clip IDs;
- adapters cannot substitute provider handles for canonical references.

## Evidence

See `../media-kernel-state-contract.md`, `../media-kernel-ir-architecture.md`, and `../media-kernel-final-language-gate.md`.
