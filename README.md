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
