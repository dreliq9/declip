# ADR-0008 — Deterministic CBOR is the canonical persistence/hash profile

**Status:** Accepted  
**Date:** 2026-08-24

## Decision

Persistent State/IR/revision/dependency/lowering/Admission records use a restricted deterministic CBOR profile based on RFC 8949 core deterministic encoding.

Initial semantic content hash:

```text
SHA-256 over exact canonical CBOR bytes
```

v0 semantic schemas do not use CBOR floating-point values; exact rationals/integers/decimal contracts are structural.

## Rationale

Native C/Odin layout cannot be the project format. The kernel needs architecture-independent deterministic bytes that can be reproduced across bindings and used for exact content identity/replay.

## Consequences

- unsigned integer map field IDs;
- reserved record keys 0 type name / 1 schema version;
- definite-length/preferred encodings, deterministic map ordering, duplicate-key rejection;
- object tables have canonical sort order;
- raw native pointers never persist;
- human-readable JSON projections are noncanonical diagnostics only.

## Evidence

Python and Odin independently encoded the same Snapshot/Clip golden fixture byte-for-byte: 251 bytes, SHA-256 `b183412b7a26781dc5f18abaad943154e97a917d7c143c7413f18e2d7f1ef8ac`; insertion order did not matter; float input was rejected; Odin ASan passed.

See `../media-kernel-canonical-serialization.md`.
