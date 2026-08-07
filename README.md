# declip

Declarative video editing — JSON in, video out. Plus an MCP server so AI agents can drive a real editor.

## What it does

You write a project as JSON (timeline, clips, transitions, filters, output) and `declip` renders it via FFmpeg. No GUI, no NLE, no clicks — just structured data and a command.

It also ships:

- A **CLI** with quick utilities (probe, trim, concat, thumbnail, scene detection, silence detection, loudness, transcription, review reports)
- An **MCP server** (`declip-mcp`) that exposes the toolbox to MCP-compatible AI agents (Claude Code, Cursor, etc.)
- An **MLT export** path for round-tripping into Shotcut / Kdenlive when you want a GUI

## Install

```bash
pip install -e .
```

Requires Python 3.11+, FFmpeg in `PATH`, and Tesseract for OCR features.

## Quickstart — render a project

```bash
declip render examples/simple_cut.json
```

The schema covers tracks, clips, trims, filters (fades, transitions, drawtext, color), and output settings. See `examples/` for working samples.

## Quickstart — analyze a file

```bash
declip probe input.mp4              # codec, resolution, duration, streams
declip detect-scenes input.mp4      # scene boundary timestamps
declip detect-silence input.mp4     # silence ranges
declip loudness input.mp4           # integrated LUFS
declip review input.mp4 -o report/  # full review pack: frames + scenes + silence
```

All commands accept `--json` for structured NDJSON output, which is what the MCP server uses internally.

## MCP server

```bash
declip-mcp
```

Then point your MCP client at the binary. Tools are grouped: `media_tools` (probe, thumbnail, frames), `analysis_tools` (scenes, silence, loudness, transcription), `edit_tools` (trim, concat, filters), `quick_tools` (one-shots), `pipeline_tools`, `generate_tools`, `advanced_tools`, and `project_tools`.

### YouTube-MCP clip-plan handoff

Declip can consume the editor-neutral materialized manifest produced by `dreliq9/youtube-mcp-v2`:

```text
YouTube research
  -> corpus.clip_plan
  -> media.materialize
  -> youtube-mcp.materialized-clip-plan/v1
  -> declip_project_from_clip_plan
  -> native Declip project.json
  -> inspect/edit
  -> declip_render
```

The MCP tool:

```text
declip_project_from_clip_plan(
  manifest_path,
  project_path,
  output_path="output.mp4",
  width=1920,
  height=1080,
  fps=30,
  transition="none",
  transition_duration=0.5,
  verify_hashes=true,
  overwrite=false
)
```

The importer verifies each materialized asset's SHA-256 by default, preserves manifest order, and maps each already-trimmed asset to a normal Declip clip with `trim_in=0` and `trim_out=duration_s`. It also writes `<project>.sources.json` containing the original YouTube IDs/URLs, source time ranges, clip hashes, and youtube-mcp plan/materialization revisions.

Import does **not** render automatically. This keeps the project reviewable and lets the agent or user change transitions, titles, music, filters, pacing, or output settings before calling `declip_render`.

## Project schema (gist)

```json
{
  "version": "1.0",
  "settings": { "resolution": [1920, 1080], "fps": 30 },
  "timeline": {
    "tracks": [{
      "id": "main",
      "clips": [
        {"asset": "a.mp4", "start": 0,        "trim_in": 0, "trim_out": 3.0},
        {"asset": "b.mp4", "start": "auto",   "trim_in": 0, "trim_out": 4.0,
         "transition_in": {"type": "dissolve", "duration": 1.0}}
      ]
    }]
  },
  "output": {"path": "out.mp4", "format": "mp4", "codec": "h264", "quality": "medium"}
}
```

`start: "auto"` chains clips end-to-end, accounting for transitions.

## Status

Active development. See `CHANGELOG.md` for version history and `AUDIT.md` for the research-backed roadmap (existing-tool fixes + planned capabilities).

## License

MIT. See `LICENSE`.
