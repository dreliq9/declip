# Declip Audit — Current State and Hardening Roadmap

Updated 2026-08-22. This supersedes the March 2026 audit as the source of truth for current implementation status.

The original research was directionally useful, but many items it listed as future work were subsequently implemented. Keeping completed work in the active roadmap made the repository look less mature than it is and obscured the real engineering risks.

## Current product boundary

Declip is a declarative media engine with multiple control surfaces.

```text
CLI / MCP / Python
        ↓
Schema + capabilities + typed results
        ↓
Normalized render plan
        ↓
FFmpeg / MLT compiler
        ↓
Execution backend
```

MCP is not the architecture center. It is one adapter to the same capability layer used by CLI, workflows, and direct Python callers.

See `docs/architecture.md` for the boundary contract.

## Capabilities already implemented

The following items from the old audit are no longer roadmap work:

- project-level `start: "auto"` sequencing
- expanded FFmpeg xfade transition set
- audio crossfades for FFmpeg transition renders
- watermark rendering for the single-clip path
- `amix normalize=0` in sidechain mixing
- smart/keyframe-aware trim option
- smart concat/stream-copy path in MCP quick tools
- PySceneDetect integration with fallback
- black-frame and frozen-frame review checks
- word-level Whisper transcription support
- auto-caption ASS generation and burn-in
- edge-tts voiceover support
- multi-platform export
- storyboard assembly
- optical-flow slow motion (`minterpolate`)
- advanced color balance / temperature / auto-levels
- chunked long-video reverse
- two-pass loudness normalization
- Silero VAD support with fallback
- workflow library + CLI + MCP surfaces for ingest, cutdown, speech cleanup, beat sync, vertical, and review
- live cached fal.ai model discovery
- structured MCP results for probe/trim/concat/thumbnail

## Hardening findings addressed by `hardening/compiler-consolidation`

### Compiler/backend separation

The branch introduces `compilers/render_plan.py`, backend-specific compiler modules, backend-specific filter lowerers, and thin execution backends. Existing backend imports remain available for compatibility.

### FFmpeg input-option scoping

The no-transition renderer still emitted `-t` after `-i` even though the transition path had already been fixed. The compiler now uses one input-argument path for every project shape, keeping `-ss`/`-t` attached to the intended input.

### Multi-clip watermark preservation

Watermarks previously existed only in the single-clip command path. The compiler now allocates watermark inputs and lowers overlays per clip before timeline composition.

### Reverse and freeze-frame parity

Reverse audio and freeze-frame behavior are now lowered from shared clip semantics rather than being single-clip special cases.

### Dedicated audio-track safety

Automatic FFmpeg selection now rejects projects with dedicated timeline audio so those tracks route to MLT instead of being silently discarded.

### Explicit normalization diagnostics

Duration probing and `start: "auto"` resolution now happen in a deep-copied render plan. Probe fallbacks become structured warnings surfaced by execution backends.

### Typed results moved below MCP

Probe/trim/concat/thumbnail result contracts now live in `declip.results`; `declip.mcp.types` re-exports them for compatibility.

### Dependency and version drift

`declip.__version__` is synchronized with `pyproject.toml` at 0.8.0. PySceneDetect and Silero VAD are represented as explicit optional extras (`analysis`, `vad`, `full-analysis`).

## Test posture

The branch adds compiler-focused regression coverage for render-plan normalization, FFmpeg option ordering, multi-clip watermarks, reverse-audio parity, freeze frames, dedicated-audio backend selection, MLT normalization, and transport-neutral result compatibility.

These are compiler tests and do not require external renderer binaries. Synthetic-media integration tests remain a useful second layer.

## Remaining architectural work

The repository is now pointed at the correct boundary, but not every older MCP tool has been migrated yet.

Highest-priority follow-ups:

1. Move remaining direct FFmpeg implementations from `mcp/edit_tools.py` into capability modules or shared operations, leaving MCP wrappers thin.
2. Move production pipeline implementations from `mcp/pipeline_tools.py` into `pipelines/` and return structured core results.
3. Convert remaining string-returning MCP tools to transport-neutral typed result models.
4. Add synthetic-media end-to-end tests for FFmpeg and, where available, MLT.
5. Audit MLT transition semantics independently; compiler separation now makes that work isolated and testable.
6. Make model-specific generation argument schemas discoverable rather than hardcoded for selected fal.ai endpoints.

## Research items still genuinely deferred

- WhisperX alignment/diarization for precision transcription
- basic-pitch polyphonic audio-to-MIDI
- face/object-aware smart reframing
- gifski output backend
- richer waveform/marker visualization

## Priority

Do not resume broad feature accumulation until the remaining MCP implementation ownership is moved beneath the adapter layer and compiler integration tests are in place. The current feature set is already broad; reliability and reusable contracts now have the higher marginal value.
