# Declip Architecture

## Governing boundary

Declip is a media engine. MCP and CLI are adapters to that engine.

No transport layer should own media semantics that another transport cannot reuse. A feature is complete when its implementation is callable beneath MCP/CLI and its adapter is thin.

## Layers

### 1. Schema and capability layer

Core reusable modules define user-facing media concepts and operations:

- `schema.py` — public project/timeline contract
- `analyze.py` — media analysis
- `ops.py` — shared low-level processing operations
- `quick.py` — structured probe/trim/concat/thumbnail operations
- `edit.py` — file-based editing capabilities
- `project_ops.py` — project validation/preparation/render/export/asset operations
- `generate.py` + `fetch_models.py` — AI generation capabilities and model discovery
- `pipelines/` — end-to-end production pipelines
- `workflows/` — reusable editing workflow recipes
- `results.py` — transport-neutral result contracts

Rules:

- no MCP imports
- no Click imports
- structured inputs/results where they materially help callers
- subprocess details may exist in low-level capabilities, but transport formatting and registration do not

### 2. Render-plan normalization

`compilers/render_plan.py` converts the convenient authoring schema into explicit backend input.

It owns:

- resolving `start: "auto"`
- resolving effective clip durations
- recording duration-probe fallbacks as diagnostics
- deep-copying rather than mutating caller-owned project objects

A backend compiler must not invent its own fallback timeline math. The legacy mutating `Project.resolve_auto_starts()` method delegates to this layer for compatibility.

### 3. Filters

`filters/` lowers schema-level effects to backend-native filter descriptions.

It does not execute processes and does not know about MCP/CLI output conventions.

### 4. Compilers

`compilers/ffmpeg.py` and `compilers/mlt.py` lower normalized projects to executable backend representations.

Compilers own:

- input option ordering
- stream graph/XML construction
- transition lowering
- watermark/overlay input mapping
- codec/backend syntax
- explicit capability rejection when a backend cannot preserve timeline semantics

Compilers do not perform the final FFmpeg or melt render.

### 5. Backends

`backends/` executes compiler output and reports progress through `OutputManager`.

A backend should be small enough that most correctness can be tested without launching the external renderer.

### 6. Adapters

`mcp/` validates MCP-specific inputs, calls core capabilities, and serializes results. Edit, quick, project, and production-pipeline MCP modules are thin wrappers around core modules; analysis/media/generation adapters primarily format existing core results.

`cli_adapter.py` owns the Click command surface but delegates project preparation, quick operations, processing operations, generation, analysis, and workflows to core modules. The historical `declip.cli:main` import remains as a compatibility shim, while the package entry point resolves directly to `declip.cli_adapter:main`.

Neither thin adapter layer owns subprocess execution. Boundary tests enforce this invariant and enumerate the CLI command surface.

## Backend capability contract

Backend selection is fail-preserving rather than optimistic. Selection happens after normalization so both compilers inspect the same explicit timeline.

### FFmpeg

The FFmpeg compiler currently accepts one sequential, unpositioned video track with clip audio. It supports hard cuts and its declared xfade transitions, shared video/audio filters, reverse, freeze-frame, and per-clip watermarks. Still-image inputs are explicitly looped for the normalized clip duration.

It rejects dedicated timeline audio, arbitrary manual timeline gaps/overlaps, positioned clips, multi-track composition, and other semantics it cannot preserve.

### MLT

The MLT compiler is deliberately conservative. It supports finite multi-track timelines, explicit gaps, dedicated audio tracks, and its explicitly lowered filter subset. It rejects semantics that the old implementation previously approximated or silently lost, including:

- `transition_in` and same-track overlap until a real two-track MLT transition lowering exists
- positioned clips until position and sizing are represented explicitly in the IR
- clip opacity, reverse, and freeze-frame where no faithful MLT lowering exists yet
- unsupported clip/audio filters
- speech ducking requests that have not been lowered

This restriction is intentional. MLT transitions combine frames from distinct A/B tracks; emitting a transition with identical `a_track` and `b_track` does not preserve an adjacent same-track dissolve. The compiler therefore fails rather than emitting semantically false XML. Current MLT documentation demonstrates transitions across separate tracks. 

### No-compatible-backend behavior

`project_ops.prepare_project()` checks both capability matrices against the normalized project. If neither backend can preserve the requested semantics, `auto` returns an explicit error instead of selecting the least-wrong renderer.

Forced backend selection is subject to the same rule.

## Planned foundational-kernel boundary

The current Declip compiler architecture is now treated as a proving ground for a lower, application-independent **foundational media kernel**. The planning record is in:

- `docs/media-kernel-research.md`
- `docs/media-kernel-construction-plan.md`

The intended long-term boundary is:

```text
Declip
  user/agent intent, workflows, analysis/generation orchestration
        │
        ▼
Foundational Media Kernel
  exact temporal semantics, persistent revisions, typed media IR,
  transformation/lowering, execution planning, semantic-loss accounting,
  resource/authority contracts, artifact admission
        │
        ▼
FFmpeg / GPU providers / GStreamer / cloud / other execution backends
```

The kernel should eventually live in its own repository. Declip remains its first reference client and should migrate incrementally rather than through a rewrite.

The governing split is:

> **Kernel:** what temporal media computation means and what guarantees hold.  
> **Declip:** what a user or agent wants to accomplish with those primitives.

Until kernel contracts are implemented and conformance-tested, the current Declip schema/render-plan/compiler boundaries remain authoritative for Declip itself.

## Compatibility policy

Existing public imports from `declip.backends.ffmpeg`, `declip.backends.mlt`, `declip.mcp.types`, and `declip.cli:main` remain available as compatibility re-exports/shims while implementation ownership moves downward.

Existing MCP tool names and the CLI command/flag surface are preserved while implementations move to reusable capability modules.

## Testing policy

Compiler correctness is primarily unit-testable. Regression tests inspect generated argv/XML, transport-neutral contracts, adapter boundaries, and negative capability cases before integration tests invoke FFmpeg/MLT.

Required regression categories include:

- input option scoping (`-ss`/`-t` before the intended `-i`)
- auto-start and transition overlap normalization
- explicit timeline gap/overlap routing
- still-image duration handling
- multi-clip watermarks
- reverse video + audio parity
- freeze-frame behavior
- backend-selection preservation of dedicated audio tracks
- explicit rejection when neither backend can preserve semantics
- MLT rejection of invalid same-track transition lowering
- transport-neutral result imports
- absence of subprocess ownership in thin MCP/CLI adapters
- CLI command-surface preservation
- production reframe and transition normalization

Synthetic-media integration tests are the second layer. The repository contains executable FFmpeg integration fixtures for concat, dissolve timing, still images, and multi-clip watermarks, plus an MLT smoke render that runs when `melt`, FFmpeg, and ffprobe are installed. These tests skip cleanly when the required external renderer is unavailable.
