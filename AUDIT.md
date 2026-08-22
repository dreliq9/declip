# Declip Audit — Current State and Hardening Roadmap

Updated 2026-08-22. This supersedes the March 2026 audit as the source of truth for current implementation status.

The original research was useful, but many items it listed as future work were subsequently implemented. This audit separates completed capability work from current correctness and architecture work.

## Current product boundary

Declip is a declarative media engine with multiple control surfaces.

```text
CLI / MCP / Python
        ↓
Schema + reusable capabilities + typed results
        ↓
Normalized render plan
        ↓
FFmpeg / MLT compiler
        ↓
Execution backend
```

MCP is an adapter, not the architecture center. Media semantics belong beneath transport layers so the same implementation can be used by MCP, CLI, workflows, and direct Python callers.

See `docs/architecture.md` for the boundary contract.

## Capabilities already implemented

The following items from the old audit are no longer roadmap work:

- project-level `start: "auto"` sequencing
- expanded FFmpeg xfade transition set
- audio crossfades for FFmpeg transition renders
- `amix normalize=0` in sidechain mixing
- smart/keyframe-aware trim and smart concat
- PySceneDetect integration with fallback
- black-frame and frozen-frame review checks
- word-level Whisper transcription
- ASS auto-captions and burn-in
- edge-tts voiceover
- multi-platform export
- storyboard assembly
- optical-flow slow motion (`minterpolate`)
- advanced color balance / temperature / auto-levels
- chunked long-video reverse
- two-pass loudness normalization
- Silero VAD with fallback
- ingest, cutdown, speech-cleanup, beat-sync, vertical, and review workflows
- live cached fal.ai model discovery
- structured probe/trim/concat/thumbnail results

## Hardening completed on `hardening/compiler-consolidation`

### Render-plan and compiler boundary

`compilers/render_plan.py` now owns authoring normalization. It deep-copies projects, resolves `start: "auto"`, makes clip durations explicit, and records duration-probe fallbacks as diagnostics.

FFmpeg and MLT compilation moved into `compilers/`; backend modules are now execution adapters. Backend-specific filter lowering lives in `filters/`.

The legacy `Project.resolve_auto_starts()` API delegates to the canonical render-plan logic instead of maintaining a second timeline algorithm.

### FFmpeg correctness

The hardening pass fixes several silent semantic losses:

- all clip input paths scope `-ss`/`-t` before the intended `-i`
- multi-clip watermarks are compiled instead of disappearing
- reverse applies to audio and video in multi-clip projects
- freeze-frame semantics use shared lowering instead of a single-clip special case
- hard cuts use real concat rather than a 1 ms fake transition
- still-image assets are looped for their declared shot duration
- dedicated timeline audio routes away from FFmpeg instead of being dropped
- arbitrary manual gaps/overlaps route away from the concat/xfade compiler instead of being collapsed

### MCP implementation ownership removed

The largest MCP implementation modules are now thin adapters:

- `mcp/edit_tools.py` → reusable `declip.edit`
- `mcp/quick_tools.py` → reusable `declip.quick`
- `mcp/pipeline_tools.py` → reusable `declip.pipelines.production`
- `mcp/project_tools.py` → reusable `declip.project_ops`
- advanced batch rendering → `declip.project_ops.batch_render`

The move exposed and fixed additional bugs: basic+advanced color grading no longer performs an unused extra encode; image-overlay sizing uses the probed main-video width; freeze-frame generation no longer limits the final output to one frame; storyboard narration is explicitly mixed rather than represented as an FFmpeg timeline audio track that the old backend ignored.

Analysis/media/generation MCP modules are mostly formatting adapters around existing core `analyze.py`, `ops.py`, `generate.py`, and `fetch_models.py` implementations.

### Typed core results

Probe/trim/concat/thumbnail result models now live in `declip.results`; `declip.mcp.types` re-exports them for compatibility. Production pipelines return a transport-neutral `PipelineResult` internally while MCP preserves the previous human-readable text surface.

### Dependency/version drift

`declip.__version__` is synchronized with `pyproject.toml` at 0.8.0. Optional analysis dependencies are explicit extras:

- `analysis`: PySceneDetect
- `vad`: Silero VAD + torch
- `full-analysis`: both

## Test posture

The branch adds regression coverage for:

- render-plan normalization and legacy API compatibility
- FFmpeg input-option scoping
- multi-clip watermarks
- reverse-audio parity
- freeze-frame compilation and file-edit behavior
- still-image duration handling
- manual timeline gap/overlap routing
- dedicated-audio backend selection
- MLT normalization
- transport-neutral result compatibility
- adapter/core import boundaries
- single-pass combined color grading
- project validation of filter assets
- ASS generation and storyboard transition aliases

A local compiler harness passed 12 focused tests during the initial compiler extraction. The repository itself has no configured CI runner, so the expanded committed suite still needs to be run in a checkout with the project dependencies and external media tools installed.

## Remaining hardening work

The architecture is now pointed in the intended direction. Remaining work is narrower:

1. **CLI de-duplication.** `cli.py` still contains legacy command implementations that overlap the new `quick`, `edit`, and `project_ops` capability APIs. Migrate commands without changing the CLI surface.
2. **Richer typed results.** Analysis, media, generation, edit, and project operations still use human-readable strings in several core paths. Add domain-specific result models where agents benefit from structured fields.
3. **Synthetic-media integration tests.** Run end-to-end renders against generated fixtures to validate actual FFmpeg graphs, not only command construction. Add MLT integration coverage where `melt` is available.
4. **MLT transition audit.** Validate same-track and multi-track transition semantics independently; compiler isolation now makes this tractable.
5. **Speed/duration semantics.** The v1 schema still has an ambiguity between source span, explicit timeline duration, and speed filters. Resolve this in the normalized IR before expanding retiming features.
6. **Generation argument schemas.** Live model discovery exists, but model-specific fal.ai parameter schemas are still curated/hardcoded for selected families.

## Research items still genuinely deferred

- WhisperX alignment/diarization for precision transcription
- basic-pitch polyphonic audio-to-MIDI
- face/object-aware smart reframing
- gifski output backend
- richer waveform/marker visualization

## Priority

The next engineering pass should be CLI de-duplication plus executable synthetic-media integration tests. Broad feature accumulation can resume after those close the remaining duplicate execution paths and establish end-to-end render confidence.
