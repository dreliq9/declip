"""Speech cleanup — talking-head jump-cut edit.

See docs/workflows/speech-cleanup.md for the recipe.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Optional

from declip.workflows._render import render_project, write_project_json
from declip.workflows.types import SpeechCleanupResult


def run(
    input_path: str,
    output_path: Optional[str] = None,
    gap: float = 0.5,
    pad: float = 0.1,
    burn_captions: bool = False,
    write_project: bool = True,
    whisper_model: str = "base",
) -> SpeechCleanupResult:
    """Build a jump-cut edit from a talking-head video.

    Args:
        input_path: Source video.
        output_path: Output .mp4. Defaults to <basename>.cleaned.mp4.
        gap: Drop silent gaps longer than this (seconds).
        pad: Pad each kept segment with this much head/tail (seconds).
        burn_captions: Burn the SRT into the rendered output (requires libass).
        write_project: Persist the generated project.json next to the output.
        whisper_model: faster-whisper model size (tiny/base/small/medium/large-v3).
    """
    from declip import probe as probe_mod
    from declip.analyze import transcribe
    from declip.schema import (
        Clip,
        Output,
        Project,
        Quality,
        Settings,
        Timeline,
        Track,
    )

    started = time.time()
    in_path = Path(input_path).resolve()
    if not in_path.exists():
        return SpeechCleanupResult(success=False, error=f"input not found: {input_path}")

    if output_path:
        out_path = Path(output_path).resolve()
    else:
        out_path = (in_path.parent / f"{in_path.stem}.cleaned.mp4").resolve()

    srt_path = out_path.with_suffix(".srt")

    try:
        info = probe_mod.probe(str(in_path))
    except Exception as e:  # noqa: BLE001
        return SpeechCleanupResult(success=False, error=f"probe failed: {e}")

    duration = float(info.duration)

    # Transcribe → SRT + structured segments
    try:
        result = transcribe(str(in_path), output_srt=str(srt_path), model_size=whisper_model)
    except Exception as e:  # noqa: BLE001
        return SpeechCleanupResult(success=False, error=f"transcribe failed: {e}")

    if not result.subtitles:
        return SpeechCleanupResult(
            success=False,
            error="no speech detected — nothing to clean",
            srt_path=str(srt_path) if srt_path.exists() else None,
        )

    # Apply pad and clamp
    padded = [
        (max(0.0, float(s.start) - pad), min(duration, float(s.end) + pad))
        for s in result.subtitles
    ]

    # Merge segments separated by < gap
    merged: list[tuple[float, float]] = [padded[0]]
    for a, b in padded[1:]:
        pa, pb = merged[-1]
        if a - pb < gap:
            merged[-1] = (pa, b)
        else:
            merged.append((a, b))

    # Build the Project
    clips = [
        Clip(
            asset=str(in_path),
            start=0 if i == 0 else "auto",
            trim_in=round(a, 3),
            trim_out=round(b, 3),
        )
        for i, (a, b) in enumerate(merged)
    ]

    project = Project(
        version="1.0",
        settings=Settings(
            resolution=(info.width or 1920, info.height or 1080),
            fps=int(info.fps or 30),
            background="#000000",
        ),
        timeline=Timeline(tracks=[Track(id="main", clips=clips)]),
        output=Output(path=str(out_path), quality=Quality.high),
    )

    project_path: Optional[str] = None
    if write_project:
        project_path = write_project_json(project, out_path.with_suffix(".project.json"))

    success, _ = render_project(project, in_path.parent)
    if not success:
        return SpeechCleanupResult(success=False, error="render failed")

    captions_burned = False
    if burn_captions and srt_path.exists():
        burned = out_path.with_suffix(".captioned.mp4")
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", str(out_path),
             "-vf", f"subtitles={srt_path}",
             "-c:a", "copy", str(burned)],
            capture_output=True, text=True,
        )
        if proc.returncode == 0:
            burned.replace(out_path)
            captions_burned = True
        # Otherwise leave the SRT sidecar; the rendered output without burned captions is still valid.

    kept_seconds = sum(b - a for a, b in merged)

    return SpeechCleanupResult(
        success=True,
        output_path=str(out_path),
        duration_seconds=kept_seconds,
        source_duration_seconds=duration,
        segments_kept=len(merged),
        kept_seconds=kept_seconds,
        srt_path=str(srt_path) if srt_path.exists() else None,
        captions_burned=captions_burned,
        project_path=project_path,
        elapsed_ms=int((time.time() - started) * 1000),
    )
