"""Beat-sync — cut video on the beats of a music track.

See docs/workflows/beat-sync.md for the recipe.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from declip.workflows._render import render_project, write_project_json
from declip.workflows.types import BeatSyncResult


def run(
    video_path: str,
    music_path: str,
    output_path: Optional[str] = None,
    stride: int = 1,
    window: Optional[float] = None,
    write_project: bool = True,
) -> BeatSyncResult:
    """Cut video footage on the beats of a music track.

    Args:
        video_path: Source video.
        music_path: Music audio file.
        output_path: Output .mp4. Defaults to <video-basename>.beat.mp4.
        stride: Cut on every Nth beat (default 1 = every beat).
        window: Clip window length in seconds. Defaults to inter-beat interval.
        write_project: Persist the generated project.json next to the output.
    """
    from declip import probe as probe_mod
    from declip.analyze import detect_beats
    from declip.schema import (
        AudioTrack,
        Clip,
        Output,
        Project,
        Quality,
        Settings,
        Timeline,
        Track,
    )

    started = time.time()
    vid = Path(video_path).resolve()
    mus = Path(music_path).resolve()
    if not vid.exists():
        return BeatSyncResult(success=False, error=f"video not found: {video_path}")
    if not mus.exists():
        return BeatSyncResult(success=False, error=f"music not found: {music_path}")

    if output_path:
        out_path = Path(output_path).resolve()
    else:
        out_path = (vid.parent / f"{vid.stem}.beat.mp4").resolve()

    try:
        v_info = probe_mod.probe(str(vid))
        m_info = probe_mod.probe(str(mus))
    except Exception as e:  # noqa: BLE001
        return BeatSyncResult(success=False, error=f"probe failed: {e}")

    v_dur = float(v_info.duration)
    m_dur = float(m_info.duration)

    # Beats
    try:
        beats_result = detect_beats(str(mus))
    except Exception as e:  # noqa: BLE001
        return BeatSyncResult(success=False, error=f"detect_beats failed: {e}")

    beat_times = [float(t) for t in beats_result.beat_times][::max(1, stride)]
    if not beat_times:
        return BeatSyncResult(success=False, error="no beats detected")

    if window is None:
        window = beat_times[1] - beat_times[0] if len(beat_times) >= 2 else 1.0

    # Sample windows from the source video, evenly distributed
    if v_dur <= window * 1.5:
        v_starts = [0.0] * len(beat_times)
    else:
        step = (v_dur - window) / max(1, len(beat_times) - 1)
        v_starts = [round(i * step, 3) for i in range(len(beat_times))]

    # Build clips, capped at music duration
    clips: list[Clip] = []
    for i, beat_t in enumerate(beat_times):
        if beat_t >= m_dur:
            break
        clip_start = v_starts[i]
        clip_end = min(v_dur, clip_start + window)
        clips.append(
            Clip(
                asset=str(vid),
                start=round(beat_t, 3),
                trim_in=round(clip_start, 3),
                trim_out=round(clip_end, 3),
            )
        )

    if not clips:
        return BeatSyncResult(success=False, error="no clips generated; music shorter than first beat?")

    # Trim last clip to music duration
    last = clips[-1]
    end = float(last.start) + (last.trim_out - last.trim_in)
    if end > m_dur:
        last.trim_out = last.trim_in + max(0.1, m_dur - float(last.start))

    project = Project(
        version="1.0",
        settings=Settings(
            resolution=(v_info.width or 1920, v_info.height or 1080),
            fps=int(v_info.fps or 30),
            background="#000000",
        ),
        timeline=Timeline(
            tracks=[Track(id="video", clips=clips)],
            audio=[AudioTrack(asset=str(mus), start=0, trim_out=round(m_dur, 3))],
        ),
        output=Output(path=str(out_path), quality=Quality.medium),
    )

    project_path: Optional[str] = None
    if write_project:
        project_path = write_project_json(project, out_path.with_suffix(".project.json"))

    success, _ = render_project(project, vid.parent)
    if not success:
        return BeatSyncResult(success=False, error="render failed")

    return BeatSyncResult(
        success=True,
        output_path=str(out_path),
        duration_seconds=m_dur,
        bpm=float(beats_result.tempo),
        beat_count=int(beats_result.beat_count),
        cut_count=len(clips),
        stride=stride,
        project_path=project_path,
        elapsed_ms=int((time.time() - started) * 1000),
    )
