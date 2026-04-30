# declip workflows

Reusable end-to-end recipes built from declip's primitives. Each workflow has:

- `docs/workflows/<name>.md` — the recipe (what it does, when to use it, gotchas)
- `examples/<name>.json` — a static reference project showing the JSON shape produced (where applicable)
- `scripts/<name>.sh` — a one-command orchestrator that runs the full pipeline

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

All scripts assume `declip` is on `PATH` (or override with `DECLIP=/path/to/declip`).

```bash
# from the repo root
./scripts/ingest.sh input.mp4 -o normalized.mp4
./scripts/cutdown.sh long.mp4 --target 60 -o highlight.mp4
./scripts/speech-cleanup.sh interview.mp4 --burn-captions
./scripts/beat-sync.sh footage.mp4 song.mp3 --stride 4
./scripts/vertical.sh wide.mp4 --mode crop
./scripts/review.sh final.mp4 -o review/
```

Every script accepts `--help` and `--dry-run` (prints the plan without executing).

## Composition

Workflows compose. Common chains:

- **Ingest then cut down:** `ingest.sh raw.mp4 -o clean.mp4 && cutdown.sh clean.mp4 --target 30`
- **Cut down then review:** `cutdown.sh long.mp4 -o short.mp4 && review.sh short.mp4 -o qa/`
- **Speech-cleanup then vertical:** `speech-cleanup.sh talk.mp4 -o cleaned.mp4 && vertical.sh cleaned.mp4 --mode pad`

## Conventions

- All scripts are POSIX-ish bash, quote-safe for paths with spaces.
- Outputs default to `<input-basename>.<workflow>.mp4` next to the input.
- Intermediate JSON (probe data, scenes, beats, silence) is written next to the output for inspection.
- Set `DECLIP_VERBOSE=1` to see every underlying declip invocation.
