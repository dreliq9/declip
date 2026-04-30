"""Ingest workflow — probe + loudnorm + optional auto-grade.

Normalizes an arbitrary input video to a known-good baseline before further
editing. See docs/workflows/ingest.md for the recipe.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from declip.workflows.types import IngestResult


def run(
    input_path: str,
    output_path: Optional[str] = None,
    target: str = "-14",
    grade: bool = False,
    write_metadata: bool = True,
) -> IngestResult:
    """Run the ingest workflow.

    Args:
        input_path: Source video path.
        output_path: Destination .mp4. Defaults to <basename>.normalized.mp4.
        target: Loudnorm target. Accepts a name (youtube/tiktok/podcast/broadcast)
                or a LUFS number like "-14".
        grade: When True, apply a neutral auto-grade (slight contrast/saturation lift).
        write_metadata: When True, write a probe JSON sidecar at <output>.metadata.json.
    """
    from declip import probe as probe_mod
    from declip.ops import color_grade, loudnorm, resolve_loudnorm_target

    started = time.time()
    in_path = Path(input_path)
    if not in_path.exists():
        return IngestResult(success=False, error=f"input not found: {input_path}")

    if output_path:
        out_path = Path(output_path)
    else:
        out_path = in_path.parent / f"{in_path.stem}.normalized.mp4"

    # Probe
    try:
        info = probe_mod.probe(str(in_path))
    except Exception as e:  # noqa: BLE001
        return IngestResult(success=False, error=f"probe failed: {e}")

    metadata_path: Optional[str] = None
    if write_metadata:
        metadata_path = str(out_path.with_suffix(".metadata.json").resolve())
        Path(metadata_path).parent.mkdir(parents=True, exist_ok=True)
        with open(metadata_path, "w") as f:
            json.dump(info.to_dict(), f, indent=2)

    # Optional grade
    staged_input = str(in_path)
    graded = False
    if grade:
        graded_path = str(out_path.with_suffix(".graded.mp4").resolve())
        ok, msg = color_grade(
            staged_input,
            midtones_r=0.02, midtones_g=0.02, midtones_b=0.02,
            auto_levels=True,
            output_path=graded_path,
        )
        if ok:
            staged_input = graded_path
            graded = True
        else:
            return IngestResult(success=False, error=f"color_grade failed: {msg}")

    # Loudnorm
    target_lufs, err = resolve_loudnorm_target(target)
    if err:
        return IngestResult(success=False, error=err)

    skipped_loudnorm = False
    if info.audio_codec is None:
        # No audio — just copy the staged file
        from shutil import copyfile
        copyfile(staged_input, str(out_path))
        skipped_loudnorm = True
    else:
        ok, msg = loudnorm(staged_input, target=target, output_path=str(out_path))
        if not ok:
            return IngestResult(success=False, error=f"loudnorm failed: {msg}")

    # Tidy up intermediate graded file if we made one
    if graded:
        try:
            Path(staged_input).unlink(missing_ok=True)
        except OSError:
            pass

    return IngestResult(
        success=True,
        output_path=str(out_path.resolve()),
        duration_seconds=info.duration,
        metadata_path=metadata_path,
        target_lufs=target_lufs,
        graded=graded,
        skipped_loudnorm=skipped_loudnorm,
        elapsed_ms=int((time.time() - started) * 1000),
    )
