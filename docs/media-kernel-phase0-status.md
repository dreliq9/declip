# Media Kernel Phase 0 Status

**Date:** 2026-08-24  
**Status:** architecture/contract freeze substantially complete; ready for repository bootstrap

## Completed decisions

| Area | Status | Governing document |
|---|---|---|
| Kernel/Declip boundary | COMPLETE | `media-kernel-research.md`, ADR-0001 |
| Implementation language | COMPLETE | `media-kernel-final-language-gate.md`, ADR-0003 |
| Stable native boundary | COMPLETE baseline | `media-kernel-core-abi-v0.md`, `spec/media_kernel_abi_v0.h` |
| Exact time | COMPLETE | `media-kernel-exact-time.md`, ADR-0002 |
| Persistent vs execution identity | COMPLETE | `media-kernel-state-contract.md`, ADR-0004 |
| Editorial vs Executable IR | COMPLETE | `media-kernel-ir-architecture.md`, ADR-0005 |
| State/revision/candidate semantics | COMPLETE baseline | `media-kernel-state-contract.md` |
| MediaType / streams | COMPLETE baseline | `media-kernel-media-type-contract.md` |
| Semantic lowering/loss | COMPLETE baseline | `media-kernel-lowering-contract.md`, ADR-0006 |
| Dependency/invalidation | COMPLETE baseline | `media-kernel-dependency-invalidation-contract.md` |
| Resource/concurrency lifetime | COMPLETE | `media-kernel-final-language-gate.md`, ADR-0007 |
| Artifact Admission | COMPLETE baseline | `media-kernel-admission-contract.md`, ADR-0010 |
| Canonical persistence/hash profile | COMPLETE baseline | `media-kernel-canonical-serialization.md`, ADR-0008 |
| Declip migration mapping | COMPLETE | `declip-to-media-kernel-mapping.md` |
| First vertical-slice executable spec | COMPLETE | `media-kernel-vertical-slice-v0.md` |
| ADR index | COMPLETE | `adr/README.md` |

## Verified Phase 0 evidence

### Language / concurrency

- C++/Rust/Zig/Odin semantic and architecture slices passed common behavior tests.
- final 96-case concurrent/asynchronous ownership matrix passed all four candidates with zero stale-handle acceptance/leaks/invariant violations.
- Odin ASan + TSan passed.
- C++ ASan/UBSan + TSan passed.
- corrected Rust TSan passed.
- real Vulkan queue/fence lifecycle validated on Mesa software Vulkan.

### Exact time

- Python arbitrary-precision rational oracle matched Odin implementation.
- common video/audio rates and mixed grids passed.
- repeated 24000/1001 arithmetic had zero drift.
- 24,300 near-i64/near-scale-limit cases passed.
- C ABI + ASan smoke passed.

### IR architecture

- typed Editorial and generalized op representations produced the same semantic hash and executable plans.
- explicit EXACT and BAKED_LOSS_OF_EDITABILITY paths matched.
- typed editorial representation selected; Executable IR retains compiler-style op/dialect model.

### Core ABI v0.2

- 38 type layouts and 48 field offsets matched across C/C++/Odin.
- append-only child growth remained safe behind pointer nesting.
- pointer-array extension evolution passed.
- critical/noncritical extension behavior passed.
- ASan/UBSan compatibility passed.

### Canonical serialization

Independent Python and Odin deterministic-CBOR fixture encoders produced byte-for-byte identical output:

```text
byte length: 251
SHA-256: b183412b7a26781dc5f18abaad943154e97a917d7c143c7413f18e2d7f1ef8ac
```

Map insertion order did not change bytes, semantic float input was rejected, and Odin ASan passed.

## Phase 0 corrections caught before implementation

Two material design corrections were discovered by conformance rather than paper review:

1. `MediaTime.scale` was narrowed from an unconstrained unsigned idea to **positive signed i64**, giving a provable signed-i128 widened arithmetic domain while retaining enormous practical resolution.
2. Core ABI v0.1's initial by-value nested growable descriptors were rejected. v0.2 freezes **fixed leaves by value; growable descriptors by pointer; growable collections as pointer arrays**.

These are examples of why conformance remains part of architecture work.

## First implementation milestone

The kernel is not considered real until `media-kernel-vertical-slice-v0.md` passes end to end:

```text
Declip authoring intent
    -> exact AssetRefs/StreamDescriptors
    -> CandidateDelta
    -> immutable Revision R1
    -> deterministic replay/hash
    -> typed Editorial IR
    -> controlled Transformation
    -> Executable IR
    -> exact FFmpeg lowering
    -> artifact + receipt
    -> kernel.basic_delivery_mp4.v1 AcceptanceRecord
```

The fixture uses 30000/1001 video and 48 kHz audio with sequence lengths deliberately aligned to both frame and sample grids.

## Remaining pre-Phase-1 action

**Create the dedicated Media Kernel repository and bootstrap it from these contracts.**

The repository name is intentionally not invented by this planning branch. Creating a new repository is an external/project-boundary action and should use the selected name rather than an accidental temporary name becoming permanent.

Once the repository exists, the first implementation work is:

1. copy/adapt the accepted ADRs/spec contracts;
2. establish the Odin package/module scaffold;
3. implement Core exact-time + canonical serialization primitives and conformance fixtures;
4. implement State IDs/revisions/snapshots/candidates;
5. implement typed Phase-1 Editorial model;
6. make replay/candidate-nonmutation/hash tests pass;
7. then begin Transformation/Executable IR/FFmpeg provider work for the vertical slice.

## Deferred hardware/provider validation

These are implementation/provider checkpoints, not reasons to reopen Phase 0:

- Apple Silicon Metal + VideoToolbox;
- real Vulkan GPUs/hardware video surfaces;
- D3D12 + Media Foundation;
- zero-copy decode/process/encode;
- VRAM pressure/eviction;
- actual hardware device-reset/loss behavior.

They reopen a frozen architectural decision only if they hit a documented reconsideration trigger.
