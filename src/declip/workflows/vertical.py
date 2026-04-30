"""Vertical workflow — reframe to 9:16 (TikTok / Reels / Shorts).

See docs/workflows/vertical.md for the recipe.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

from declip.workflows.types import VerticalResult


def run(
    input_path: str,
    output_path: Optional[str] = None,
    mode: str = "crop",
    width: int = 1080,
    height: int = 1920,
    background: str = "#000000",
    target: str = "-14",
    force: bool = False,
) -> VerticalResult:
    """Reframe horizontal video to 9:16.

    Args:
        input_path: Source video path.
        output_path: Destination. Defaults to <basename>.vertical.mp4.
        mode: "crop" (zoom in), "pad" (letterbox), or "blur-pad" (blurred bg plate).
        width: Target width (rounded to even).
        height: Target height (rounded to even).
        background: Pad-mode background colour.
        target: Loudnorm target after reframe.
        force: Reframe even if source is already vertical.
    """
    from declip import probe as probe_mod
    from declip.ops import loudnorm

    started = time.time()
    in_path = Path(input_path)
    if not in_path.exists():
        return VerticalResult(success=False, error=f"input not found: {input_path}")

    if mode not in ("crop", "pad", "blur-pad"):
        return VerticalResult(success=False, error=f"bad mode: {mode}")

    width = (width // 2) * 2
    height = (height // 2) * 2

    if output_path:
        out_path = Path(output_path)
    else:
        out_path = in_path.parent / f"{in_path.stem}.vertical.mp4"

    try:
        info = probe_mod.probe(str(in_path))
    except Exception as e:  # noqa: BLE001
        return VerticalResult(success=False, error=f"probe failed: {e}")

    src_w, src_h = info.width or 0, info.height or 0
    skipped = False
    tmp_reframed = out_path.with_suffix(".tmp_reframed.mp4")

    if src_h > src_w and not force:
        # Already vertical — skip the reframe and just loudnorm.
        from shutil import copyfile
        copyfile(str(in_path), str(tmp_reframed))
        skipped = True
    else:
        # Build FFmpeg filter
        bg = background.lstrip("#")
        if mode == "crop":
            vf = (
                f"scale=if(gt(a\\,{width}/{height})\\,-2\\,{width}):"
                f"if(gt(a\\,{width}/{height})\\,{height}\\,-2),"
                f"crop={width}:{height}"
            )
            cmd = ["ffmpeg", "-y", "-i", str(in_path), "-vf", vf, "-c:a", "copy", str(tmp_reframed)]
        elif mode == "pad":
            vf = (
                f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=0x{bg}"
            )
            cmd = ["ffmpeg", "-y", "-i", str(in_path), "-vf", vf, "-c:a", "copy", str(tmp_reframed)]
        else:  # blur-pad
            fc = (
                f"[0:v]split=2[bg][fg];"
                f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,"
                f"crop={width}:{height},gblur=sigma=30[bgblur];"
                f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[fgsc];"
                f"[bgblur][fgsc]overlay=(W-w)/2:(H-h)/2"
            )
            cmd = ["ffmpeg", "-y", "-i", str(in_path), "-filter_complex", fc, "-c:a", "copy", str(tmp_reframed)]

        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            return VerticalResult(success=False, error=f"ffmpeg reframe failed: {proc.stderr.splitlines()[-1] if proc.stderr else 'unknown'}")

    # Loudnorm pass
    if info.audio_codec is None:
        from shutil import move
        move(str(tmp_reframed), str(out_path))
    else:
        ok, msg = loudnorm(str(tmp_reframed), target=target, output_path=str(out_path))
        try:
            tmp_reframed.unlink(missing_ok=True)
        except OSError:
            pass
        if not ok:
            return VerticalResult(success=False, error=f"loudnorm failed: {msg}")

    return VerticalResult(
        success=True,
        output_path=str(out_path.resolve()),
        duration_seconds=info.duration,
        source_resolution=(src_w, src_h) if src_w and src_h else None,
        target_resolution=(width, height),
        mode=mode,
        skipped_reframe=skipped,
        elapsed_ms=int((time.time() - started) * 1000),
    )
