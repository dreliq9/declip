#!/usr/bin/env bash
# beat-sync.sh — cut video on the beats of a music track
# See docs/workflows/beat-sync.md
set -euo pipefail

DECLIP="${DECLIP:-declip}"
PYTHON="${PYTHON:-python3}"

usage() {
  cat <<'EOF'
Usage: beat-sync.sh <video> <music> [options]

Options:
  -o, --output PATH       Output path (default: <video-basename>.beat.mp4)
  --stride N              Cut on every Nth beat (default: 1)
  --window SECONDS        Clip window length (default: matches inter-beat interval)
  --keep-audio            Mix original video audio under the music at -10 dB
  --dry-run               Print the plan, don't render
  -h, --help              Show this help

Outputs:
  <output>.mp4             rendered beat-synced video
  <output>.project.json    declip project
  <output>.beats.json      beat timestamps and BPM
EOF
}

VIDEO=""
MUSIC=""
OUTPUT=""
STRIDE=1
WINDOW=""
KEEP_AUDIO=0
DRY_RUN=0

POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -o|--output) OUTPUT="$2"; shift 2 ;;
    --stride) STRIDE="$2"; shift 2 ;;
    --window) WINDOW="$2"; shift 2 ;;
    --keep-audio) KEEP_AUDIO=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -*) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    *) POSITIONAL+=("$1"); shift ;;
  esac
done

[[ ${#POSITIONAL[@]} -lt 2 ]] && { echo "Need <video> and <music>" >&2; usage; exit 2; }
VIDEO="${POSITIONAL[0]}"
MUSIC="${POSITIONAL[1]}"
[[ ! -f "$VIDEO" ]] && { echo "Video not found: $VIDEO" >&2; exit 1; }
[[ ! -f "$MUSIC" ]] && { echo "Music not found: $MUSIC" >&2; exit 1; }

if [[ -z "$OUTPUT" ]]; then
  base="$(basename "$VIDEO")"
  OUTPUT="${base%.*}.beat.mp4"
fi
PROJECT="${OUTPUT%.*}.project.json"
BEATS="${OUTPUT%.*}.beats.json"
PROBE_V="${OUTPUT%.*}.video.probe.json"
PROBE_M="${OUTPUT%.*}.music.probe.json"

run() {
  if [[ "${DECLIP_VERBOSE:-0}" == "1" || "$DRY_RUN" == "1" ]]; then
    echo "+ $*" >&2
  fi
  [[ "$DRY_RUN" == "1" ]] || "$@"
}

echo "==> probe video + music"
run sh -c "'$DECLIP' --json probe '$VIDEO' > '$PROBE_V'"
run sh -c "'$DECLIP' --json probe '$MUSIC' > '$PROBE_M'"

echo "==> detect beats"
run sh -c "'$DECLIP' --json detect-beats '$MUSIC' > '$BEATS'"

[[ "$DRY_RUN" == "1" ]] && { echo "(dry-run: skipping plan + render)"; exit 0; }

echo "==> plan + write project.json"
VIDEO_ABS="$(cd "$(dirname "$VIDEO")" && pwd)/$(basename "$VIDEO")"
MUSIC_ABS="$(cd "$(dirname "$MUSIC")" && pwd)/$(basename "$MUSIC")"
"$PYTHON" - "$PROBE_V" "$PROBE_M" "$BEATS" "$VIDEO_ABS" "$MUSIC_ABS" "$PROJECT" "$OUTPUT" "$STRIDE" "${WINDOW:-auto}" "$KEEP_AUDIO" <<'PYEOF'
import json, sys
probe_v_p, probe_m_p, beats_p, vid, mus, project_p, output_p, stride, window, keep_audio = sys.argv[1:]
stride = int(stride); keep_audio = int(keep_audio)

def last_json_line(path):
    with open(path) as f:
        for line in reversed(f.read().strip().splitlines()):
            line = line.strip()
            if line:
                try: return json.loads(line)
                except json.JSONDecodeError: continue
    return {}

probe_v = last_json_line(probe_v_p)
probe_m = last_json_line(probe_m_p)
v_dur = float(probe_v.get("duration", 0))
m_dur = float(probe_m.get("duration", 0))

# Parse beats: declip detect-beats prints stats then beat lines.
# Capture the structured JSON line if present.
beats = []
with open(beats_p) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            obj = json.loads(line)
            if "beats" in obj and isinstance(obj["beats"], list):
                beats = [float(b) for b in obj["beats"]]
                break
            if "timestamp" in obj:
                beats.append(float(obj["timestamp"]))
        except json.JSONDecodeError:
            pass

if not beats:
    print("  no beats parsed; aborting", file=sys.stderr)
    sys.exit(1)

# Apply stride
beats = beats[::stride]

# Window: inter-beat interval at the chosen stride, or user-specified
if window == "auto":
    if len(beats) >= 2:
        window = beats[1] - beats[0]
    else:
        window = 1.0
else:
    window = float(window)

# Clip pool: sample distinct moments from the source video
v_clips = []
if v_dur <= window * 1.5:
    # Source too short; loop from the start
    v_starts = [0.0] * len(beats)
else:
    step = (v_dur - window) / max(1, len(beats) - 1)
    v_starts = [round(i * step, 3) for i in range(len(beats))]

clips = []
for i, beat_t in enumerate(beats):
    clip_start = v_starts[i]
    clips.append({
        "asset": vid,
        "start": round(beat_t, 3),
        "trim_in": clip_start,
        "trim_out": round(min(v_dur, clip_start + window), 3),
    })

# Truncate clips that exceed the music duration
clips = [c for c in clips if float(c["start"]) < m_dur]
# Last clip may run past music end — trim it
if clips:
    last = clips[-1]
    end = float(last["start"]) + (last["trim_out"] - last["trim_in"])
    if end > m_dur:
        last["trim_out"] = last["trim_in"] + max(0.1, m_dur - float(last["start"]))

# Music track
music_track = {
    "id": "music",
    "clips": [{"asset": mus, "start": 0, "trim_in": 0, "trim_out": round(m_dur, 3)}],
}

project = {
    "version": "1.0",
    "settings": {
        "resolution": [int(probe_v.get("width", 1920)), int(probe_v.get("height", 1080))],
        "fps": int(probe_v.get("fps", 30)),
        "background": "#000000",
    },
    "timeline": {"tracks": [{"id": "video", "clips": clips}, music_track]},
    "output": {"path": output_p, "format": "mp4", "codec": "h264", "quality": "medium"},
}

with open(project_p, "w") as f:
    json.dump(project, f, indent=2)

print(f"  {len(clips)} cuts, ~{window:.2f}s each, music duration {m_dur:.1f}s")
PYEOF

echo "==> render"
run "$DECLIP" render "$PROJECT"

echo "==> done: $OUTPUT (project: $PROJECT)"
