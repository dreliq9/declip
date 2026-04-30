# declip workflows

Reusable end-to-end recipes built from declip's primitives. Each workflow is available three ways — pick whichever fits the caller:

1. **Python library** — `from declip.workflows import cutdown; cutdown.run(...)` returns a typed Pydantic result. Best for scripting and other Python tools.
2. **CLI** — `declip workflow cutdown ...`. Best for shell pipelines and one-off runs.
3. **MCP** — `declip_workflow_cutdown(...)`. Returns the same typed result via the MCP protocol's `structuredContent`. Best for AI agents.

The bash scripts in `scripts/` are now 3-line `exec` wrappers around the CLI; preserved for muscle memory.

## Available workflows

| Workflow | What it does | Inputs | Output |
|---|---|---|---|
| [ingest](ingest.md) | Normalize loudness + probe + optional auto-grade | any video | `<name>.normalized.mp4` + `metadata.json` |
| [cutdown](cutdown.md) | Long source → short highlight reel via scene detection | one video, target duration | `<name>.cutdown.mp4` + `project.json` |
| [speech-cleanup](speech-cleanup.md) | Talking head → jump-cut edit (drop silences, optional captions) | one video with speech | `<name>.cleaned.mp4` + `.srt` + `project.json` |
| [beat-sync](beat-sync.md) | Cut video to music beat grid | video + music | `<name>.beat.mp4` + `project.json` |
| [vertical](vertical.md) | 16:9 (or other) → 9:16 reformat with crop or pad | any video | `<name>.vertical.mp4` |
| [review](review.md) | QA report pack: probe + scenes + silence + beats + frame strips | any rendered video | `<dir>/` with `REVIEW.md` and assets |

## Running

### CLI

```bash
declip workflow ingest input.mp4 -o normalized.mp4
declip workflow cutdown long.mp4 --target 60 -o highlight.mp4
declip workflow speech-cleanup interview.mp4 --burn-captions
declip workflow beat-sync footage.mp4 song.mp3 --stride 4
declip workflow vertical wide.mp4 --mode crop
declip workflow review final.mp4 -o review/
```

Pass `--json` to the parent `declip` group for NDJSON output:

```bash
declip --json workflow cutdown input.mp4 --target 60
```

### Python library

```python
from declip.workflows import cutdown

result = cutdown.run(
    input_path="input.mp4",
    target_seconds=60,
    output_path="highlight.mp4",
)
print(result)                       # human-readable summary
print(result.duration_seconds)      # 57.5
print(result.segments)              # list[CutdownSegment]
result.model_dump_json()            # full JSON
```

Every workflow returns a `WorkflowResult` subclass with `success`, `error`, `output_path`, `duration_seconds`, plus workflow-specific fields. `__str__` produces the same summary the CLI prints.

### MCP

The MCP server registers `declip_workflow_<name>` tools alongside the per-primitive tools. Agents call one structured tool and get a typed result back via `structuredContent` — no string parsing of intermediate steps.

## Composition

Workflows compose. Common chains:

- **Ingest then cut down:**
  ```bash
  declip workflow ingest raw.mp4 -o clean.mp4
  declip workflow cutdown clean.mp4 --target 30
  ```
- **Cut down then review:**
  ```bash
  declip workflow cutdown long.mp4 -o short.mp4
  declip workflow review short.mp4 -o qa/
  ```
- **Speech-cleanup then vertical:**
  ```bash
  declip workflow speech-cleanup talk.mp4 -o cleaned.mp4
  declip workflow vertical cleaned.mp4 --mode pad
  ```

## Conventions

- All commands accept `--help`.
- Outputs default to `<input-basename>.<workflow>.mp4` next to the input.
- Intermediate JSON (project.json, probe metadata) is written next to the output for inspection.
- Library calls accept `write_project=False` to skip writing the project sidecar.
