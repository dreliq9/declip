# ADR-0003 — Odin primary implementation; stable C ABI

**Status:** Accepted  
**Date:** 2026-08-24

## Decision

- Primary Phase 1 implementation language: **Odin**.
- Durable native public contract: **stable versioned C ABI**.
- C/C++ remain first-class provider/integration languages.
- Rust is the default safety-first fallback if production evidence triggers reconsideration.

## Rationale

The final language gate showed that explicit kernel ownership/resource structures remained clean under real multithreading, cancellation, backpressure, generational reuse, deferred fence reclamation, provider loss, ASan, and TSan. Odin therefore retained the unified-kernel architecture advantage without growing a home-made borrow checker.

The C ABI is stronger than the Odin choice: implementation subsystems may change behind it.

## Consequences

- kernel safety depends on architectural invariants plus sanitizer/stress/conformance discipline;
- provider-native SDK friction can be isolated in C/C++ without redefining kernel semantics;
- changing primary language requires production evidence, not a synthetic benchmark win.

## Evidence

See `../media-kernel-final-language-gate.md` and the earlier language/architecture bakeoff records.
