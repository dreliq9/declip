#!/usr/bin/env bash
# speech-cleanup.sh — talking-head jump-cut edit (drop silences, optional captions)
# See docs/workflows/speech-cleanup.md
set -euo pipefail

DECLIP="${DECLIP:-declip}"
PYTHON="${PYTHON:-python3}"

usage() {
  cat <<'EOF'
Usage: speech-cleanup.sh <input> [options]

Options:
  -o, --output PATH       Output path (default: <input-basename>.cleaned.mp4)
  --gap SECONDS           Drop silent gaps longer than this (default: 0.5)
  --pad SECONDS           Pad each kept segment with this much head/tail (default: 0.1)
  --burn-captions         Burn the SRT into the rendered output (requires libass)
  --dry-run               Print the plan, don't render
  -h, --help              Show this help

Outputs:
  <output>.mp4             cleaned video
  <output>.srt             subtitle sidecar (always written)
  <output>.project.json    trim plan
EOF
}

INPUT=""
OUTPUT=""
GAP=0.5
PAD=0.1
BURN=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -o|--output) OUTPUT="$2"; shift 2 ;;
    --gap) GAP="$2"; shift 2 ;;
    --pad) PAD="$2"; shift 2 ;;
    --burn-captions) BURN=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -*) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    *) INPUT="$1"; shift ;;
  esac
done

[[ -z "$INPUT" ]] && { echo "Missing <input>" >&2; usage; exit 2; }
[[ ! -f "$INPUT" ]] && { echo "Input not found: $INPUT" >&2; exit 1; }

if [[ -z "$OUTPUT" ]]; then
  base="$(basename "$INPUT")"
  OUTPUT="${base%.*}.cleaned.mp4"
fi
PROJECT="${OUTPUT%.*}.project.json"
SRT_OUT="${OUTPUT%.*}.srt"
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

echo "==> transcribe (whisper)"
run "$DECLIP" transcribe "$INPUT" 2>&1 | tail -5

# transcribe writes SRT next to the source — find it and copy to our naming
INPUT_DIR="$(cd "$(dirname "$INPUT")" && pwd)"
INPUT_BASE="$(basename "$INPUT")"
SRT_SRC="$INPUT_DIR/${INPUT_BASE%.*}.srt"
if [[ -f "$SRT_SRC" ]]; then
  cp "$SRT_SRC" "$SRT_OUT"
fi

echo "==> detect silence"
run sh -c "'$DECLIP' --json detect-silence '$INPUT' > '$SILENCE'"

[[ "$DRY_RUN" == "1" ]] && { echo "(dry-run: skipping plan + render)"; exit 0; }

if [[ ! -s "$SRT_OUT" ]]; then
  echo "  no speech detected — nothing to clean. Bailing." >&2
  rm -f "$PROJECT" "$PROBE" "$SILENCE"
  exit 1
fi

echo "==> plan kept-segments"
INPUT_ABS="$INPUT_DIR/$INPUT_BASE"
"$PYTHON" - "$PROBE" "$SRT_OUT" "$INPUT_ABS" "$PROJECT" "$OUTPUT" "$GAP" "$PAD" <<'PYEOF'
import json, re, sys
probe_p, srt_p, src, project_p, output_p, gap, pad = sys.argv[1:]
gap = float(gap); pad = float(pad)

with open(probe_p) as f:
    probe = json.loads(f.read().strip().splitlines()[-1])
duration = float(probe["duration"])

def srt_time(t):
    h, m = divmod(int(t), 3600)
    m, s = divmod(m, 60)
    return h, m, s, int((t - int(t)) * 1000)

def parse_srt(path):
    pat = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")
    out = []
    with open(path) as f:
        text = f.read()
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2: continue
        # second line is timing
        tline = next((l for l in lines if "-->" in l), None)
        if not tline: continue
        a, _, b = tline.partition("-->")
        ma, mb = pat.search(a), pat.search(b)
        if not ma or not mb: continue
        def to_s(m): return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3)) + int(m.group(4))/1000
        out.append((to_s(ma), to_s(mb)))
    return out

segments = parse_srt(srt_p)
if not segments:
    print("  no segments parsed from SRT", file=sys.stderr)
    sys.exit(1)

# Apply pad and clamp
padded = [(max(0, a - pad), min(duration, b + pad)) for a, b in segments]

# Merge segments separated by < gap
merged = [padded[0]]
for a, b in padded[1:]:
    pa, pb = merged[-1]
    if a - pb < gap:
        merged[-1] = (pa, b)
    else:
        merged.append((a, b))

# Build clips
clips = []
for i, (a, b) in enumerate(merged):
    clips.append({
        "asset": src,
        "start": 0 if i == 0 else "auto",
        "trim_in": round(a, 3),
        "trim_out": round(b, 3),
    })

project = {
    "version": "1.0",
    "settings": {
        "resolution": [int(probe.get("width", 1920)), int(probe.get("height", 1080))],
        "fps": int(probe.get("fps", 30)),
        "background": "#000000",
    },
    "timeline": {"tracks": [{"id": "main", "clips": clips}]},
    "output": {"path": output_p, "format": "mp4", "codec": "h264", "quality": "high"},
}

with open(project_p, "w") as f:
    json.dump(project, f, indent=2)

total = sum(b - a for a, b in merged)
print(f"  kept {len(merged)} segments, total {total:.1f}s of {duration:.1f}s ({100*total/duration:.0f}%)")
PYEOF

echo "==> render"
run "$DECLIP" render "$PROJECT"

if [[ "$BURN" == "1" ]]; then
  BURNED="${OUTPUT%.*}.captioned.mp4"
  echo "==> burn captions"
  if run ffmpeg -y -i "$OUTPUT" -vf "subtitles='$SRT_OUT'" -c:a copy "$BURNED" 2>&1 | tail -3; then
    mv "$BURNED" "$OUTPUT"
  else
    echo "  caption burn failed (FFmpeg likely missing libass) — sidecar SRT preserved at $SRT_OUT" >&2
  fi
fi

echo "==> done: $OUTPUT (project: $PROJECT, srt: $SRT_OUT)"
