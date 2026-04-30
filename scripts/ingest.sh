#!/usr/bin/env bash
# ingest.sh — normalize loudness + probe + optional auto-grade
# See docs/workflows/ingest.md
set -euo pipefail

DECLIP="${DECLIP:-declip}"

usage() {
  cat <<'EOF'
Usage: ingest.sh <input> [options]

Options:
  -o, --output PATH    Output path (default: <input-basename>.normalized.mp4)
  -t, --target VAL     Loudness target: youtube (-14), tiktok (-11), podcast (-16),
                       broadcast (-23), or custom number like -18. Default: -14
  --grade              Apply neutral auto-grade (slight contrast/saturation lift)
  --dry-run            Print the plan, don't execute
  -h, --help           Show this help

Outputs:
  <output>.mp4          normalized video
  <output>.metadata.json  probe results
EOF
}

INPUT=""
OUTPUT=""
TARGET="-14"
GRADE=0
DRY_RUN=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage; exit 0 ;;
    -o|--output) OUTPUT="$2"; shift 2 ;;
    -t|--target) TARGET="$2"; shift 2 ;;
    --grade) GRADE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -*) echo "Unknown option: $1" >&2; usage; exit 2 ;;
    *) INPUT="$1"; shift ;;
  esac
done

[[ -z "$INPUT" ]] && { echo "Missing <input>" >&2; usage; exit 2; }
[[ ! -f "$INPUT" ]] && { echo "Input not found: $INPUT" >&2; exit 1; }

if [[ -z "$OUTPUT" ]]; then
  base="$(basename "$INPUT")"
  OUTPUT="${base%.*}.normalized.mp4"
fi
META="${OUTPUT%.*}.metadata.json"

run() {
  if [[ "${DECLIP_VERBOSE:-0}" == "1" || "$DRY_RUN" == "1" ]]; then
    echo "+ $*" >&2
  fi
  [[ "$DRY_RUN" == "1" ]] || "$@"
}

echo "==> probe"
run sh -c "'$DECLIP' --json probe '$INPUT' > '$META'"

if [[ "$GRADE" == "1" ]]; then
  GRADED="${OUTPUT%.*}.graded.mp4"
  echo "==> auto-grade"
  run "$DECLIP" color-grade "$INPUT" --contrast 1.05 --saturation 1.05 -o "$GRADED"
  STAGED="$GRADED"
else
  STAGED="$INPUT"
fi

echo "==> loudnorm (target $TARGET LUFS)"
case "$TARGET" in
  youtube|tiktok|podcast|broadcast) TGT="$TARGET" ;;
  *) TGT="$TARGET" ;;
esac

if run "$DECLIP" loudnorm "$STAGED" --target "$TGT" -o "$OUTPUT"; then
  echo "==> done: $OUTPUT (metadata: $META)"
else
  echo "loudnorm failed (input may have no audio); copying instead" >&2
  run cp "$STAGED" "$OUTPUT"
fi

# clean up intermediate graded file unless verbose
if [[ "$GRADE" == "1" && "${DECLIP_VERBOSE:-0}" != "1" && "$DRY_RUN" != "1" ]]; then
  rm -f "$GRADED"
fi
