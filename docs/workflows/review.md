# Review

Generate a QA report pack for a rendered video. Adapted from a real production pipeline (`feedback_video_review_workflow.md`).

## What it does

The four-phase review pattern, condensed into one command:

1. **Phase 0 — Probe.** Capture container, codec, resolution, fps, duration, color metadata.
2. **Phase 1 — Audio analysis (parallel):**
   - `detect-scenes` — cut points
   - `detect-beats` — BPM (useful for music-driven content; returns empty for ambient)
   - `detect-silence` — gap ranges
3. **Phase 2 — Sparse frame pass.** Extract `--frames` evenly spaced thumbnails (default 16) for a quick visual overview.
4. **Phase 3 — Targeted frame extraction at cut points.** For each scene cut from Phase 1, extract two frames: 0.5s before and 0.5s after. Catches bad trim points, flash frames, and source-baked content (logos, bumpers).

A `REVIEW.md` summary is generated tying everything together.

## When to use

- After any non-trivial render, before declaring done.
- When debugging "why does this edit feel off?" without watching the full video.
- As a CI/automation hook — check that scenes/silence/loudness fall in expected ranges.

## Usage

```bash
./scripts/review.sh final.mp4
./scripts/review.sh final.mp4 -o review/
./scripts/review.sh final.mp4 --frames 24 --scene-threshold 0.4
```

## Output

A directory (default `<input-basename>-review/`) containing:

- `REVIEW.md` — human-readable summary tying all the analyses together
- `probe.json` — full probe output
- `scenes.json`, `silence.json`, `beats.json` — analysis results
- `contact_sheet.png` — 5×4 thumbnail grid
- `sparse/` — 16 evenly-spaced frame extracts
- `cuts/` — per-cut frame pairs (`cut_<idx>_before.png`, `cut_<idx>_after.png`)
- `loudness.txt` — integrated LUFS, range, true peak

## Validation tricks (from real production)

- **Crossfades working?** Phase 1 scene-detect should find *fewer* cuts than the number of clip boundaries in your project. Hard cuts → high count; crossfades → low count.
- **Source bumpers?** Look at the last frame of `cuts/cut_*_before.png` against `cuts/cut_*_after.png` — if a logo/bumper appears right before a cut, your trim point was set after the source's own end-card.
- **Audio fade timing?** Cross-reference `silence.json` start/end with intended fade-in/fade-out points.

## Gotchas

- **PyAV frame extraction lands on nearest keyframe.** For AI-generated clips with sparse keyframes, frames may look identical. AUDIT.md flags this. Use higher `--frames` density to compensate, or accept the limitation.
- **Scene detection is currently weak** (manual frame-diff). On continuous-take video it returns 0; the cuts/ directory will be empty.
- **No motion-quality check.** This workflow doesn't catch frame-rate stutters or jitter — for that, you need denser frame extraction or actual playback.
