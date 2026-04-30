#!/usr/bin/env bash
# cutdown.sh — long source → short highlight reel
# See docs/workflows/cutdown.md
set -euo pipefail

DECLIP="${DECLIP:-declip}"
PYTHON="${PYTHON:-python3}"

usage() {
  cat <<'EOF'
Usage: cutdown.sh <input> [options]

Options:
  -o, --output PATH       Output path (default: <input-basename>.cutdown.mp4)
  --target SECONDS        Target duration of the highlight (default: 60)
  --transition NAME       Transition between clips (default: dissolve)
                          Examples: dissolve, fade_black, wipe_left, slide_up
  --crossfade SECONDS     Transition duration (default: 0.5)
  --segment-min SECONDS   Minimum segment length to consider (default: 3)
  --segment-max SECONDS   Maximum segment length per clip (default: 10)
  --dry-run               Print the plan, don't render
  -h, --help              Show this help

Outputs:
  <output>.mp4             rendered highlight
  <output>.project.json    declip project (edit + re-render to refine)
  <output>.scenes.json     scene-detect results
  <output>.silence.json    silence-detect results
EOF
}

INPUT=""
OUTPUT=""
TARGET=60
TRANSITION="dissolve"
CROSSFADE=0.5
SEG_MIN=3
SEG_MAX=10
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -o|--output) OUTPUT="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    --transition) TRANSITION="$2"; shift 2 ;;
    --crossfade) CROSSFADE="$2"; shift 2 ;;
    --segment-min) SEG_MIN="$2"; shift 2 ;;
    --segment-max) SEG_MAX="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -*) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    *) INPUT="$1"; shift ;;
  esac
done

[[ -z "$INPUT" ]] && { echo "Missing <input>" >&2; usage; exit 2; }
[[ ! -f "$INPUT" ]] && { echo "Input not found: $INPUT" >&2; exit 1; }

if [[ -z "$OUTPUT" ]]; then
  base="$(basename "$INPUT")"
  OUTPUT="${base%.*}.cutdown.mp4"
fi
PROJECT="${OUTPUT%.*}.project.json"
SCENES="${OUTPUT%.*}.scenes.json"
SILENCE="${OUTPUT%.*}.silence.json"
PROBE="${OUTPUT%.*}.probe.json"

run() {
  if [[ "${DECLIP_VERBOSE:-0}" == "1" || "$DRY_RUN" == "1" ]]; then
    echo "+ $*" >&2
  fi
  [[ "$DRY_RUN" == "1" ]] || "$@"
}

echo "==> probe"
run sh -c "'$DECLIP' --json probe '$INPUT' > '$PROBE'"

echo "==> detect scenes"
run sh -c "'$DECLIP' --json detect-scenes '$INPUT' > '$SCENES'"

echo "==> detect silence"
run sh -c "'$DECLIP' --json detect-silence '$INPUT' > '$SILENCE'"

[[ "$DRY_RUN" == "1" ]] && { echo "(dry-run: skipping plan + render)"; exit 0; }

echo "==> plan + write project.json"
INPUT_ABS="$(cd "$(dirname "$INPUT")" && pwd)/$(basename "$INPUT")"
"$PYTHON" - "$PROBE" "$SCENES" "$SILENCE" "$INPUT_ABS" "$PROJECT" "$OUTPUT" "$TARGET" "$TRANSITION" "$CROSSFADE" "$SEG_MIN" "$SEG_MAX" <<'PYEOF'
import json, sys
probe_p, scenes_p, silence_p, src, project_p, output_p, target, transition, crossfade, seg_min, seg_max = sys.argv[1:]
target = float(target); crossfade = float(crossfade); seg_min = float(seg_min); seg_max = float(seg_max)

# Probe is one JSON line
with open(probe_p) as f:
    probe = json.loads(f.read().strip().splitlines()[-1])
duration = float(probe["duration"])

def load_ndjson(path):
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: out.append(json.loads(line))
            except json.JSONDecodeError: pass
    return out

scenes = load_ndjson(scenes_p)
silence = load_ndjson(silence_p)

# Build silence ranges (list of [start, end])
silence_ranges = []
for s in silence:
    if "ranges" in s:
        for r in s["ranges"]:
            silence_ranges.append((float(r["start"]), float(r["end"])))
    elif "start" in s and "end" in s:
        silence_ranges.append((float(s["start"]), float(s["end"])))

# Scene cut timestamps
cuts = []
for s in scenes:
    if "cuts" in s:
        for c in s["cuts"]:
            cuts.append(float(c if isinstance(c, (int, float)) else c.get("timestamp", c.get("time", 0))))
    elif "timestamp" in s:
        cuts.append(float(s["timestamp"]))
cuts = sorted(set([0.0] + cuts + [duration]))

# Segments between cuts
segments = []
for a, b in zip(cuts, cuts[1:]):
    if b - a < seg_min: continue
    # Trim segment if it overlaps silence
    seg_start, seg_end = a, b
    for sa, sb in silence_ranges:
        if sb <= seg_start or sa >= seg_end:
            continue
        # If silence covers most of the segment, drop it
        overlap = min(seg_end, sb) - max(seg_start, sa)
        if overlap > 0.5 * (seg_end - seg_start):
            seg_end = seg_start  # mark as empty
            break
    if seg_end - seg_start < seg_min: continue
    # Cap each segment length
    if seg_end - seg_start > seg_max:
        seg_end = seg_start + seg_max
    segments.append((seg_start, seg_end))

# If scene detection produced too little material, fall back to evenly-spaced sampling
if not segments or sum(b - a for a, b in segments) < target * 0.8:
    n_segs = max(3, int(target / seg_max))
    seg_len = min(seg_max, max(seg_min, target / n_segs))
    spacing = (duration - seg_len) / max(1, n_segs - 1) if n_segs > 1 else 0
    segments = [(i * spacing, i * spacing + seg_len) for i in range(n_segs)]

# Pick segments to hit target duration, evenly distributed
# Greedy: longest segments first, then check distribution
segments.sort(key=lambda s: (s[1] - s[0]), reverse=True)
picked = []
total = 0.0
for s in segments:
    seg_dur = s[1] - s[0]
    if total + seg_dur > target * 1.1: continue
    picked.append(s)
    total += seg_dur
    if total >= target * 0.9: break

if not picked:
    picked = segments[:1]

# Sort picked back into timeline order
picked.sort(key=lambda s: s[0])

# Build clips
clips = []
for i, (a, b) in enumerate(picked):
    clip = {
        "asset": src,
        "start": 0 if i == 0 else "auto",
        "trim_in": round(a, 3),
        "trim_out": round(b, 3),
    }
    if i == 0:
        clip["filters"] = [{"type": "fade_in", "duration": 0.5}]
    else:
        clip["transition_in"] = {"type": transition, "duration": crossfade}
    if i == len(picked) - 1:
        clip.setdefault("filters", []).append({"type": "fade_out", "duration": 0.5})
    clips.append(clip)

project = {
    "version": "1.0",
    "settings": {
        "resolution": [int(probe.get("width", 1920)), int(probe.get("height", 1080))],
        "fps": int(probe.get("fps", 30)),
        "background": "#000000",
    },
    "timeline": {"tracks": [{"id": "main", "clips": clips}]},
    "output": {"path": output_p, "format": "mp4", "codec": "h264", "quality": "medium"},
}

with open(project_p, "w") as f:
    json.dump(project, f, indent=2)

print(f"  picked {len(picked)} segments, total {total:.1f}s")
PYEOF

echo "==> render"
run "$DECLIP" render "$PROJECT"

echo "==> done: $OUTPUT (project: $PROJECT)"
