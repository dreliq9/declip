#!/usr/bin/env bash
# review.sh — generate a QA report pack for a rendered video
# See docs/workflows/review.md
set -euo pipefail

DECLIP="${DECLIP:-declip}"
PYTHON="${PYTHON:-python3}"

usage() {
  cat <<'EOF'
Usage: review.sh <input> [options]

Options:
  -o, --output DIR        Report directory (default: <input-basename>-review/)
  --frames N              Sparse-frame count (default: 16)
  --scene-threshold V     Scene-detect threshold 0.0-1.0 (default: 0.4)
  --dry-run               Print the plan, don't execute
  -h, --help              Show this help

Outputs in <output>/:
  REVIEW.md               summary tying everything together
  probe.json              probe data
  scenes.json             scene-detect output
  silence.json            silence-detect output
  beats.json              beat-detect output (BPM)
  loudness.txt            integrated LUFS
  contact_sheet.png       5x4 thumbnail grid
  sparse/                 N evenly-spaced frame extracts
  cuts/                   per-cut frame pairs (before/after each scene cut)
EOF
}

INPUT=""
OUTPUT=""
FRAMES=16
THRESHOLD=0.4
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -o|--output) OUTPUT="$2"; shift 2 ;;
    --frames) FRAMES="$2"; shift 2 ;;
    --scene-threshold) THRESHOLD="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    -*) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    *) INPUT="$1"; shift ;;
  esac
done

[[ -z "$INPUT" ]] && { echo "Missing <input>" >&2; usage; exit 2; }
[[ ! -f "$INPUT" ]] && { echo "Input not found: $INPUT" >&2; exit 1; }

if [[ -z "$OUTPUT" ]]; then
  base="$(basename "$INPUT")"
  OUTPUT="${base%.*}-review"
fi

run() {
  if [[ "${DECLIP_VERBOSE:-0}" == "1" || "$DRY_RUN" == "1" ]]; then
    echo "+ $*" >&2
  fi
  [[ "$DRY_RUN" == "1" ]] || "$@"
}

mkdir -p "$OUTPUT/sparse" "$OUTPUT/cuts"

echo "==> Phase 0: probe"
run sh -c "'$DECLIP' --json probe '$INPUT' > '$OUTPUT/probe.json'"

echo "==> Phase 1: audio analysis (parallel)"
run sh -c "'$DECLIP' --json detect-scenes --threshold $THRESHOLD '$INPUT' > '$OUTPUT/scenes.json'" &
PID_SCENES=$!
run sh -c "'$DECLIP' --json detect-silence '$INPUT' > '$OUTPUT/silence.json'" &
PID_SILENCE=$!
run sh -c "'$DECLIP' --json detect-beats '$INPUT' > '$OUTPUT/beats.json'" &
PID_BEATS=$!
wait $PID_SCENES $PID_SILENCE $PID_BEATS

echo "==> loudness"
run sh -c "'$DECLIP' loudness '$INPUT' > '$OUTPUT/loudness.txt'"

echo "==> Phase 2: contact sheet + sparse frames"
run "$DECLIP" contact-sheet "$INPUT" --columns 5 --rows 4 -o "$OUTPUT/contact_sheet.png" || true
run "$DECLIP" extract-frames "$INPUT" --count "$FRAMES" -o "$OUTPUT/sparse/" || true

[[ "$DRY_RUN" == "1" ]] && { echo "(dry-run: skipping Phase 3 + REVIEW.md)"; exit 0; }

echo "==> Phase 3: targeted frames at cut points"
"$PYTHON" - "$OUTPUT/scenes.json" "$INPUT" "$OUTPUT/cuts" "$DECLIP" <<'PYEOF'
import json, subprocess, sys, os
scenes_p, src, out_dir, declip = sys.argv[1:]
cuts = []
with open(scenes_p) as f:
    for line in f:
        line = line.strip()
        if not line: continue
        try:
            obj = json.loads(line)
            if "cuts" in obj:
                for c in obj["cuts"]:
                    if isinstance(c, (int, float)): cuts.append(float(c))
                    elif isinstance(c, dict):
                        for k in ("timestamp", "time", "t"):
                            if k in c: cuts.append(float(c[k])); break
            elif "timestamp" in obj:
                cuts.append(float(obj["timestamp"]))
        except json.JSONDecodeError:
            pass
print(f"  {len(cuts)} scene cuts; extracting before/after frames")
for i, t in enumerate(cuts):
    for offset, label in ((-0.5, "before"), (0.5, "after")):
        ts = max(0.0, t + offset)
        out = os.path.join(out_dir, f"cut_{i:03d}_{label}.png")
        subprocess.run([declip, "thumbnail", src, "--at", str(ts), "-o", out], check=False, capture_output=True)
PYEOF

echo "==> Synthesize REVIEW.md"
"$PYTHON" - "$OUTPUT" "$INPUT" <<'PYEOF'
import json, os, sys
out_dir, src = sys.argv[1:]

def last_json(path):
    if not os.path.exists(path): return {}
    try:
        with open(path) as f:
            lines = [l for l in f.read().strip().splitlines() if l.strip()]
        return json.loads(lines[-1]) if lines else {}
    except Exception:
        return {}

def collect_lines(path):
    if not os.path.exists(path): return []
    out = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: out.append(json.loads(line))
            except json.JSONDecodeError: pass
    return out

probe = last_json(os.path.join(out_dir, "probe.json"))
scenes = collect_lines(os.path.join(out_dir, "scenes.json"))
silence = collect_lines(os.path.join(out_dir, "silence.json"))
beats = collect_lines(os.path.join(out_dir, "beats.json"))

loud = ""
lp = os.path.join(out_dir, "loudness.txt")
if os.path.exists(lp):
    loud = open(lp).read().strip()

cut_count = 0
for s in scenes:
    if "cuts" in s and isinstance(s["cuts"], list):
        cut_count = max(cut_count, len(s["cuts"]))
silence_count = 0
for s in silence:
    if "ranges" in s and isinstance(s["ranges"], list):
        silence_count = max(silence_count, len(s["ranges"]))
bpm = ""
for b in beats:
    if "tempo" in b: bpm = f"{float(b['tempo']):.1f} BPM"; break
    if "bpm" in b: bpm = f"{float(b['bpm']):.1f} BPM"; break

dur = float(probe.get("duration", 0))
size = float(probe.get("file_size", 0)) / 1024 / 1024

md = f"""# Review: {os.path.basename(src)}

## Probe
- Duration: {dur:.1f}s
- Resolution: {probe.get('width','?')}x{probe.get('height','?')} @ {probe.get('fps','?')}fps
- Codec: {probe.get('codec','?')} / {probe.get('audio_codec','?')}
- Size: {size:.1f} MB
- HDR: {probe.get('is_hdr', False)}

## Audio
{loud}

## Phase 1 results
- Scene cuts: **{cut_count}**
- Silent segments: **{silence_count}**
- Tempo: **{bpm or 'no tempo detected (likely non-music)'}**

## Phase 2 — visual overview
- `contact_sheet.png` — 5x4 grid
- `sparse/` — evenly-spaced frame extracts

## Phase 3 — cut-point detail
- `cuts/cut_NNN_before.png` and `cuts/cut_NNN_after.png` for each scene boundary

## Validation tricks
- **Crossfades present?** Lower scene count than clip count = working transitions.
- **Source bumpers?** Compare `cuts/cut_*_before.png` vs `cuts/cut_*_after.png` for unwanted logos/end-cards.
- **Audio fades correct?** Cross-check `silence.json` start/end vs intended fade timing.
"""

with open(os.path.join(out_dir, "REVIEW.md"), "w") as f:
    f.write(md)
print(f"  REVIEW.md written")
PYEOF

echo "==> done: $OUTPUT/REVIEW.md"
