# Beat-sync

Cut video footage on the beats of a music track.

## What it does

1. **Detect beats** in the music with librosa beat tracking. Returns BPM + beat timestamps.
2. **Probe** the video to know its duration.
3. **Plan** — slice the video into segments, one per beat (or every Nth beat with `--stride`), each clip showing a short window of the source. The video plays at normal speed; cuts happen on beat boundaries.
4. **Build a project JSON** with the music as a separate audio track and the cut video on the main track.
5. **Render** to `<output>.mp4`.

## When to use

- Music videos, fitness/workout reels, montages.
- When you have a single long video that should be reframed as rhythmic cuts.
- Anywhere the soundtrack should drive the visual pacing.

## Usage

```bash
./scripts/beat-sync.sh footage.mp4 song.mp3
./scripts/beat-sync.sh footage.mp4 song.mp3 --stride 4 -o video.mp4
./scripts/beat-sync.sh footage.mp4 song.mp3 --stride 2 --window 1.5
```

- `--stride N` — cut on every Nth beat. Default 1 (cut on every beat). At 117 BPM that's ~0.5s clips; use 2–4 for a calmer pace.
- `--window S` — duration of each clip in seconds. Default: matches the inter-beat interval.

## Output

- `<output>.mp4` — rendered beat-synced video
- `<output>.project.json` — the assembled project
- `<output>.beats.json` — beat timestamps

## Gotchas

- **detect-beats uses librosa**, which expects clean musical audio. Live recordings with a lot of speech or noise on top will produce noisy beat detection.
- **Source duration matters.** If the music is longer than the video × stride, the script loops the video. If the video is longer, it gets cropped to the music length.
- **Cut-on-every-beat at high BPM can look frantic.** 117 BPM with stride 1 = ~500 cuts in 4 minutes. Use stride 4 (cut per bar in 4/4) for a more cinematic feel.
- **Original video audio is muted** — only the music plays. Use `--keep-audio` if you want both (the clip audio is mixed at -10 dB under the music).

## Reference

See [`examples/beat-sync.json`](../../examples/beat-sync.json) for the project shape (multi-track, music + video).

## Composition

```bash
./scripts/ingest.sh raw.mp4 -o clean.mp4
./scripts/beat-sync.sh clean.mp4 song.mp3 --stride 4 -o reel.mp4
./scripts/vertical.sh reel.mp4
```
