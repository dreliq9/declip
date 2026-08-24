# Foundational Media Kernel Construction Plan

**Status:** active construction plan  
**Date:** 2026-08-24  
**Working name:** Media Kernel  
**Reference client:** Declip  
**Primary implementation language:** Odin  
**Durable public boundary:** stable C ABI

This plan turns `docs/media-kernel-research.md` into a build sequence. It is intentionally biased toward proving semantics with small vertical slices rather than building a broad editor feature set.

Phase 0 now has three frozen architectural decisions:

- implementation language: `docs/media-kernel-final-language-gate.md`;
- exact temporal primitive: `docs/media-kernel-exact-time.md`;
- two-level IR architecture: `docs/media-kernel-ir-architecture.md`.

The remaining Phase 0 work is contract definition rather than open-ended technology selection: Core ABI v0, the first passive media/type/dependency/loss contracts, ADR consolidation, and the executable vertical-slice specification.

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

The planning documents live in Declip because the need was discovered there. Kernel implementation should move to a dedicated repository before Phase 1 code begins. The final repository name remains intentionally undecided until that creation step.

## 2. Kernel constitution: non-negotiable invariants

These should be written as executable conformance tests as early as possible.

1. **Exact semantic time.** Canonical finite time is normalized `{i64 value, positive i64 scale}` exact rational time. No binary floating-point seconds in committed semantic state or canonical IR.
2. **Committed state is immutable.** Changes occur through typed candidate deltas and atomic commits.
3. **Persistent identity is not execution identity.** Durable project/editorial objects and transient execution nodes/frames/buffers are separate identities and lifecycles.
4. **Canonical Editorial IR is backend-neutral.** FFmpeg, MLT, GStreamer, Metal, Vulkan, CUDA, cloud-provider, or codec-specific concepts do not define editorial semantics.
5. **Editorial and Executable IR are distinct.** Durable/editorial meaning is typed and media-shaped; executable computation is operation/graph oriented.
6. **No silent semantic loss.** Lowering either preserves semantics, records explicit loss/approximation, or fails.
7. **No implicit consequential conversion.** Time-base, color, channel-layout, memory-domain, precision, and other meaning-changing conversions must be explicit in IR or in a lowering report.
8. **Render success is not delivery acceptance.** Execution and admission are separate decisions.
9. **Every derived result declares dependencies.** Analyses, caches, plans, and admissions must be invalidatable from declared dependencies.
10. **Every external effect declares authority/resource requirements.** Network/model/plugin/cloud execution cannot rely on ambient authority in the long-term architecture.
11. **Preview and final render share semantics.** Preview may select cheaper implementations but must not silently change the intended project.
12. **Compatibility is versioned and machine-checkable.** IR, ABI, dialects, operations, plugins, and serialized state all carry versions.
13. **Creative reasoning remains above the kernel.** The kernel may verify, optimize, schedule, and explain; it does not decide what story the user should tell.
14. **Provenance is not truth.** Origin, verification, authority, synthetic status, and factual truth remain distinct concepts.
15. **Backend choice is explainable.** A planner can report why an implementation/backend was selected or rejected.
16. **Old revisions remain interpretable.** Later invalidation or supersession never rewrites historical meaning.
17. **Durable objects do not use cross-module owning pointers.** Stable IDs/references are the ownership-neutral contract for persistent media state.
18. **Ephemeral resources are generation-addressed.** CPU/GPU/provider resources use central stores and `slot + generation` handles so stale reuse is detectable.
19. **Asynchronous lifetime is explicit.** Submission/fence/cancellation/loss state, not lexical scope, determines when execution resources may be reclaimed.
20. **Queues are bounded.** Backpressure is an execution condition the scheduler must expose and manage, not an accidental failure mode.
21. **Safety instrumentation is part of definition of done.** Sanitizers, randomized stress, deterministic replay, ABI conformance, and resource-accounting checks are required for trusted-core changes.
22. **Transformation cannot commit State.** Transformation may verify, normalize, rewrite, lower, and propose deltas; State alone publishes persistent revisions.
23. **Core editorial semantics are typed.** Extensibility uses scoped/versioned extension contracts rather than turning all core objects into generic key/value attribute bags.

## 3. Working module boundaries

Names remain provisional package/module names. The kernel begins in Odin behind a stable versioned C ABI. Provider modules may use C/C++ or another native language when a concrete integration justifies it.

```text
media-core-abi
    passive IDs, references, hashes, exact time, diagnostics,
    dependency/provenance/resource/effect envelopes, version negotiation

media-state
    projects, revisions, snapshots, branches, transactions,
    persistent dependency graph, artifact identity

media-ir
    typed/versioned Editorial Media IR
    + operation/dialect-oriented Executable Media IR

media-transform
    verification, canonicalization, controlled rewrites,
    analyses, normalization, lowering, semantic-loss reports

media-execution
    capability planning, graph scheduling, resource/memory domains,
    preview/final policy, execution receipts

media-backend-ffmpeg
    first concrete execution provider

media-admission
    artifact checkers, acceptance profiles, acceptance records

media-governance
    capabilities, budgets, isolation/effect authorization
    (minimal initially, expanded after the core vertical slice)

media-capi
    stable C ABI over kernel-owned operations/contracts

bindings/
    Python first for Declip; other languages later

conformance/
    kernel invariants, ABI fixtures, backend capability suites,
    serialization/replay fixtures

examples/
    minimal reference applications and Declip integration fixtures
```

## 4. Phase 0 — Architecture freeze and technical contracts

**Goal:** establish the contracts that are expensive to change before implementing the kernel.

### 4.1 Exact time — COMPLETE

Frozen by `docs/media-kernel-exact-time.md`.

Canonical finite time is:

```text
MediaTime {
    value: i64
    scale: i64   // strictly positive
}
```

with GCD normalization, canonical zero `0/1`, exact-or-fail arithmetic, explicit overflow, and no implicit rounding.

Frame/sample rates remain separate positive rationals. VFR uses exact timestamps. Drop-frame timecode is presentation only. Ranges are half-open and reject negative duration.

Conformance evidence included common video/audio rates, mixed-rate exact alignment, 20,000 repeated 24000/1001 frame additions with zero drift, VFR/nanosecond timestamps, long sample timelines, drop-frame vectors, randomized arbitrary-precision comparison, 24,300 near-domain-limit cases, a compiled C ABI consumer, and AddressSanitizer.

**Exit criterion: SATISFIED.**

### 4.2 Implementation language / ABI direction — COMPLETE

The stable ABI remains the hard commitment. The implementation-language investigation progressed through three increasingly realistic experiments:

1. a semantic/C-ABI slice across Rust, C++, Zig, and Odin;
2. a whole-architecture slice covering revisioned state, candidate commits, generational resources, typed execution DAGs, and randomized invalid-operation stress;
3. a concurrent/asynchronous ownership gate covering bounded queues, backpressure, multiple producers/workers, cancellation, deferred reclamation behind simulated fences, device/provider loss, sanitizers, ThreadSanitizer, and a real Mesa/llvmpipe Vulkan fence lifecycle.

The final decision in `docs/media-kernel-final-language-gate.md` is:

```text
Primary kernel implementation: Odin
Durable external contract:      stable versioned C ABI
Native provider languages:      C/C++ first-class where justified
Safety-first fallback:          Rust
Zig:                            allowed for a concrete narrow advantage
```

**Exit criterion: SATISFIED.** Do not reopen general language selection during Phase 1 unless a reconsideration trigger from the final language record is hit.

### 4.3 Canonical IR architecture — COMPLETE

Frozen by `docs/media-kernel-ir-architecture.md`.

The kernel uses a two-level representation:

```text
Persistent State
       |
       v
Typed/versioned Editorial Media IR
       |
       | verify / canonicalize / transform
       v
Operation/dialect-oriented Executable Media IR
       |
       v
planner / scheduler / providers
```

The Phase 0 spike represented one exact-time project both as typed editorial objects and as a generalized op/attribute graph. Both produced the same semantic hash and the same 11-node executable plans, including `EXACT` and `BAKED_LOSS_OF_EDITABILITY` target cases. Both rejected semantic invalidity.

The typed editorial slice required 71 nonblank lines and zero dynamic attribute lookups; the generalized editorial slice required 180 lines and 15 attribute lookups and made a missing required field representable. This is supporting evidence rather than the core decision criterion.

Compiler-style concepts remain first-class in Transformation/Executable IR: dialects, typed ops, traits/interfaces, analyses, controlled rewrites, pass management, target legality, invalidation, and explicit lowering loss. MLIR itself remains an optional future implementation choice rather than a dependency commitment. OTIO is an adapter/interchange contract rather than literal canonical IR.

**Exit criterion: SATISFIED.**

### 4.4 Core ABI v0 passive schema — NEXT

Specify passive, versionable representations for at least:

```text
AbiVersion
MediaTime
TimeRange
MediaRate
ObjectId
ObjectRef
ArtifactRef
SnapshotRef
RevisionRef
ContentHash
Diagnostic
MediaType / StreamDescriptor
DependencyDescriptor
InvalidationDescriptor
ProvenanceEvent
ResourceHandle
ResourceBudget
ResourceUsage
EffectDescriptor
KernelInvocation
KernelResult
LoweringLoss
LoweringReport
AcceptanceRef / AcceptanceVectorRef
```

The ABI should define representation and compatibility mechanics without stealing semantic authority from State, Transformation, Execution, Admission, or Governance.

### 4.5 Phase 0 ADR consolidation

At minimum persist architecture decisions equivalent to:

```text
ADR-0001  Kernel family boundaries and Declip separation
ADR-0002  Exact time and time-range semantics
ADR-0003  Stable C ABI and Odin implementation choice
ADR-0004  Persistent State vs Executable computation identity
ADR-0005  Typed Editorial IR vs operation-oriented Executable IR
ADR-0006  Semantic-loss accounting
ADR-0007  Resource generation/fence lifetime model
```

These may initially be compact records that link the larger research/decision documents rather than duplicating them.

### 4.6 First vertical-slice executable specification

Freeze the expected inputs, revisions, canonical editorial representation, executable plan, lowering-loss result, artifact properties, receipt bindings, and admission result for the first end-to-end fixture before Phase 1 grows broad.

**Phase 0 exit deliverables:**

- exact-time specification — **complete**;
- implementation-language decision — **complete**;
- IR architecture decision — **complete**;
- Core ABI v0 schema;
- ADR index/records;
- first vertical-slice executable specification;
- dedicated kernel repository created before Phase 1 production code begins.

## 5. Phase 1 — State kernel and operation model

**Goal:** prove durable media state without any rendering dependency.

**Implementation:** Odin. Keep State/Editorial IR free of provider-specific objects and preserve stable-ID/candidate-commit rules.

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

- binds to an exact base snapshot/revision;
- validates preconditions;
- creates a candidate delta;
- declares affected dependencies;
- does not mutate committed state;
- commits atomically into a new revision only through State.

### Required behavior

- undo = move to prior revision, not reverse-mutation magic;
- branch = new lineage from an existing revision;
- candidate deltas can be inspected without commit;
- conflicting base revisions are detected;
- serialization is deterministic and versioned;
- content hashes bind exact committed state;
- durable object IDs remain distinct from any later executable node IDs.

**Exit criterion:** a small editing session can be replayed from operations and deterministically reproduce the same revision graph.

## 6. Phase 2 — Typed Editorial IR and Transformation kernel

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
2. structural/schema validation;
3. exact-time/range validation;
4. type validation;
5. asset/reference validation;
6. cross-object scope validation;
7. extension/operation obligations;
8. target-profile legality only when lowering.

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

Passes declare preserved/invalidated analyses and cannot publish persistent State.

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

**Exit criterion:** semantically equivalent authoring forms canonicalize consistently, and unsupported target semantics cannot disappear silently.

## 7. Phase 3 — Operation-oriented Executable Media IR and first FFmpeg backend

**Goal:** prove that canonical editorial semantics can lower into an executable graph without making FFmpeg canonical.

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

- typed input/output media ports;
- exact time behavior;
- color behavior;
- temporal footprint;
- supported memory domains;
- deterministic/replayable/cache traits;
- resource estimate hooks;
- capability requirements;
- lowering interfaces;
- dependency/invalidation behavior.

### First backend

Use FFmpeg because Declip already provides concrete compiler experience and synthetic integration fixtures.

The FFmpeg backend is an implementation provider, not the semantic model. Direct C integration from Odin is acceptable; a narrow C/C++ adapter is equally acceptable when it reduces integration risk.

### Planner outputs

The planner should emit:

- selected implementation/backend;
- rejected alternatives and reasons;
- inserted conversions;
- semantic-loss report;
- resource estimate;
- stable execution-plan hash;
- diagnostics.

**Exit criterion:** the same committed project revision compiles repeatedly into equivalent semantic execution plans, renders through FFmpeg, and rejects cleanly if required semantics cannot be preserved.

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
9. Project revision lowers/projects to typed canonical Editorial IR.
10. Transformation lowers Editorial IR to Executable Media IR.
11. Plan through FFmpeg with zero silent semantic loss.
12. Render.
13. Probe/verify the artifact.
14. Produce a render receipt.
15. Evaluate a basic delivery admission profile.

### Vertical-slice success criteria

- every timeline time calculation is exact;
- candidate delta can be rejected without touching revision 0;
- committed revision 1 is reproducible from the operation log;
- durable IDs and executable node IDs remain distinct;
- the execution plan records backend/version/conversions;
- unsupported behavior causes an explicit lowering failure/loss record;
- output duration is correct within defined frame/sample semantics;
- output resolution/rate/audio layout/color metadata match declared intent or are reported as deviations;
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

Preserve the concurrency-gate rules: resources stay alive through explicit submission/fence completion, cancellation, or provider-loss accounting, and stale generations must be rejected.

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
2. Declip project schema projects/lowers to kernel typed Editorial IR.
3. Declip render-plan normalization is progressively replaced by kernel Transformation passes.
4. Declip FFmpeg compiler becomes or delegates to the kernel FFmpeg provider.
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

- exact-time arithmetic and exact/inexact conversion;
- state/revision replay;
- transaction conflict behavior;
- candidate delta non-mutation;
- Editorial IR structural/semantic verification;
- canonicalization/idempotence;
- Executable IR type/DAG verification;
- backend semantic capability;
- semantic-loss accounting;
- dependency/invalidation correctness;
- preview/final semantic equivalence;
- admission-profile reproducibility;
- ABI compatibility/unknown-extension preservation;
- fuzzing of serialized IR and edit operations;
- concurrent resource retain/release;
- generation-safe reuse under contention;
- bounded-queue/backpressure behavior;
- asynchronous completion/fence reclamation;
- cancellation and provider/device-loss cleanup;
- sanitizer/race-detector stress on trusted runtime paths.

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

## 17. Immediate research/build backlog

Before writing the first persistent kernel implementation:

1. **COMPLETE:** freeze exact time and time-range algebra.
2. **COMPLETE:** freeze Odin + stable C ABI language direction through semantic, architectural, concurrency, sanitizer, and race-detector gates.
3. **COMPLETE:** freeze typed Editorial IR → controlled Transformation → operation-oriented Executable IR.
4. Define Core ABI v0 passive schema and compatibility rules.
5. Specify revision/snapshot/candidate-delta contracts.
6. Specify `MediaType` / stream descriptors.
7. Specify `LoweringReport` and `LoweringLoss` data contracts.
8. Specify dependency and invalidation contracts.
9. Specify the first acceptance vector/profile.
10. Map Declip's current schema/render-plan concepts onto the frozen kernel types.
11. Freeze the synthetic end-to-end vertical-slice fixture and expected hashes/semantics.
12. Consolidate ADRs/index.
13. Create the dedicated kernel repository with Odin-oriented package/module scaffolding before Phase 1 implementation begins.

## 18. Primary success metric

Do not measure early success by tool count.

The first meaningful success condition is:

> A Declip-originated edit can become a versioned candidate delta, commit to exact persistent media state, project into typed backend-neutral Editorial IR, lower through controlled Transformation into operation-oriented Executable Media IR, compile into an FFmpeg execution plan without silent semantic loss, render, and produce a separately checkable accepted artifact with a complete receipt.

Once that works, the foundation is real rather than conceptual.
