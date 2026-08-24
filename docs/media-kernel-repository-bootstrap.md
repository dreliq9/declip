# Media Kernel Repository Bootstrap

**Status:** ready to execute once repository name is selected  
**Date:** 2026-08-24

## 1. Repository role

The dedicated repository contains the reusable foundational Media Kernel implementation and conformance suites.

It is **not** a Declip subpackage and should not absorb Declip application workflows.

Declip consumes the kernel through the stable C ABI / Python binding and remains the first reference client.

## 2. Initial repository layout

```text
/
├── README.md
├── LICENSE / project licensing files
├── SECURITY.md
├── docs/
│   ├── architecture.md
│   ├── adr/
│   └── specs/
│       ├── exact-time.md
│       ├── core-abi-v0.md
│       ├── canonical-serialization-v0.md
│       ├── state-contract.md
│       ├── media-type.md
│       ├── lowering.md
│       ├── dependency-invalidation.md
│       ├── admission.md
│       └── vertical-slice-v0.md
│
├── src/
│   ├── core/
│   │   ├── time/
│   │   ├── ids/
│   │   ├── hash/
│   │   ├── serialization/
│   │   └── diagnostics/
│   │
│   ├── state/
│   ├── editorial_ir/
│   ├── transform/
│   ├── executable_ir/
│   ├── execution/
│   ├── admission/
│   ├── governance/
│   └── providers/
│       └── ffmpeg/
│
├── capi/
│   ├── include/
│   │   └── media_kernel.h
│   └── src/
│
├── bindings/
│   └── python/
│
├── conformance/
│   ├── exact_time/
│   ├── core_abi/
│   ├── serialization/
│   ├── state/
│   ├── editorial_ir/
│   ├── transform/
│   ├── execution/
│   ├── admission/
│   └── vertical_slice/
│
├── fixtures/
│   ├── generators/
│   ├── golden/
│   └── negative/
│
└── examples/
    └── minimal_client/
```

The exact Odin package names may be adjusted for language conventions, but the semantic boundaries should stay visible rather than collapsing into one `kernel` package.

## 3. Dependency direction

The module graph should be acyclic at the semantic-authority layer.

Conceptually:

```text
core
 ↑
 ├──────── state
 ├──────── editorial_ir
 │            ↑
 │        transform
 │            ↓
 │      executable_ir
 │            ↓
 │        execution
 │            ↓
 │        providers
 │
 ├──────── admission
 └──────── governance
```

More precisely:

- `core` is passive and depends on no semantic-owner module;
- `state` may use core types but does not depend on Execution/Admission policy;
- `editorial_ir` uses core types and State references/contracts without committing State;
- `transform` consumes verified Editorial IR and produces candidate deltas/Executable IR/lowering facts;
- `executable_ir` does not depend on Declip/provider-native types;
- `execution` consumes legal executable plans and resource/governance contracts;
- providers implement Execution interfaces and may use native C/C++ adapters;
- Admission consumes artifacts/receipts/checker evidence but does not become part of rendering;
- Governance interprets capability/budget/effect policy; other modules carry refs/requests but do not duplicate its decisions.

## 4. First Odin implementation order

### Bootstrap 1 — leaf primitives

Implement and lock:

```text
MediaTime
MediaRate
Ratio
TimeRange
Id128
ContentHash
ResourceHandle
status/diagnostic primitives
```

Port the exact-time conformance suite first.

### Bootstrap 2 — canonical serialization

Implement the deterministic CBOR profile and SHA-256 hash domain.

The first production encoder must reproduce the existing Phase 0 golden fixture:

```text
251 bytes
SHA-256 b183412b7a26781dc5f18abaad943154e97a917d7c143c7413f18e2d7f1ef8ac
```

Keep the independent Python reference encoder as a conformance oracle until another independent implementation replaces it.

### Bootstrap 3 — Core ABI v0.2

Implement Odin-to-C wrappers/declarations for the tested passive baseline.

Conformance must reproduce C/C++/Odin layout tests and the nested-descriptor evolution fixtures.

Do not expand the public active function ABI before the result-handle/borrowed-lifetime design is explicitly specified.

### Bootstrap 4 — State

Implement:

```text
ProjectId/ObjectId
Revision
Snapshot
Branch/Head
CandidateDelta
OperationBatch
canonical State encoding/hash
candidate application
atomic publication abstraction
replay
```

Start in memory with deterministic persistence fixtures before choosing a sophisticated durable database.

### Bootstrap 5 — typed Phase-1 Editorial model

Implement only the first durable types needed by the vertical slice:

```text
Project
Sequence
Track
AssetRef
Clip
Transition
AudioRoute
OutputIntent
```

Do not begin with a generic effect/plugin universe.

### Bootstrap 6 — first operations

Implement enough operations to express the vertical fixture and State invariants:

```text
CreateProject
CreateSequence
AddTrack
InsertClip
TrimClip
MoveClip
SetTransition
SetAudioRoute
SetOutputIntent
```

`SplitClip`/`RippleDelete` may follow once the first candidate expansion/replay path is proven; the v0 vertical slice can represent ripple as a deterministic typed operation batch.

## 5. Trusted-core coding rules

### Ownership

- durable objects use IDs/references, not cross-module owning pointers;
- committed State is immutable;
- candidate projection is isolated from committed State;
- ephemeral resources use generation handles;
- asynchronous resources live until explicit completion/cancel/loss accounting.

### Context / allocation

Odin's implicit context must not become hidden semantic state.

- pure semantic helpers should be contextless where practical;
- allocator/logging/thread/runtime context is explicit at consequential boundaries;
- allocator domains are explicit for persistent State, transformation scratch, execution plans, and frame/resource pools.

### Native boundaries

- stable C ABI is the public/native lingua franca;
- C/C++ provider shims are narrow and audited;
- no provider-native object enters canonical State/Editorial IR;
- every consequential provider conversion is visible in Executable IR/LoweringReport.

## 6. Verification gates from day one

Every trusted-core change should run the relevant subset of:

```text
exact-time property tests
canonical serialization golden tests
C ABI layout/compatibility tests
State candidate-nonmutation/replay tests
Editorial validation tests
lowering/loss tests
dependency/invalidation tests
resource concurrency/accounting tests
ASan/TSan where supported
negative/fuzz fixtures
```

Do not postpone verification until the FFmpeg provider exists.

## 7. Initial external dependencies

Keep the semantic core dependency-light.

### Allowed early dependency classes

- standard/verified cryptographic SHA-256 implementation if the Odin core library implementation is suitable;
- platform/native C interfaces required by conformance;
- FFmpeg libraries/process integration only inside the provider boundary.

### Avoid early

- editor/UI frameworks;
- cloud SDKs;
- AI provider SDKs;
- large plugin frameworks;
- MLIR as a mandatory dependency before an executable-IR implementation spike proves it worthwhile;
- one database/storage engine becoming part of the State semantic model.

## 8. Build outputs

The first useful build artifacts are:

```text
native media-kernel library
public C header
Python binding/package for Declip
conformance runner
fixture generator
```

A CLI may exist for conformance/debugging but is not the kernel product boundary.

## 9. Python/Declip binding

The Python binding should expose kernel concepts, not mirror raw C pointers.

Phase-1 surface should eventually support concepts like:

```text
ProjectStore
SnapshotRef
RevisionRef
CandidateDelta
apply_candidate()
commit_candidate()
EditorialProject view/projection
```

but Python callers never receive mutable references to committed Odin State.

The binding owns/borrows native result handles according to the active C lifetime ABI once that contract is frozen.

## 10. First provider

FFmpeg is the first provider because Declip already supplies concrete semantics, compiler experience, and integration fixtures.

Provider implementation order:

1. ingest/probe adapter -> AssetRef/StreamDescriptor evidence;
2. exact executable node lowering for vertical slice;
3. capability/target legality reporting;
4. execution + cancellation/progress;
5. artifact probing/receipt;
6. Admission checker integration.

Do not begin by porting every existing Declip FFmpeg filter.

## 11. First milestone branch strategy

Recommended implementation progression in the new repo:

```text
main
  ↓
phase1/core-primitives
  ↓
phase1/state-revisions
  ↓
phase1/editorial-ir
  ↓
phase2/transformation
  ↓
phase3/ffmpeg-vertical-slice
```

Exact branch naming is flexible. The important rule is that each stage reaches its conformance exit criterion before broad feature work begins.

## 12. Migration relationship to Declip

Do not copy Declip wholesale into the new repository.

Move/extract only reusable semantics. Declip retains:

```text
MCP/CLI/tool UX
social presets
caption workflow
transcription strategy
highlight logic
generative provider orchestration
publishing paths
application convenience policy
```

Declip adapter initially converts Project v1 authoring into kernel State/Editorial semantics.

## 13. Definition of bootstrap complete

Repository bootstrap is complete when:

- Odin project/package structure exists;
- accepted ADR/specs are present;
- exact-time conformance passes;
- deterministic-CBOR golden hash passes against independent reference;
- Core ABI v0.2 C/C++/Odin conformance passes;
- State module skeleton exposes immutable snapshot/candidate boundaries;
- Python binding can load the native library and query ABI/version information;
- no Declip-specific workflow code has leaked into the kernel.

Only then move into substantive Phase 1 State implementation.
