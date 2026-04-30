# Speech cleanup

Remove dead air from talking-head video. Optionally burn in captions.

## What it does

1. **Transcribe** with Whisper (segment-level timestamps).
2. **Detect silence** as a fallback signal where transcription is sparse.
3. **Plan** — keep speech segments, drop gaps longer than `--gap` (default 0.5s). Each kept segment is padded with `--pad` (default 0.1s) at both ends to avoid clipping word edges.
4. **Build a project JSON** with the kept segments.
5. **Render** to `<output>.mp4`.
6. **(Optional) Burn captions** — when `--burn-captions` is set, the SRT is overlaid on the rendered output via FFmpeg's `subtitles=` filter.

## When to use

- Interviews, vlogs, lecture recordings, podcast video.
- Anywhere the unedited source has long pauses or `um`-laden gaps.
- First pass before manual fine-tuning in a real NLE.

## Usage

```bash
./scripts/speech-cleanup.sh interview.mp4
./scripts/speech-cleanup.sh interview.mp4 --burn-captions
./scripts/speech-cleanup.sh interview.mp4 --gap 0.3 --pad 0.15 -o cleaned.mp4
```

## Output

- `<output>.mp4` — cleaned video
- `<output>.srt` — subtitle file (sidecar even if not burned)
- `<output>.project.json` — the trim plan

## Gotchas

- **Whisper segment-level only.** declip's `transcribe` doesn't yet emit word-level timestamps (WhisperX is in the roadmap). Trims are based on segment boundaries, which can be coarse.
- **No speech detected → no edit.** If transcribe returns 0 segments (non-speech audio, very quiet, or very heavy accent), the script bails with a clear error rather than producing an empty video.
- **Caption burn-in requires FFmpeg with `libass`.** If your Homebrew FFmpeg was built without it, `--burn-captions` will fail. Install with `brew install ffmpeg --with-freetype --with-libass`. The sidecar SRT is always written regardless.
- **Pad too large** can cause overlapping segments. The script merges segments that overlap after padding.

## Reference

See [`examples/speech-cleanup.json`](../../examples/speech-cleanup.json) for the project shape this workflow produces.

## Composition

```bash
./scripts/ingest.sh raw.mp4 -o clean.mp4
./scripts/speech-cleanup.sh clean.mp4 --burn-captions -o final.mp4
./scripts/vertical.sh final.mp4 --mode pad
```
