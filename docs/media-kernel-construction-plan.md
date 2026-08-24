# Foundational Media Kernel Construction Plan

**Status:** active implementation roadmap  
**Date:** 2026-08-24  
**Reference client:** Declip  
**Primary implementation language:** Odin  
**Durable native boundary:** stable versioned C ABI  
**Canonical persistence:** deterministic CBOR + SHA-256

This is the authoritative build sequence after the Phase 0 architecture freeze. Detailed semantics live in the linked contracts/ADRs rather than being duplicated here.

## 1. Frozen architecture

The implementation begins from these accepted decisions:

```text
Applications / editors / agents / automation
                    |
                    v
          Stable versioned C ABI
                    |
                    v
┌──────────────────────────────────────────┐
│              Media Kernel                │
│                                          │
│  State                                   │
│    revisions / snapshots / candidates   │
│                                          │
│  Typed Editorial IR                     │
│             |                            │
│      Transformation                     │
│             |                            │
│  Executable Media IR                    │
│             |                            │
│  Execution / resources                  │
│                                          │
│  Admission        Governance            │
└──────────────────────────────────────────┘
                    |
                    v
       FFmpeg / GPU / native providers
```

Declip remains outside the kernel as the first reference application.

## 2. Governing documents

| Contract | Document |
|---|---|
| Phase 0 status | `media-kernel-phase0-status.md` |
| ADR index | `adr/README.md` |
| Language | `media-kernel-final-language-gate.md` |
| Exact time | `media-kernel-exact-time.md` |
| Core ABI v0.2 | `media-kernel-core-abi-v0.md` + `spec/media_kernel_abi_v0.h` |
| Canonical persistence | `media-kernel-canonical-serialization.md` |
| State/revisions/candidates | `media-kernel-state-contract.md` |
| IR architecture | `media-kernel-ir-architecture.md` |
| MediaType/streams | `media-kernel-media-type-contract.md` |
| Lowering/loss | `media-kernel-lowering-contract.md` |
| Dependency/invalidation | `media-kernel-dependency-invalidation-contract.md` |
| Admission | `media-kernel-admission-contract.md` |
| Declip migration | `declip-to-media-kernel-mapping.md` |
| First vertical slice | `media-kernel-vertical-slice-v0.md` |
| Repository bootstrap | `media-kernel-repository-bootstrap.md` |

If this roadmap conflicts with one of those semantic contracts, the more specific accepted contract governs until an ADR explicitly supersedes it.

## 3. Kernel constitution

Phase 1 implementation must preserve these invariants:

1. Canonical media time is exact normalized `{i64 value, positive i64 scale}`; no binary-float semantic time.
2. Committed State is immutable.
3. Every change is a typed candidate delta verified against an exact base and atomically published by State.
4. Persistent object identity is distinct from executable/resource identity.
5. Editorial IR is typed, versioned, and media-shaped.
6. Executable IR is operation/graph oriented.
7. Transformation cannot commit persistent State.
8. No consequential semantic conversion/loss is silent.
9. Render success is separate from Admission.
10. State owns the authoritative durable dependency graph.
11. Preservation/invalidation is explicit and conservative when uncertain.
12. Media semantics are distinct from memory/provider placement.
13. Ephemeral resources use generation-bearing handles.
14. Async resource lifetime is tied to explicit submission/fence/cancel/loss state.
15. Queues are bounded; backpressure is first-class.
16. Provenance, verification, acceptance, trust, and truth remain distinct.
17. Core ABI carries shared representations but does not steal semantic authority.
18. Fixed C ABI leaves embed by value; growable descriptors nest by pointer and collect via pointer arrays.
19. Native C ABI is not durable serialization.
20. Canonical persistent objects use deterministic CBOR and declared SHA-256 hash domains.
21. Critical unknown extensions fail closed.
22. Sanitizers, deterministic replay, randomized stress, and conformance are part of definition of done.
23. Creative/product reasoning remains above the kernel.

## 4. Phase 0 — COMPLETE except repository creation

Completed and verified:

- language bakeoffs and final concurrency/race gate;
- exact-time conformance;
- typed Editorial vs generalized IR spike;
- corrected Core ABI v0.2 conformance;
- deterministic cross-language CBOR golden fixture;
- State/revision/candidate contract;
- MediaType/StreamDescriptor contract;
- lowering/semantic-loss contract;
- dependency/invalidation contract;
- first Admission profile/record contract;
- Declip migration map;
- vertical-slice executable specification;
- ADR consolidation;
- repository bootstrap specification.

The only remaining project-boundary action is creating the dedicated repository under the selected permanent name.

## 5. Repository bootstrap

Execute `media-kernel-repository-bootstrap.md` after the repository name is chosen.

Bootstrap exit criteria:

- Odin package/module boundaries exist;
- accepted specs/ADRs copied into the new repository;
- exact-time suite passes;
- deterministic-CBOR golden fixture reproduces 251 bytes / SHA-256 `b183412b7a26781dc5f18abaad943154e97a917d7c143c7413f18e2d7f1ef8ac`;
- Core ABI v0.2 C/C++/Odin layout/compatibility tests pass;
- State/candidate module boundaries exist;
- Python binding can load/query native ABI/version;
- no Declip-specific workflow logic has leaked into the kernel.

## 6. Phase 1 — State kernel and typed Editorial foundation

**Goal:** prove deterministic durable media State before rendering.

### Implement first

```text
Core IDs/hashes/serialization
Project
Sequence
Track
AssetRef
Clip
Transition
AudioRoute
OutputIntent
Revision
Snapshot
Branch/Head
CandidateDelta
OperationBatch
```

### Initial operations

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

Add Split/RippleDelete after the first deterministic operation-batch path is proven.

### Required behaviors

- candidate application never mutates its base;
- failed candidate leaves canonical refs/hashes unchanged;
- branch publication uses compare-and-swap semantics;
- stale/precondition conflicts fail atomically;
- deterministic canonical serialization/hash;
- replay reproduces exact Snapshot bytes/hash;
- deleted durable IDs are not recycled;
- candidate/committed/executable identities cannot be substituted;
- idempotent retry cannot double-publish.

### Phase 1 exit

Starting from revision 0, a deterministic edit sequence can produce inspectable candidates, reject invalid/stale proposals without mutation, publish valid immutable revisions, and replay to identical Snapshot hashes.

## 7. Phase 2 — Transformation and canonical Editorial verification

**Goal:** turn committed State into independently verifiable canonical media semantics.

### First Editorial coverage

```text
exact source ranges
timeline placement
gaps
hard cuts
two-clip transitions
track ordering/composition
audio routing/gain intent
OutputIntent dimensions/rate/color/audio
asset/version bindings
```

### Verification stages

1. schema/version;
2. structural;
3. exact time/range;
4. object/reference;
5. MediaType/routing;
6. cross-object semantics;
7. extension obligations;
8. target legality only during lowering.

### Initial controlled passes

```text
normalize_time
resolve_asset_refs
canonicalize_track_order
normalize_gaps
normalize_transition_ranges
infer_required_media_types
```

Passes declare preserved/invalidated analyses and cannot publish State.

### Phase 2 exit

Semantically equivalent authoring forms canonicalize consistently; invalid Editorial semantics are rejected before provider lowering; every pass has deterministic preservation/invalidation behavior.

## 8. Phase 3 — Executable Media IR + FFmpeg provider

**Goal:** lower verified Editorial meaning into an executable graph without making FFmpeg canonical.

### First executable operations

```text
Source/Decode
SourceRange
TimeTransform
Scale
ColorConvert
Composite
Transition
AudioDecode/Source
Gain
AudioMix/Route
EncodeVideo
EncodeAudio
Mux
Sink
```

Each operation declares as applicable:

```text
typed ports
exact temporal behavior
temporal footprint
color behavior
memory-domain capabilities
determinism/replay/cache traits
resource estimates
provider requirements
lowering interfaces
dependency/invalidation behavior
```

### FFmpeg provider

Provider consumes Executable IR, not Declip Project objects.

Asset media probing moves to ingest/AssetRef/StreamDescriptor evidence rather than occurring secretly during compilation.

Consequential provider behavior such as:

```text
resample
color conversion
pixel/sample format conversion
silence insertion
frame-rate conversion
baking unsupported effects
```

must be explicit in Executable IR/LoweringReport.

### Phase 3 exit

The same exact committed revision repeatedly produces equivalent normalized plans; target capability failures are explicit; the first FFmpeg plan executes with receipt/provenance/resource accounting.

## 9. Phase 4 — Vertical Slice v0

Execute `media-kernel-vertical-slice-v0.md` exactly.

Reference semantics:

```text
30000/1001 video
48 kHz stereo audio
12-frame dissolve
initial sequence: 290 frames / 464,464 audio samples
candidate removes: 30 frames
revision-1 sequence: 260 frames / 416,416 audio samples
```

The candidate trims Clip A, ripples Clip B, and trims the audio bed to the new exact sequence end.

### Required proof chain

```text
Declip authoring
    -> CandidateDelta
    -> nonmutation proof
    -> atomic R1 commit
    -> deterministic replay/hash
    -> typed Editorial IR
    -> Executable IR
    -> FFmpeg TargetProfile
    -> EXACT LoweringReport
    -> execution receipt
    -> independent artifact probe
    -> kernel.basic_delivery_mp4.v1 AcceptanceRecord
```

Negative cases include stale base, invalid source range, overlong transition, unknown critical extension, provider semantic failure, forced bake, truncated artifact, output mismatch, artifact mutation, and replay mismatch.

### Phase 4 exit

The full success condition in the vertical-slice spec passes through automated conformance.

## 10. Phase 5 — Admission depth and receipts

Start with stable kernel-owned profiles:

```text
kernel.basic_delivery_mp4.v1
kernel.review_proxy.v1
kernel.reference_master.v1
```

Do not hard-code mutable social-platform folklore into the foundation.

Expand checker classes:

- structure/container;
- decode-through/frame integrity;
- dimensions/rate/duration;
- audio layout/sample rate;
- A/V synchronization;
- color/HDR metadata;
- provenance/receipt completeness;
- lowering/plan consistency;
- later loudness/captions/signatures/platform-specific profiles.

Only Admission creates AcceptanceRecords.

## 11. Phase 6 — Dependency/invalidation/cache

Build in order:

1. exact durable dependency graph;
2. semantic ChangeSets;
3. preservation/invalidation declarations;
4. time-domain/range dirty propagation;
5. temporal-footprint expansion;
6. stable computation identity;
7. cacheability/determinism traits;
8. content-addressed intermediates where safe.

First product-impact proof:

> a title/metadata edit preserves transcription/scene analysis and invalidates only affected composite/render work.

Do not implement universal CAS before semantic invalidation is correct.

## 12. Phase 7 — Governance and resource-aware execution

Add explicit capabilities for:

```text
read selected assets
write candidate artifacts
modify candidate State
commit revisions
network
external model/provider
final render/publish
```

Resource budgets include:

```text
wall time
CPU/GPU time
RAM/VRAM
storage
network
model/tool calls
external cost
```

Execution policies:

```text
InteractivePreview
BackgroundPreview
FinalRender
Analysis
```

Different implementations may serve preview/final only when semantic differences are explicit in the plan/lowering result.

## 13. Phase 8 — Professional media depth

### Color

- formal semantic registries;
- OpenColorIO integration where appropriate;
- libplacebo evaluation;
- HDR/scene/display-referred transforms;
- no hidden Rec.709 defaults.

### GPU / hardware media

- CPU resources;
- Metal textures/VideoToolbox;
- Vulkan images/video;
- D3D12/Media Foundation;
- CUDA/vendor surfaces where justified;
- external/imported handles;
- zero-copy paths.

No GPU API becomes canonical.

### Audio

Promote to a full graph:

```text
buses
sends
sample-accurate automation
channel layouts
resampling
sidechains
loudness metadata
synchronization
```

### Interchange

- OTIO adapter;
- FCPXML/other editorial adapters as justified;
- OpenFX compatibility bridge;
- C2PA provenance export;
- additional execution providers.

## 14. Phase 9 — Live/distributed temporal profiles

Later add:

```text
wall-clock/external timecode
ingest time
growing media
late analyses
corrections/retractions
watermarks/progress
collaborative revisions
remote/distributed execution
resumability/recovery
```

Offline editing remains a valid simpler profile of the same semantic model.

## 15. Declip migration

Migration remains incremental:

1. Declip Project v1 adapter resolves assets/exact times into kernel candidate semantics.
2. Kernel exact time/refs sit behind compatibility adapters.
3. Declip project projects into typed Editorial IR.
4. current `build_render_plan()` normalization is replaced by Transformation passes.
5. FFmpeg compiler delegates to the kernel provider.
6. editing commands emit CandidateDeltas.
7. MCP/CLI/Python expose proposal/commit/history.
8. Declip consumes receipts/Admission.
9. legacy path remains until dual-run conformance proves replacement.

Do not rewrite Declip in one step.

## 16. What stays out of the kernel

Do not prioritize or absorb early:

```text
social presets/workflows
highlight selection
transcription provider strategy
caption wording/style UX
generative-media provider orchestration
publishing integrations
full editor UI
motion-graphics catalog
plugin marketplace
distributed render farm
```

These are consumers/tests of the foundation.

## 17. Verification policy

The kernel's value is semantic trust. Relevant conformance is part of implementation, not post-hoc hardening.

Required suites include:

```text
exact-time property/oracle tests
canonical CBOR cross-language golden tests
C ABI layout/evolution tests
candidate nonmutation/replay/conflict tests
Editorial validation
Executable IR type/DAG tests
semantic-loss consistency
provider capability/fail-closed tests
dependency/invalidation tests
resource lifetime/concurrency tests
Admission reproducibility
ASan/UBSan/TSan where supported
negative/fuzz inputs
```

Hardware-specific provider validation is required before claiming those providers production-ready, but does not reopen frozen architecture unless a documented reconsideration trigger is hit.

## 18. Immediate next action

The architecture/contract work is complete enough to stop extending the Declip planning branch.

**Next:** choose the permanent dedicated repository name, create it, and execute `media-kernel-repository-bootstrap.md`.

The first code in that repository should be the already-proven leaf primitives/conformance—not FFmpeg features.

## 19. Primary success metric

Early success is not tool count or effect count.

> **A Declip-originated exact candidate edit can commit to immutable deterministic State, replay to the same hash, project into typed Editorial IR, lower without silent semantic change into provider-neutral Executable IR, execute through FFmpeg, produce a complete receipt, and receive a separately checkable Admission result.**

Once Vertical Slice v0 proves that chain, the foundation is real.
