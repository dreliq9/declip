# Vertical

Reframe horizontal video to 9:16 for TikTok / Reels / Shorts. Either crop (zoom in) or pad (letterbox).

## What it does

1. **Probe** the input to get source dimensions.
2. **Compute target** — defaults to 1080×1920 (9:16). Override with `--width` and `--height`.
3. **Reframe** with FFmpeg:
   - `--mode crop` (default) — center-crop the source to the new aspect ratio, then scale.
   - `--mode pad` — scale the source to fit fully, pad the empty space (default `#000000`, override with `--bg`).
   - `--mode blur-pad` — like pad, but the background is a blurred, scaled-up copy of the source (the modern Reels look).
4. **Loudnorm** the audio to `--target` (default `-14 LUFS`).

## When to use

- Republishing landscape content as Reels / Shorts / TikTok.
- Quick reformat before final captioning or vertical-specific editing.

## Usage

```bash
./scripts/vertical.sh wide.mp4
./scripts/vertical.sh wide.mp4 --mode pad --bg "#FFFFFF"
./scripts/vertical.sh wide.mp4 --mode blur-pad
./scripts/vertical.sh wide.mp4 --width 720 --height 1280
```

## Output

- `<output>.mp4` — vertical-reformatted video

## Gotchas

- **Crop mode is destructive.** Action near the edges of the source frame will be lost. Use `pad` or `blur-pad` if subject framing matters.
- **Blur-pad is heavier.** It runs the source through a Gaussian blur as the background plate; render time roughly doubles vs. plain pad.
- **Source already vertical?** The script no-ops the reframe and only runs loudnorm. Set `--force` to override.
- **Aspect-ratio rounding.** Odd source dimensions can produce off-by-one errors with FFmpeg's `crop` filter. The script rounds target dims to even numbers automatically.

## Composition

```bash
./scripts/ingest.sh raw.mp4 -o clean.mp4
./scripts/speech-cleanup.sh clean.mp4 --burn-captions -o cleaned.mp4
./scripts/vertical.sh cleaned.mp4 --mode blur-pad -o reel.mp4
```
