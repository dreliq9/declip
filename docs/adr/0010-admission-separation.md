# ADR-0010 — Artifact Admission is separate from render success

**Status:** Accepted  
**Date:** 2026-08-24

## Decision

Execution creating an artifact does not qualify it for delivery. Only the Admission Kernel creates immutable, profile-bound `AcceptanceRecord`s from exact artifact/checker/evidence bindings.

There is no generic `verified=true` / `accepted=true` flag writable by arbitrary callers.

## Rationale

Successful encoders can still produce artifacts that are truncated, semantically mismatched, out of sync, incorrectly colored, noncompliant, or missing required provenance. Qualification is a separate skeptical process.

## Consequences

- checker statuses distinguish PASS/FAIL/INDETERMINATE/ERROR;
- acceptance is dimensioned and profile/version specific;
- same artifact may pass one profile and fail another;
- historical acceptance remains bound to exact artifact/profile/checker versions;
- provenance completeness never implies factual truth.

The first stable profile is `kernel.basic_delivery_mp4.v1`.

## Evidence

See `../media-kernel-admission-contract.md` and `../media-kernel-vertical-slice-v0.md`.
