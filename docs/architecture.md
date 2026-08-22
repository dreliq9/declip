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
- `project_ops.py` — project validation/render/export/asset operations
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

`mcp/` validates MCP-specific inputs, calls core capabilities, and serializes results. The major edit, quick, project, and production-pipeline MCP modules are thin wrappers around core modules.

`cli.py` is also an adapter by design, but it still contains legacy duplicate implementations. Removing that duplication is the next boundary cleanup; it should reuse the same core modules without changing command names or flags.

## Backend selection

Backend selection is fail-preserving rather than optimistic.

FFmpeg is selected only when its compiler can preserve the project semantics. It currently accepts one sequential, unpositioned video track with clip audio. Dedicated timeline audio, arbitrary manual timeline gaps/overlaps, positioned clips, and multi-track composition route to MLT. A forced unsupported FFmpeg backend returns a compilation error instead of dropping or collapsing content.

Still-image inputs are explicitly looped by the FFmpeg compiler for their normalized clip duration.

## Compatibility policy

Existing public imports from `declip.backends.ffmpeg`, `declip.backends.mlt`, and `declip.mcp.types` remain available as compatibility re-exports while implementation ownership moves downward.

Existing MCP tool names and principal argument signatures are preserved while implementations move to reusable capability modules.

## Testing policy

Compiler correctness is primarily unit-testable. Regression tests inspect generated argv/XML and adapter boundaries before integration tests invoke FFmpeg/MLT.

Required regression categories include:

- input option scoping (`-ss`/`-t` before the intended `-i`)
- auto-start and transition overlap normalization
- explicit timeline gap/overlap routing
- still-image duration handling
- multi-clip watermarks
- reverse video + audio parity
- freeze-frame behavior
- backend-selection preservation of dedicated audio tracks
- transport-neutral result imports
- absence of subprocess ownership in thin MCP adapters

Synthetic-media integration tests remain the required second layer for actual render verification.
