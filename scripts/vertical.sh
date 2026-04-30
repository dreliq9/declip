#!/usr/bin/env bash
# vertical.sh — reframe horizontal video to 9:16 (TikTok / Reels / Shorts)
# See docs/workflows/vertical.md
set -euo pipefail

DECLIP="${DECLIP:-declip}"

usage() {
  cat <<'EOF'
Usage: vertical.sh <input> [options]

Options:
  -o, --output PATH       Output path (default: <input-basename>.vertical.mp4)
  --mode MODE             crop | pad | blur-pad (default: crop)
  --width N               Target width (default: 1080)
  --height N              Target height (default: 1920)
  --bg COLOR              Background color for pad mode (default: #000000)
  --target VAL            Loudness target (default: -14)
  --force                 Reframe even if source is already vertical
  --dry-run               Print the plan, don't run
  -h, --help              Show this help

Outputs:
  <output>.mp4             reformatted vertical video
EOF
}

INPUT=""
OUTPUT=""
MODE="crop"
WIDTH=1080
HEIGHT=1920
BG="#000000"
TARGET="-14"
FORCE=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -o|--output) OUTPUT="$2"; shift 2 ;;
    --mode) MODE="$2"; shift 2 ;;
    --width) WIDTH="$2"; shift 2 ;;
    --height) HEIGHT="$2"; shift 2 ;;
    --bg) BG="$2"; shift 2 ;;
    --target) TARGET="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -*) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    *) INPUT="$1"; shift ;;
  esac
done

[[ -z "$INPUT" ]] && { echo "Missing <input>" >&2; usage; exit 2; }
[[ ! -f "$INPUT" ]] && { echo "Input not found: $INPUT" >&2; exit 1; }

case "$MODE" in
  crop|pad|blur-pad) ;;
  *) echo "Bad --mode: $MODE (use crop|pad|blur-pad)" >&2; exit 2 ;;
esac

# Round target dims to even
WIDTH=$(( (WIDTH / 2) * 2 ))
HEIGHT=$(( (HEIGHT / 2) * 2 ))

if [[ -z "$OUTPUT" ]]; then
  base="$(basename "$INPUT")"
  OUTPUT="${base%.*}.vertical.mp4"
fi
TMPNORM="${OUTPUT%.*}.tmp_reframed.mp4"

run() {
  if [[ "${DECLIP_VERBOSE:-0}" == "1" || "$DRY_RUN" == "1" ]]; then
    echo "+ $*" >&2
  fi
  [[ "$DRY_RUN" == "1" ]] || "$@"
}

# Probe to check current dims
echo "==> probe"
PROBE_JSON="$("$DECLIP" --json probe "$INPUT" | tail -1)"
SRC_W=$(echo "$PROBE_JSON" | "${PYTHON:-python3}" -c 'import json,sys; print(json.loads(sys.stdin.read())["width"])')
SRC_H=$(echo "$PROBE_JSON" | "${PYTHON:-python3}" -c 'import json,sys; print(json.loads(sys.stdin.read())["height"])')
echo "  source: ${SRC_W}x${SRC_H} → target: ${WIDTH}x${HEIGHT}"

if [[ "$SRC_H" -gt "$SRC_W" && "$FORCE" != "1" ]]; then
  echo "  source already vertical, skipping reframe (use --force to override)"
  cp "$INPUT" "$TMPNORM"
else
  echo "==> reframe (mode: $MODE)"
  case "$MODE" in
    crop)
      VF="scale=if(gt(a\,${WIDTH}/${HEIGHT})\,-2\,${WIDTH}):if(gt(a\,${WIDTH}/${HEIGHT})\,${HEIGHT}\,-2),crop=${WIDTH}:${HEIGHT}"
      ;;
    pad)
      VF="scale=${WIDTH}:${HEIGHT}:force_original_aspect_ratio=decrease,pad=${WIDTH}:${HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=${BG}"
      ;;
    blur-pad)
      VF="[0:v]split=2[bg][fg];[bg]scale=${WIDTH}:${HEIGHT}:force_original_aspect_ratio=increase,crop=${WIDTH}:${HEIGHT},gblur=sigma=30[bgblur];[fg]scale=${WIDTH}:${HEIGHT}:force_original_aspect_ratio=decrease[fgsc];[bgblur][fgsc]overlay=(W-w)/2:(H-h)/2"
      ;;
  esac

  if [[ "$MODE" == "blur-pad" ]]; then
    run ffmpeg -y -i "$INPUT" -filter_complex "$VF" -c:a copy "$TMPNORM"
  else
    run ffmpeg -y -i "$INPUT" -vf "$VF" -c:a copy "$TMPNORM"
  fi
fi

echo "==> loudnorm (target $TARGET LUFS)"
if run "$DECLIP" loudnorm "$TMPNORM" --target "$TARGET" -o "$OUTPUT"; then
  rm -f "$TMPNORM"
else
  echo "  loudnorm failed; using reframed output as-is" >&2
  mv "$TMPNORM" "$OUTPUT"
fi

echo "==> done: $OUTPUT"
