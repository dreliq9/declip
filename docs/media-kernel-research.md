# Foundational Media Kernel Research

**Status:** planning record  
**Date:** 2026-08-22  
**Branch:** `planning/media-kernel`

## 1. Decision under investigation

Declip currently sits at an agent/application layer above FFmpeg and MLT. Recent hardening made that layer substantially safer by introducing normalized render plans, compiler boundaries, backend capability checks, and fail-preserving rendering.

The larger architectural opportunity is different:

> Build a reusable foundational kernel for temporal media, then make Declip its first reference application.

The target is not "another video editor" and not "a better FFmpeg wrapper." The target is closer to the role OCCT plays for CAD or LLVM plays for compilers: a durable semantic and computational substrate on which editors, agents, automation systems, render services, and interchange tools can be built.

## 2. Market synthesis

No current project examined provides the entire target architecture.

### Existing foundations each solve a subset

- **OpenTimelineIO** has strong editorial/time semantics and interchange, but intentionally stops short of a complete executable effects/audio/color kernel.
- **GStreamer + GES** provide a mature media graph, scheduling, negotiation, hardware-memory domains, and high-level editing concepts, but do not define a universal persistent editorial semantics layer.
- **MLT** is the closest existing open NLE engine, but combines historical timeline/render semantics and backend behavior in ways that make it less suitable as a clean universal semantic kernel.
- **FFmpeg/libav*** provide excellent codecs, filtering, muxing, probing, and media primitives, but are execution libraries rather than a durable project/editing kernel.
- **libplacebo** is excellent prior art and a likely dependency for modern GPU image processing, color conversion, HDR, scaling, dithering, and frame mixing; it is not a timeline/state kernel.
- **OpenColorIO** is the strongest ecosystem choice for interoperable professional color-management semantics and transforms.
- **OpenFX** provides important plugin-ABI lessons, especially the value of a stable C ABI, but should be treated as a compatibility layer rather than the native semantic node model.
- **C2PA** provides an external provenance/authenticity standard that can consume a richer internal provenance model.

### New agent-oriented editors each discovered a different missing piece

- **mcpCut**: immutable project snapshots, pure mutations, journaled operations, multi-engine rendering.
- **OpenChatCut**: one shared editor command layer consumed by UI, internal agent, and external MCP; proposal-based edits.
- **Kinocut**: typed tool contracts, guarded execution, QC/release gates, receipts, and an explicit move toward durable project/revision state.
- **Declip**: normalized render planning, compiler isolation, backend semantic capability checks, and explicit refusal to silently drop unsupported semantics.

The market is converging on pieces of a common architecture, but remains fragmented.

## 3. Transfer from the graph-kernel research

The graph-kernel research is useful because it converged away from a monolithic "graph kernel" and toward a family of narrowly owned responsibilities.

Relevant source repositories:

- `dreliq9/Graph-Kernel-Core-ABI`
- `dreliq9/Ai-Graph-Compiler-Kernel`
- `dreliq9/Ai-Reasoning-Kernel`
- `dreliq9/Ai-OS-Graph-Kernel`
- `dreliq9/Ai-theorem-prover-kernal`

The transferable principle is not graph-specific vocabulary. It is:

> A trustworthy computational substrate should separate durable state, legal transformation, execution authority, artifact acceptance, and application reasoning instead of allowing one runtime to own all of them.

### 3.1 Passive shared ABI

The Graph Kernel Core ABI established several useful rules:

- one concept, one canonical contract;
- exact version/content binding for consequential objects;
- shared invocation/result/diagnostic/provenance envelopes;
- compatibility is explicit and machine-checkable;
- shared types do not imply shared decision authority.

For media, this implies a **Media Core ABI** that owns representation only: IDs, rational time, references, content hashes, snapshots, diagnostics, dependency descriptors, resource descriptors, provenance envelopes, and compatibility negotiation.

### 3.2 State is not computation

The Graph State research distinguishes persistent identity-bearing state from transient computation.

For media:

**Persistent media state** includes:

- assets;
- asset versions;
- sequences;
- tracks;
- clips;
- markers;
- captions;
- effect instances;
- revisions;
- branches;
- accepted render artifacts.

**Transient execution values** include:

- decoded frames;
- GPU textures;
- linearized frames;
- mixed audio blocks;
- intermediate analysis tensors;
- encoded packets.

A project object must not be the render graph. The project compiles into a transient execution graph.

### 3.3 Transformations should be typed candidate deltas

The Graph Transformation research requires semantic change to be expressed as typed transformations rather than unrestricted node mutation.

For media, edits should be operations such as:

```text
InsertClip
TrimClip
MoveClip
SplitClip
RippleDelete
SetTransform
SetEffectParameter
RouteAudio
SetColorTransform
```

Operations produce a **CandidateMediaDelta** against an exact snapshot. State commits the accepted delta into a new revision.

This is stronger than ordinary undo and naturally supports agent proposals, partial approval, branching, diffing, collaboration, and reproducibility.

### 3.4 Semantic loss must be explicit

The Transformation Kernel's `LoweringLoss` concept transfers directly.

Any lowering/export/backend conversion should emit a report describing:

- preserved semantics;
- inserted conversions;
- approximations;
- unsupported semantics;
- precision loss;
- editability/reversibility loss;
- provenance loss;
- target-specific assumptions.

A render or export must never silently approximate a declared semantic contract.

This generalizes Declip's current `can_handle()` behavior into a richer contract.

### 3.5 Invalidation is a semantic contract

The graph research uses conservative invalidation: analyses are invalidated unless preservation is explicitly established.

Media transformations should declare which derived products they preserve, invalidate, or conditionally preserve.

Example: changing title color may preserve transcription, scene detection, tracking, stabilization analysis, and audio analysis while invalidating only the title composite and downstream render cache.

This is the foundation for efficient incremental recomputation and safe content-addressed caching.

### 3.6 Admission is distinct from successful execution

The Graph Admission Kernel's key idea is that successful computation is not the same thing as accepted output.

For media:

```text
RenderResult != DeliveryAcceptance
```

A render artifact may be evaluated against an explicit profile such as:

- YouTube SDR delivery;
- YouTube HDR delivery;
- broadcast master;
- archival master;
- social short;
- client review proxy;
- evidentiary/provenance-sensitive media.

An acceptance record should bind to exact artifact content, exact profile/version, exact checkers, and exact assumptions.

Do not reduce assurance to `verified=true`.

A media acceptance vector may include:

```text
structural
codec/container
resolution/frame-rate
duration
frame integrity
A/V sync
color/HDR metadata
audio layout
loudness
caption/accessibility
provenance
nondeterminism disclosure
target-platform compliance
```

### 3.7 Governance is distinct from execution

The Governance Kernel research is especially relevant to AI/media plugins.

A plugin, agent, cloud model, or analysis service should receive only the capabilities it needs, potentially scoped by:

- readable assets;
- writable candidate artifacts;
- network access;
- GPU memory;
- CPU/wall time;
- storage;
- external API cost;
- publish/final-render authority;
- human-approval requirements.

This is a better long-term trust model than loading arbitrary native plugins with ambient process authority.

### 3.8 Resource budgets should be hierarchical

Media execution should understand explicit budgets for:

- latency;
- CPU;
- GPU;
- VRAM;
- RAM;
- storage/cache;
- network bandwidth;
- cloud/API spend;
- energy where useful;
- human-review time where workflows require it.

This provides a principled way to distinguish interactive preview, background preview, analysis, and final-render execution policies.

### 3.9 Multiple time axes are necessary for a truly general kernel

Exact rational media time remains foundational, but the State temporal research suggests it is not sufficient for an all-in-one temporal-media kernel.

The model should distinguish where applicable:

- source/sample time;
- clip-local time;
- sequence/presentation time;
- external timecode/wall-clock time;
- ingest/arrival time;
- revision/transaction time.

This allows one foundation to support both offline editing and live/growing media with late analysis, corrections, retractions, collaborative state, and streaming.

### 3.10 Provenance, verification, trust, and truth are different

A media kernel should preserve distinct information about:

- origin/provenance;
- cryptographic verification;
- trusted authority/attestation;
- synthetic/AI modification;
- factual truth claims.

The kernel can accurately state that a frame is AI-generated, camera-originated, composited, signed, or provenance-complete without pretending to decide whether depicted events are factually true.

## 4. Revised kernel-family architecture

The graph research suggests avoiding one giant media monolith.

The working architecture is:

```text
Applications / editors / agents / automation
                    │
                    ▼
            Media Operation API
                    │
        candidate edits / proposals
                    ▼
┌────────────────────────────────────────────┐
│            Media Kernel Family             │
│                                            │
│  Core ABI                                  │
│    exact time, identity, refs, diagnostics │
│                                            │
│  State                                     │
│    revisions, snapshots, transactions,     │
│    dependency graph, durable artifacts     │
│                                            │
│  Transformation                            │
│    editorial IR, verification, rewrites,   │
│    canonicalization, lowering, loss        │
│                                            │
│  Execution                                 │
│    executable graph, scheduling, memory,   │
│    preview/final policies, backend plans   │
│                                            │
│  Admission                                 │
│    QC/delivery profiles and accepted       │
│    artifact records                        │
│                                            │
│  Governance                                │
│    capabilities, budgets, isolation,       │
│    external/AI effect authorization        │
└────────────────────────────────────────────┘
                    │
                    ▼
      FFmpeg / GPU / GStreamer / cloud / ...
```

**Reasoning is intentionally outside the foundational media kernel.** Declip or another application may use an LLM or deterministic planner to choose edits, but the kernel should not decide creative intent.

## 5. Hard architectural bets

### Very high confidence

1. Exact rational time is foundational.
2. Persistent project state and transient execution graphs are different objects.
3. Editorial IR and execution IR are distinct.
4. Media graph ports/values must be typed.
5. Color semantics are kernel-level, not merely a filter enum.
6. Memory/resource domain must be explicit enough to support zero-copy planning.
7. Temporal dependency must be declared by processing operations.
8. Unsupported/lossy lowering must be explicit and machine-readable.
9. Preview and final render are different execution policies over the same semantics.
10. Durable edit state should be revisioned and transaction-based.
11. Provenance/diagnostics/dependencies should be standard envelopes.
12. A stable C ABI/wire ABI is more important than the internal implementation language.

### High confidence, but staged

- candidate deltas as the primary mutation model;
- typed artifact admission profiles;
- capability-scoped plugin/AI execution;
- hierarchical resource budgets;
- semantic dependency invalidation;
- content-addressed caching built on declared dependencies;
- C2PA export from richer internal provenance.

### Deliberately not hard-coded yet

- Rust as the permanent implementation language;
- Vulkan as the universal GPU execution API;
- libplacebo as the only image-processing implementation;
- OpenTimelineIO as the literal internal IR;
- OpenFX as the native plugin API;
- any one codec library or renderer as canonical.

## 6. User-value test

Kernel work is justified only when it enables concrete outcomes:

- agents can propose large edits without risking the live project;
- exports explain exactly what semantics were preserved or lost;
- destination-specific masters can be certified rather than merely rendered;
- changing one thing recomputes only what actually depends on it;
- preview automatically trades quality for latency while final render preserves intent;
- projects survive renderer, hardware, and application changes;
- AI-generated and AI-modified material remains traceable;
- plugins and agents can operate with narrowly scoped authority and spending limits;
- live, offline, and collaborative media can share one temporal/state foundation.

## 7. Boundary with Declip

The kernel should own **what temporal media computation means**.

Declip should own **what a user or agent wants to accomplish**.

### Kernel examples

- clip/sequence/time semantics;
- transforms and compositing;
- color contracts;
- audio routing primitives;
- typed processing nodes;
- state revisions and candidate deltas;
- render planning;
- resource/capability contracts;
- semantic-loss reporting;
- delivery admission.

### Declip examples

- silence-removal workflow;
- highlight selection;
- caption wording/style strategy;
- social-platform workflow intent;
- transcription provider orchestration;
- TTS/generation model selection;
- storyboard generation;
- agent/MCP/CLI UX.

Declip should remain the first reference consumer and dogfood environment for kernel construction.

## 8. Source research

Internal kernel research:

- https://github.com/dreliq9/Graph-Kernel-Core-ABI
- https://github.com/dreliq9/Ai-Graph-Compiler-Kernel
- https://github.com/dreliq9/Ai-Reasoning-Kernel
- https://github.com/dreliq9/Ai-OS-Graph-Kernel
- https://github.com/dreliq9/Ai-theorem-prover-kernal

External prior art to continue validating against:

- https://opentimelineio.readthedocs.io/
- https://gstreamer.freedesktop.org/documentation/gst-editing-services/
- https://www.mltframework.org/
- https://ffmpeg.org/
- https://libplacebo.org/
- https://opencolorio.org/
- https://openfx.readthedocs.io/
- https://c2pa.org/

## 9. Condensed conclusion

The strongest opportunity is not merely to treat video editing as compilation.

> Treat temporal media as a governed, versioned computational system whose persistent state can be transformed into typed execution graphs, lowered across heterogeneous backends with explicit semantic-loss accounting, executed under resource and authority constraints, and admitted against machine-checkable delivery profiles.

That is the working definition of the foundational media kernel.