# declip

Declarative video editing — JSON in, video out. Declip is an AI-native media engine with CLI and MCP adapters, not an MCP implementation with video code embedded inside it.

## What it does

A Declip project describes a timeline, clips, transitions, filters, audio, and output settings as structured data. Declip normalizes that project into a render plan, compiles the plan for a backend, and executes it.

Current surfaces:

- **Python library** for projects, operations, analysis, and workflow recipes
- **CLI** (`declip`) for rendering and one-shot media operations
- **MCP server** (`declip-mcp`) for AI agents
- **FFmpeg compiler/backend** for single-track projects
- **MLT compiler/backend** for compositing, dedicated audio tracks, and GUI round-tripping to Shotcut/Kdenlive
- **Workflow library** for ingest, cutdown, speech cleanup, beat sync, vertical conversion, and review
- **Generation integration** with a cached live fal.ai model catalog

## Architecture

The core boundary is deliberately transport-neutral:

```text
CLI / MCP / Python
        |
        v
Project schema + capability APIs + typed results
        |
        v
Render-plan normalization
        |
        v
Backend compiler (FFmpeg / MLT)
        |
        v
Execution backend
        |
        v
Media output
```

`src/declip/mcp/` is an adapter layer. Backend-native filter construction lives in `src/declip/filters/`; compilation lives in `src/declip/compilers/`; process execution lives in `src/declip/backends/`. See `docs/architecture.md` for the boundary rules.

## Install

```bash
pip install -e .
```

Requires Python 3.11+ and FFmpeg in `PATH`. Tesseract is required for the legacy OCR path.

Optional analysis accelerators are explicit extras:

```bash
pip install -e '.[analysis]'       # PySceneDetect
pip install -e '.[vad]'            # Silero VAD + torch
pip install -e '.[full-analysis]'  # both
```

The analysis module retains fallbacks when these extras are absent.

## Quickstart — render a project

```bash
declip render examples/simple_cut.json
```

Example:

```json
{
  "version": "1.0",
  "settings": {"resolution": [1920, 1080], "fps": 30},
  "timeline": {
    "tracks": [{
      "id": "main",
      "clips": [
        {"asset": "a.mp4", "start": 0, "trim_in": 0, "trim_out": 3.0},
        {"asset": "b.mp4", "start": "auto", "trim_in": 0, "trim_out": 4.0,
         "transition_in": {"type": "dissolve", "duration": 1.0}}
      ]
    }]
  },
  "output": {"path": "out.mp4", "format": "mp4", "codec": "h264", "quality": "medium"}
}
```

`start: "auto"` is resolved by the render-plan compiler, including transition overlap. Backends receive explicit starts and durations instead of independently guessing timeline semantics.

## Quickstart — analyze a file

```bash
declip probe input.mp4
declip detect-scenes input.mp4
declip detect-silence input.mp4
declip loudness input.mp4
declip review input.mp4 -o report/
```

Commands support `--json` where applicable for structured output.

## MCP server

```bash
declip-mcp
```

The MCP server exposes Declip capabilities to compatible agents. Structured result models live in `declip.results` and are re-exported from `declip.mcp.types` for backward compatibility; callers do not need MCP to consume the core result contracts.

### YouTube-MCP clip-plan handoff

Declip can import the editor-neutral materialized manifest from `dreliq9/youtube-mcp-v2` using `declip_project_from_clip_plan`. The importer verifies each materialized asset's SHA-256 by default, preserves manifest order, maps each source-trimmed asset to a native clip with `trim_in=0` and `trim_out=duration_s`, and writes a `<project>.sources.json` provenance sidecar.

Import does not render automatically. Review or edit the resulting project, then call `declip_render`.

## Backend selection

Automatic selection is conservative. FFmpeg currently handles one unpositioned video track with clip audio. Projects with multiple video tracks, positioned overlays, or dedicated timeline audio tracks route to MLT so semantics are not silently discarded.

## Status

Active development. `AUDIT.md` tracks the current hardening state and `docs/architecture.md` defines the intended boundaries.

## License

MIT. See `LICENSE`.
