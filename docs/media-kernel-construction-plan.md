# Foundational Media Kernel Construction Plan

**Status:** initial construction plan  
**Date:** 2026-08-22  
**Working name:** Media Kernel  
**Reference client:** Declip

This plan turns `docs/media-kernel-research.md` into a build sequence. It is intentionally biased toward proving semantics with small vertical slices rather than building a broad editor feature set.

## 1. Construction strategy

### 1.1 Build a kernel family, initially in one repository

The architecture has multiple responsibility domains, but implementation should begin in one repository/monorepo with hard module boundaries.

Do **not** create separate State, Transformation, Execution, Admission, and Governance repositories before the contracts have been exercised together.

Split repositories only if deployment, release cadence, security isolation, or ABI ownership later requires it.

### 1.2 Keep Declip separate

Declip remains an application/reference client.

The kernel must not absorb:

- creative intent;
- highlight selection;
- transcription strategy;
- social-media workflow logic;
- caption wording/style strategy;
- AI provider/model selection;
- MCP/CLI UX.

The kernel should provide the primitives and guarantees those workflows consume.

### 1.3 Implementation repository

The planning documents live in Declip because the need was discovered there. Kernel implementation should move to a dedicated repository before Phase 1 code begins. The final repository name is intentionally left undecided here.

## 2. Kernel constitution: non-negotiable invariants

These should be written as executable conformance tests as early as possible.

1. **Exact semantic time.** No binary floating-point seconds in committed semantic state or canonical IR.
2. **Committed state is immutable.** Changes occur through typed candidate deltas and atomic commits.
3. **Persistent identity is not execution identity.** Durable project objects and transient frames/buffers are separate types and lifecycles.
4. **Canonical IR is backend-neutral.** FFmpeg, MLT, GStreamer, Metal, Vulkan, CUDA, cloud-provider, or codec-specific concepts do not define canonical semantics.
5. **No silent semantic loss.** Lowering either preserves semantics, records explicit loss/approximation, or fails.
6. **No implicit consequential conversion.** Time-base, color, channel-layout, memory-domain, precision, and other meaning-changing conversions must be explicit in IR or in a lowering report.
7. **Render success is not delivery acceptance.** Execution and admission are separate decisions.
8. **Every derived result declares dependencies.** Analyses, caches, plans, and admissions must be invalidatable from declared dependencies.
9. **Every external effect declares authority/resource requirements.** Network/model/plugin/cloud execution cannot rely on ambient authority in the long-term architecture.
10. **Preview and final render share semantics.** Preview may select cheaper implementations but must not silently change the intended project.
11. **Compatibility is versioned and machine-checkable.** IR, ABI, dialects, operations, plugins, and serialized state all carry versions.
12. **Creative reasoning remains above the kernel.** The kernel may verify, optimize, schedule, and explain; it does not decide what story the user should tell.
13. **Provenance is not truth.** Origin, verification, authority, synthetic status, and factual truth remain distinct concepts.
14. **Backend choice is explainable.** A planner can report why an implementation/backend was selected or rejected.
15. **Old revisions remain interpretable.** Later invalidation or supersession never rewrites historical meaning.

## 3. Working module boundaries

Names are conceptual until the implementation-language decision is complete.

```text
media-core-abi
    passive IDs, references, hashes, exact time, diagnostics,
    dependency/provenance/resource/effect envelopes, version negotiation

media-state
    projects, revisions, snapshots, branches, transactions,
    persistent dependency graph, artifact identity

media-ir
    editorial IR + executable media IR types and dialect contracts

media-transform
    verification, canonicalization, controlled rewrites,
    normalization, lowering, semantic-loss reports

media-execution
    capability planning, graph scheduling, resource/memory domains,
    preview/final policy, execution receipts

media-backend-ffmpeg
    first concrete execution backend

media-admission
    artifact checkers, acceptance profiles, acceptance records

media-governance
    capabilities, budgets, isolation/effect authorization
    (minimal initially, expanded after the core vertical slice)

media-capi
    stable C ABI over kernel-owned operations

bindings/
    Python first for Declip; other languages later

conformance/
    kernel invariants, backend capability suites, serialization fixtures

examples/
    minimal reference applications and Declip integration fixtures
```

## 4. Phase 0 — Architecture freeze and technical bakeoffs

**Goal:** establish the contracts that are expensive to change before implementing the kernel.

### 4.1 Exact time bakeoff

Evaluate at least:

- signed integer ticks + exact rational rate;
- canonical numerator/denominator rational time;
- fixed common-timescale representation with exact conversion metadata.

Tests must cover:

- 24/1, 25/1, 30/1;
- 24000/1001, 30000/1001, 60000/1001;
- 44.1 kHz and 48 kHz audio;
- hour-scale and day-scale timelines;
- negative time where legal;
- drop-frame timecode formatting versus underlying exact time;
- mixed-rate composition without cumulative drift;
- overflow behavior.

**Exit criterion:** exact arithmetic and conversion rules are specified independently of implementation language.

### 4.2 Implementation-language/ABI bakeoff

The stable ABI is the hard commitment; internal language is not.

Benchmark a small representative kernel slice in:

- Rust;
- C++;
- optionally Zig if it remains competitive after ecosystem/FFI review.

Measure:

- C ABI ergonomics;
- FFmpeg/libav interop;
- GStreamer/libplacebo/OpenColorIO interop;
- opaque-handle ownership safety;
- plugin-call overhead;
- graph construction/traversal overhead;
- reference counting/arena strategies;
- build/package complexity;
- sanitizer/fuzzing support;
- cross-platform toolchain maturity.

**Current prior:** Rust core + stable C ABI is attractive, but this phase must validate it rather than assume it.

### 4.3 Canonical IR research spike

Build throwaway prototypes for:

- OTIO-like editorial objects with stronger exact-time/types;
- MLIR-inspired operations/dialects/traits/interfaces/pass management;
- a simpler custom SSA/dataflow execution IR.

Do not commit to MLIR itself without proving that dependency weight and runtime model fit a media kernel.

### 4.4 Define the first ABI schema

Specify passive versions of:

```text
MediaTime
TimeRange
ObjectId
ObjectRef
ArtifactRef
SnapshotRef
RevisionRef
ContentHash
Diagnostic
DependencyDescriptor
ProvenanceEvent
ResourceBudget
ResourceUsage
EffectDescriptor
KernelInvocation
KernelResult
LoweringLoss
LoweringReport
```

**Phase 0 deliverables:**

- architecture decision records;
- exact-time specification;
- ABI v0 schema;
- language bakeoff report;
- first vertical-slice executable specification.

## 5. Phase 1 — State kernel and operation model

**Goal:** prove durable media state without any rendering dependency.

### Minimal persistent model

```text
Project
Sequence
Track
Clip
AssetRef
Transition
AudioRoute
OutputIntent
Revision
Snapshot
```

Do not model every future effect yet.

### Initial operations

```text
CreateProject
CreateSequence
AddTrack
InsertClip
TrimClip
MoveClip
SplitClip
RippleDelete
SetTransition
SetAudioRoute
SetOutputIntent
```

Each operation:

- binds to a base snapshot/revision;
- validates preconditions;
- creates a candidate delta;
- declares affected dependencies;
- does not mutate committed state;
- commits atomically into a new revision only through State.

### Required behavior

- undo = move to prior revision, not reverse mutation magic;
- branch = new lineage from an existing revision;
- candidate deltas can be inspected without commit;
- conflicting base revisions are detected;
- serialization is deterministic and versioned;
- content hashes bind exact committed state.

**Exit criterion:** a small editing session can be replayed from operations and deterministically reproduce the same revision graph.

## 6. Phase 2 — Canonical editorial IR and Transformation kernel

**Goal:** make project meaning explicit and independently verifiable.

### First semantic coverage

- exact source ranges;
- exact timeline placement;
- gaps;
- hard cuts;
- two-clip transitions;
- track ordering/composition intent;
- clip gain/audio routing intent;
- output dimensions/rate/color intent;
- asset references and version bindings.

### Verification pipeline

1. encoding/IR-version validation;
2. structural validation;
3. exact-time/range validation;
4. type validation;
5. asset/reference validation;
6. cross-object scope validation;
7. operation/trait obligations;
8. target-profile legality when lowering.

### Controlled rewrite system

No unrestricted IR mutation by passes.

Initial passes:

```text
normalize_time
resolve_asset_refs
canonicalize_track_order
normalize_gaps
normalize_transition_ranges
infer_required_media_types
```

Passes declare preserved/invalidated analyses.

### Semantic-loss contract

Every target conversion returns a `LoweringReport`.

At minimum:

```text
EXACT
EXACT_WITH_INSERTED_CONVERSION
APPROXIMATED
BAKED_LOSS_OF_EDITABILITY
UNSUPPORTED
```

with structured details rather than prose-only warnings.

**Exit criterion:** two semantically equivalent authoring forms canonicalize to the same intended canonical representation, and unsupported target semantics cannot disappear silently.

## 7. Phase 3 — Executable Media IR and first FFmpeg backend

**Goal:** prove that canonical semantics can lower into an executable graph without making FFmpeg canonical.

### Minimal executable node classes

```text
Decode
SourceRange
TimeTransform
Scale
ColorConvert
Composite
Transition
AudioDecode
Gain
AudioMix
Encode
Mux
Sink
```

Each operation/node contract should declare where applicable:

- input/output media types;
- exact time behavior;
- color behavior;
- temporal footprint;
- supported memory domains;
- deterministic/replayable traits;
- resource estimate hooks;
- lowering capabilities.

### First backend

Use FFmpeg because Declip already provides concrete compiler experience and synthetic integration fixtures.

The FFmpeg backend should be treated as an implementation provider, not as the semantic model.

### Planner outputs

The planner should emit:

- selected implementation/backend;
- rejected alternatives and reasons;
- inserted conversions;
- semantic-loss report;
- resource estimate;
- stable execution-plan hash;
- diagnostics.

**Exit criterion:** the same committed project revision can be compiled repeatedly into equivalent semantic execution plans, rendered through FFmpeg, and rejected cleanly if the backend cannot preserve required semantics.

## 8. Phase 4 — First end-to-end vertical slice

This is the first milestone that should be demoed externally.

### Scenario

1. Create project and revision 0.
2. Add two synthetic video clips with exact source ranges.
3. Add a 12-frame dissolve.
4. Add a separate music/audio bed with exact routing/gain.
5. Declare output dimensions, frame rate, and color intent.
6. Agent/application proposes a trim/ripple edit as a candidate delta.
7. Inspect the candidate diff.
8. Commit it to revision 1.
9. Compile revision 1 to canonical editorial IR.
10. Lower to executable media IR.
11. Plan through FFmpeg with zero silent semantic loss.
12. Render.
13. Probe/verify the artifact.
14. Produce a render receipt.
15. Evaluate a basic delivery admission profile.

### Vertical-slice success criteria

- every timeline time calculation is exact;
- candidate delta can be rejected without touching revision 0;
- committed revision 1 is reproducible from the operation log;
- the execution plan records backend/version/conversions;
- unsupported behavior causes an explicit lowering failure/loss record;
- output duration is correct within defined frame/sample semantics;
- output resolution/rate/audio layout/color metadata match the declared intent or are reported as deviations;
- receipt binds project revision, plan, inputs, tool/backend versions, and output hash;
- admission is a separate result from render success.

## 9. Phase 5 — Admission kernel and render receipts

**Goal:** turn artifact correctness into a first-class machine-readable contract.

### Start with stable profiles, not mutable social-platform folklore

Initial profiles:

```text
kernel.reference_master.v1
kernel.review_proxy.v1
kernel.basic_delivery_mp4.v1
```

Later profiles may encode broadcast/platform requirements with explicit versioning.

### Initial checks

- artifact exists and hashes correctly;
- container/codec profile;
- dimensions;
- exact/declared frame rate;
- duration bounds;
- audio sample rate/layout;
- basic A/V synchronization;
- color/HDR metadata consistency;
- decode-through/frame integrity;
- declared provenance completeness.

### Acceptance record

Bind to:

- artifact hash;
- profile/version;
- checker versions;
- project revision;
- execution-plan hash;
- assumptions;
- findings;
- acceptance vector.

**Exit criterion:** a successfully rendered file can still fail admission for a precise reason, and historical acceptance remains reproducible.

## 10. Phase 6 — Dependency graph, invalidation, and cache

**Goal:** make large/AI-heavy projects incrementally efficient.

### First dependency classes

```text
READS
DERIVED_FROM
MATERIALIZED_FROM
LOWERED_FROM
USES_COLOR_CONFIG
USES_MODEL
USES_POLICY
CHECKED_AGAINST
```

### Transformation invalidation contract

Each edit/pass declares:

```text
preserved
invalidated
conditionally_preserved
```

### Cache progression

1. explicit dependency graph;
2. dirty-range calculation;
3. stable computation identity;
4. cacheability traits;
5. content-addressed intermediate storage where proven safe.

Do not jump directly to universal content-addressed caching before dependency semantics are correct.

**Exit criterion:** changing an unrelated title/metadata operation does not cause transcription, scene analysis, or other independent derived work to recompute in an integration fixture.

## 11. Phase 7 — Governance and resource-aware execution

**Goal:** make agents, plugins, cloud models, and previews safe and predictable.

### Capability model

Initial scopes:

- read selected assets;
- write candidate artifacts;
- modify candidate project state;
- commit revisions;
- network read/write;
- invoke external model;
- final-render/publish authority.

### Resource budgets

```text
wall_time
CPU time
RAM
VRAM
storage/cache
network
external API cost
```

### Execution policies

```text
InteractivePreview
BackgroundPreview
FinalRender
Analysis
```

The planner may choose different implementations under each policy but must preserve the same declared semantics or explicitly report approximation.

**Exit criterion:** one project can run a reduced-cost preview and a full final render through different implementations without changing committed project meaning.

## 12. Phase 8 — Professional media depth

After the semantic foundation is stable, expand where established libraries are strongest instead of reinventing them.

### Color

- formalize color type/contracts;
- integrate OpenColorIO where appropriate;
- evaluate libplacebo for GPU transforms/HDR/scaling;
- explicit scene/display-referred transformations;
- no hidden Rec.709 assumptions.

### GPU/resource providers

Provide backend-neutral resource handles and capability negotiation for combinations such as:

- CPU memory;
- Metal textures;
- Vulkan images;
- D3D textures;
- CUDA/hardware surfaces;
- external/imported handles.

Do not make one GPU API canonical.

### Audio

Promote audio to a real graph:

- buses;
- sends;
- sample-accurate automation;
- channel layouts;
- resampling;
- sidechains;
- loudness metadata;
- synchronization contracts.

### Interchange

- OTIO adapter;
- FCPXML/other editorial adapters as justified;
- OpenFX compatibility bridge;
- C2PA provenance export;
- GStreamer/GES and/or additional render backend evaluation.

## 13. Phase 9 — Live and distributed temporal profiles

Do not force live/distributed complexity into the first implementation, but reserve the semantics from Phase 0.

Add support for:

- wall-clock/external timecode;
- ingest/arrival time;
- growing media;
- late analyses;
- corrections/retractions;
- stream progress/watermarks;
- collaborative revisions;
- remote/distributed execution;
- resumable execution and failure recovery.

The offline kernel should remain a valid simpler profile of the same model.

## 14. Declip migration strategy

Do not rewrite Declip in one step.

### Migration order

1. Kernel exact time + refs become available behind a Declip adapter.
2. Declip project schema lowers to kernel editorial IR.
3. Declip render-plan normalization is progressively replaced by kernel Transformation passes.
4. Declip FFmpeg compiler becomes or delegates to the kernel FFmpeg backend.
5. Declip editing commands emit kernel candidate operations/deltas.
6. Declip gains proposal/commit UX through MCP/CLI/Python.
7. Declip consumes kernel receipts/admission.
8. Legacy compatibility shims remain until conformance tests prove replacement.

At every step Declip remains usable.

## 15. What not to build early

Avoid feature accumulation before the vertical slice proves the foundation.

Do not prioritize early:

- dozens of transitions;
- generative-media providers;
- transcription;
- social-media templates;
- motion-graphics libraries;
- a full editor UI;
- distributed render farms;
- an enormous plugin marketplace;
- every professional interchange format.

Those are consumers/tests of the kernel, not prerequisites for proving the kernel.

## 16. Verification strategy

The kernel should be unusually test-driven because its value is semantic trust.

### Conformance suites

- exact-time arithmetic;
- state/revision replay;
- transaction conflict behavior;
- candidate delta non-mutation;
- canonicalization/idempotence;
- backend semantic capability;
- semantic-loss accounting;
- dependency/invalidation correctness;
- preview/final semantic equivalence;
- admission-profile reproducibility;
- ABI compatibility/unknown-field preservation;
- fuzzing of serialized IR and edit operations.

### Golden media fixtures

Prefer generated deterministic fixtures for:

- mixed frame rates;
- mixed audio sample rates;
- gaps/overlaps;
- exact transitions;
- color-space transformations;
- channel-layout changes;
- VFR ingestion;
- corrupted input behavior;
- missing streams;
- long-duration drift.

## 17. First research/build backlog

Before writing the first persistent kernel implementation:

1. Specify exact time and time-range algebra.
2. Specify revision/snapshot/candidate-delta contracts.
3. Specify `MediaType`/stream descriptors.
4. Specify `LoweringReport` and `LoweringLoss` taxonomy.
5. Specify dependency and invalidation contracts.
6. Specify the first acceptance vector/profile.
7. Run Rust/C++/optional-Zig C-ABI bakeoff.
8. Prototype OTIO-like editorial IR versus custom/MLIR-inspired representation.
9. Map Declip's current schema/render-plan concepts onto the proposed kernel types.
10. Define the synthetic end-to-end vertical-slice fixture and expected hashes/semantics.

## 18. Primary success metric

Do not measure early success by tool count.

The first meaningful success condition is:

> A Declip-originated edit can become a versioned candidate delta, commit to exact persistent media state, compile through a backend-neutral semantic IR into an FFmpeg execution plan, render without silent semantic loss, and produce a separately checkable accepted artifact with a complete receipt.

Once that works, the foundation is real rather than conceptual.