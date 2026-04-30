# Ingest

Normalize an arbitrary video to a known-good baseline before further editing.

## What it does

1. **Probe** the input — captures duration, codec, resolution, fps, bitrate, audio specs, color metadata. Saved as `<output>.metadata.json`.
2. **Loudnorm** — two-pass EBU R128 normalization to a platform target (default `-14 LUFS` for streaming).
3. **Optional auto-grade** — neutral color correction (`color-grade` with default exposure/contrast/saturation lift). Off by default; toggle with `--grade`.

## When to use

- Right after exporting from a phone or camera, before editing.
- Before running `cutdown` or `speech-cleanup` — those workflows assume normalized loudness.
- When pulling in third-party footage with unknown levels.

## Usage

```bash
./scripts/ingest.sh input.mp4
./scripts/ingest.sh input.mp4 -o normalized.mp4 --target -16
./scripts/ingest.sh input.mp4 --grade
```

Targets: `youtube` (-14), `tiktok` (-11), `podcast` (-16), `broadcast` (-23), or a custom number like `-18`.

## Output

- `<output>.mp4` — normalized video
- `<output>.metadata.json` — probe results in JSON

## Gotchas

- Loudnorm is two-pass — runtime is roughly 2× the video duration on a single CPU.
- Auto-grade is conservative. For real grading, use `declip color-grade` directly with tuned params, or feed the result into a project JSON with custom filters.
- If the input has no audio, loudnorm fails fast — the script falls back to a no-op copy and warns.

## Composition

Common follow-ups:

```bash
./scripts/ingest.sh raw.mp4 -o clean.mp4
./scripts/cutdown.sh clean.mp4 --target 60
./scripts/review.sh clean.mp4 -o qa/
```
