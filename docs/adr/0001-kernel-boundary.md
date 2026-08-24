# ADR-0001 — Kernel family boundaries and Declip separation

**Status:** Accepted  
**Date:** 2026-08-24

## Decision

The foundational Media Kernel is a reusable substrate separate from Declip.

Kernel responsibility is divided into Core ABI, State, Transformation, Execution, Admission, and Governance. Creative reasoning/workflow orchestration remains above the kernel.

```text
Declip / editors / agents / automation
                ↓
          Media Kernel
                ↓
       execution providers
```

## Boundary

Kernel owns what temporal media computation means and what guarantees hold.

Declip owns what a user/agent wants to accomplish: transcription strategy, highlights, caption wording/style, social/publishing workflows, provider orchestration, MCP/CLI UX, and similar product intent.

## Consequences

- Declip remains the first reference client/dogfood application.
- Kernel implementation moves to a dedicated repository before Phase 1 production code.
- App convenience policy does not become canonical media semantics merely because Declip currently implements it.
- Reasoning/creative policy is not a foundational kernel responsibility.

## Evidence

See `../media-kernel-research.md`, `../media-kernel-construction-plan.md`, and `../declip-to-media-kernel-mapping.md`.
