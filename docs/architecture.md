# Declip Architecture

## Governing boundary

Declip is a media engine. MCP and CLI are adapters to that engine.

No transport layer should own media semantics that another transport cannot reuse. A feature is complete only when its implementation is callable beneath MCP/CLI and its adapter is thin.

## Layers

### 1. Schema and capability layer

`schema.py`, `ops.py`, `analyze.py`, `generate.py`, `workflows/`, and `results.py` define user-facing media concepts and reusable operations.

Rules:

- no MCP imports
- no Click imports
- structured inputs and structured return values where practical
- subprocess details may exist in low-level operations, but transport formatting does not

### 2. Render-plan normalization

`compilers/render_plan.py` converts the convenient authoring schema into explicit backend input.

It owns:

- resolving `start: "auto"`
- resolving effective clip durations
- recording duration-probe fallbacks as diagnostics
- deep-copying rather than mutating caller-owned project objects

A backend compiler must not invent its own fallback timeline math.

### 3. Filters

`filters/` lowers schema-level effects to backend-native filter descriptions.

It does not execute processes and does not know about MCP/CLI output conventions.

### 4. Compilers

`compilers/ffmpeg.py` and `compilers/mlt.py` lower normalized projects to executable backend representations.

Compilers own:

- input option ordering
- stream graph construction
- transition lowering
- watermark/overlay input mapping
- codec/backend syntax

Compilers do not run FFmpeg or melt.

### 5. Backends

`backends/` executes compiler output and reports progress through `OutputManager`.

A backend should be small enough that most correctness can be tested without launching the external renderer.

### 6. Adapters

`cli.py` and `mcp/` validate transport-specific input, call core capabilities, and serialize results.

They should not become alternative implementations of Declip features.

## Backend selection

Backend selection is fail-preserving rather than optimistic.

FFmpeg is selected only when its compiler can preserve the project semantics. Multi-track compositing, positioned tracks, and dedicated timeline audio currently route to MLT. A forced unsupported backend returns a compilation error instead of dropping content.

## Compatibility policy

Existing public imports from `declip.backends.ffmpeg`, `declip.backends.mlt`, and `declip.mcp.types` remain available as compatibility re-exports while implementation ownership moves downward.

This lets architecture improve without making CLI/MCP consumers migrate in lockstep.

## Testing policy

Compiler correctness is primarily unit-testable. Regression tests should inspect generated argv/XML for semantic invariants before integration tests invoke FFmpeg/MLT.

Required regression categories:

- input option scoping (`-ss`/`-t` before the intended `-i`)
- auto-start and transition overlap normalization
- multi-clip watermarks
- reverse video + audio parity
- freeze-frame behavior in single and multi-clip projects
- backend-selection preservation of dedicated audio tracks
- transport-neutral result imports

Synthetic-media integration tests are useful as a second layer, but compiler unit tests are the first defense against silent render regressions.
