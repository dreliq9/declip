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

MCP and CLI are adapters, not architecture centers. Media semantics belong beneath transport layers so the same implementation can be used by MCP, CLI, workflows, and direct Python callers.

See `docs/architecture.md` for the boundary contract and backend capability matrix.

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

`compilers/render_plan.py` owns authoring normalization. It deep-copies projects, resolves `start: "auto"`, makes clip durations explicit, and records duration-probe fallbacks as diagnostics.

FFmpeg and MLT compilation moved into `compilers/`; backend modules are execution adapters. Backend-specific filter lowering lives in `filters/`.

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

### MLT correctness and capability audit

The MLT compiler was audited against MLT's current transition model. MLT transitions combine two distinct tracks; the old Declip compiler emitted same-track transitions with identical `a_track` and `b_track`, which did not faithfully represent adjacent-clip dissolves.

The compiler is now fail-preserving instead of falsely permissive:

- `transition_in` and same-track overlap are rejected until a real two-track transition lowering exists
- explicit clip duration is reflected in finite playlist entry spans
- timeline gaps are preserved
- dedicated audio is mixed as a distinct track
- reverse, freeze-frame, positioned clips, opacity, unsupported filters, and unlowered speech ducking are rejected explicitly
- project includes are not silently ignored

`project_ops.prepare_project()` now checks both normalized backend capability matrices. `auto` errors when neither backend can preserve the project instead of selecting a renderer that would drop semantics.

### Adapter implementation ownership removed

The largest MCP implementation modules are thin adapters:

- `mcp/edit_tools.py` → reusable `declip.edit`
- `mcp/quick_tools.py` → reusable `declip.quick`
- `mcp/pipeline_tools.py` → reusable `declip.pipelines.production`
- `mcp/project_tools.py` → reusable `declip.project_ops`
- advanced batch rendering → `declip.project_ops.batch_render`

The CLI was similarly consolidated. `cli_adapter.py` owns the Click command surface and delegates project preparation, quick operations, processing, generation, analysis, and workflows to core modules. `declip.cli:main` remains a compatibility shim, and the package script points directly to `declip.cli_adapter:main`.

Boundary tests enforce that thin MCP/CLI adapters do not own subprocess execution and enumerate the preserved CLI command/workflow surface.

The move exposed and fixed additional bugs: basic+advanced color grading no longer performs an unused extra encode; image-overlay sizing uses the probed main-video width; freeze-frame generation no longer limits the final output to one frame; storyboard narration is explicitly mixed rather than represented as an FFmpeg timeline audio track that the old backend ignored.

### Production-pipeline hardening

The extracted production pipeline also received correctness fixes:

- center-crop scales to cover before cropping, avoiding invalid crop widths on narrow sources
- platform export handles video without audio instead of always applying loudness filters
- storyboard accepts FFmpeg-style `fade` as schema `dissolve` and validates transitions before project construction
- TTS provider calls work from synchronous callers even when an event loop is already active
- missing or stalled `ffprobe` no longer turns a successful TTS generation into a pipeline failure
- storyboard narration/music mixing handles source videos with no existing audio stream

### Typed core results

Probe/trim/concat/thumbnail result models live in `declip.results`; `declip.mcp.types` re-exports them for compatibility. Production pipelines return a transport-neutral `PipelineResult` internally while MCP preserves the previous human-readable text surface.

### Dependency/version drift

`declip.__version__` is synchronized with `pyproject.toml` at 0.8.0. Optional analysis dependencies are explicit extras:

- `analysis`: PySceneDetect
- `vad`: Silero VAD + torch
- `full-analysis`: both

## Test posture

The branch contains regression coverage for:

- render-plan normalization and legacy API compatibility
- FFmpeg input-option scoping
- multi-clip watermarks
- reverse-audio parity
- freeze-frame compilation and file-edit behavior
- still-image duration handling
- manual timeline gap/overlap routing
- dedicated-audio backend selection
- no-compatible-backend failures
- MLT normalization, finite clip spans, gap preservation, and capability rejection
- transport-neutral result compatibility
- MCP/CLI adapter boundaries and CLI command-surface preservation
- single-pass combined color grading
- project validation of filter assets
- ASS generation, transition aliases, and reframe filter construction

Executable synthetic-media integration tests are also committed:

- FFmpeg two-clip concat
- FFmpeg dissolve timing
- FFmpeg still-image duration
- FFmpeg multi-clip watermark render
- MLT bounded/trimmed smoke render when `melt` is available

The initial compiler extraction was exercised with a 12-test local harness. The current environment cannot clone and execute the complete GitHub branch checkout, so the expanded committed suite has not been run end-to-end here. That is now the principal verification gap before merge; the missing coverage itself has been written.

## Remaining engineering work

The broad architecture/hardening pass is complete. Remaining work is narrower:

1. **Execute the full committed suite in a normal checkout.** This is the immediate pre-merge gate. Run unit tests plus the renderer integration fixtures with FFmpeg; run the MLT smoke fixture wherever `melt` is installed.
2. **Implement real MLT transition lowering if MLT transition support is required.** The current compiler correctly rejects it rather than emitting invalid same-track XML. A future implementation should construct overlapping A/B tracks in accordance with MLT's model.
3. **Richer typed results.** Analysis, media, generation, edit, and project operations still use human-readable strings in several core paths. Add domain-specific result models where agents benefit from structured fields.
4. **Resolve speed/duration semantics.** The v1 schema still has ambiguity between source span, explicit timeline duration, and speed filters. Resolve this in the normalized IR before expanding retiming features.
5. **Generation argument schemas.** Live model discovery exists, but model-specific fal.ai parameter schemas remain curated/hardcoded for selected families.

## Research items still genuinely deferred

- WhisperX alignment/diarization for precision transcription
- basic-pitch polyphonic audio-to-MIDI
- face/object-aware smart reframing
- gifski output backend
- richer waveform/marker visualization

## Priority

Do not add another broad feature wave before the committed suite has been executed in a normal checkout. After that verification gate, the architecture is sufficiently consolidated for feature development to resume without reintroducing the old transport/backend boundary problems.
