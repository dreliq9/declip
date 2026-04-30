# Cutdown

Turn a long source into a shorter highlight reel using scene detection and silence as the signal.

## What it does

1. **Probe** the source.
2. **Detect scenes** — ranks segment boundaries by visual change.
3. **Detect silence** — gives candidate "skip" ranges.
4. **Plan** — pick the longest non-silent segments evenly distributed across the timeline, summing to roughly `--target` seconds.
5. **Build a project JSON** — selected segments with crossfades between them.
6. **Render** to `<output>.mp4`.

The picker is deliberately simple: longest non-silent runs, evenly spaced. It's a starting point — edit the generated `project.json` and re-render with `declip render` for finer control.

## When to use

- 10–60 minute source → 30–120 second highlight.
- Sports, b-roll reels, recap videos, lecture summaries.
- Any case where "the interesting bits are the long, non-silent stretches."

## Usage

```bash
./scripts/cutdown.sh long.mp4
./scripts/cutdown.sh long.mp4 --target 90 -o highlight.mp4
./scripts/cutdown.sh long.mp4 --target 30 --transition fade_black --crossfade 0.75
```

Defaults: target 60s, transition `dissolve`, crossfade duration 0.5s.

## Output

- `<output>.mp4` — rendered highlight
- `<output>.project.json` — the assembled project (edit + re-render to refine)
- `<output>.scenes.json`, `<output>.silence.json` — analysis intermediates

## Gotchas

- **Scene detection in declip is currently weak** (manual frame-diff). For continuous-take video it returns 0 cuts and the picker falls back to evenly-spaced sampling. AUDIT.md flags PySceneDetect as the planned upgrade.
- **The picker is heuristic.** It will sometimes cut mid-action or include a low-energy stretch. For final-quality work, treat the output as a first draft.
- **Crossfades cost duration.** A 0.5s crossfade overlaps clips by 0.5s; the rendered length is shorter than the sum of clip durations.

## Reference

See [`examples/cutdown.json`](../../examples/cutdown.json) for a hand-built example showing the project shape this workflow produces.

## Composition

```bash
./scripts/ingest.sh raw.mp4 -o clean.mp4
./scripts/cutdown.sh clean.mp4 --target 60 -o highlight.mp4
./scripts/review.sh highlight.mp4 -o qa/
```
