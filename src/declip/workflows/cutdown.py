"""Cutdown workflow — long source → short highlight reel.

See docs/workflows/cutdown.md for the recipe.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

from declip.workflows._render import project_duration, render_project, write_project_json
from declip.workflows.types import CutdownResult, CutdownSegment


def run(
    input_path: str,
    output_path: Optional[str] = None,
    target_seconds: float = 60.0,
    transition: str = "dissolve",
    crossfade_duration: float = 0.5,
    segment_min: float = 3.0,
    segment_max: float = 10.0,
    scene_threshold: float = 27.0,
    write_project: bool = True,
) -> CutdownResult:
    """Cut a long source down to a short highlight reel.

    Args:
        input_path: Source video.
        output_path: Output .mp4. Defaults to <basename>.cutdown.mp4.
        target_seconds: Target highlight duration.
        transition: Transition type (declip TransitionType — dissolve, fade_black, etc).
        crossfade_duration: Transition duration in seconds.
        segment_min: Minimum candidate segment length to consider.
        segment_max: Maximum candidate segment length per clip.
        scene_threshold: PySceneDetect ContentDetector threshold.
        write_project: Persist the generated project.json next to the output.
    """
    from declip import probe as probe_mod
    from declip.analyze import detect_scenes, detect_silence
    from declip.schema import (
        Clip,
        Filter,
        FilterType,
        Output,
        Project,
        Quality,
        Settings,
        Timeline,
        Track,
        Transition,
        TransitionType,
    )

    started = time.time()
    in_path = Path(input_path).resolve()
    if not in_path.exists():
        return CutdownResult(success=False, error=f"input not found: {input_path}")

    if output_path:
        out_path = Path(output_path).resolve()
    else:
        out_path = (in_path.parent / f"{in_path.stem}.cutdown.mp4").resolve()

    # Probe
    try:
        info = probe_mod.probe(str(in_path))
    except Exception as e:  # noqa: BLE001
        return CutdownResult(success=False, error=f"probe failed: {e}")

    duration = float(info.duration)

    # Scene detection
    try:
        cuts = detect_scenes(str(in_path), threshold=scene_threshold)
    except Exception as e:  # noqa: BLE001
        return CutdownResult(success=False, error=f"detect_scenes failed: {e}")

    cut_times = sorted({0.0} | {float(c.timestamp) for c in cuts} | {duration})

    # Silence detection (used to drop silent segments)
    try:
        silence = detect_silence(str(in_path))
    except Exception:  # noqa: BLE001 — silence detection is advisory; non-fatal
        silence = []
    silence_ranges = [(float(s.start), float(s.end)) for s in silence]

    # Candidate segments between cuts, with silence trimming and length cap.
    raw_segments: list[tuple[float, float]] = []
    for a, b in zip(cut_times, cut_times[1:]):
        if b - a < segment_min:
            continue
        seg_start, seg_end = a, b
        for sa, sb in silence_ranges:
            if sb <= seg_start or sa >= seg_end:
                continue
            overlap = min(seg_end, sb) - max(seg_start, sa)
            if overlap > 0.5 * (seg_end - seg_start):
                seg_end = seg_start  # mark dropped
                break
        if seg_end - seg_start < segment_min:
            continue
        if seg_end - seg_start > segment_max:
            seg_end = seg_start + segment_max
        raw_segments.append((seg_start, seg_end))

    # Fallback to evenly-spaced sampling when scene-detect produced too little
    fallback_used = False
    total_raw = sum(b - a for a, b in raw_segments)
    if not raw_segments or total_raw < target_seconds * 0.8:
        fallback_used = True
        n_segs = max(3, int(target_seconds / segment_max))
        seg_len = min(segment_max, max(segment_min, target_seconds / n_segs))
        spacing = (duration - seg_len) / max(1, n_segs - 1) if n_segs > 1 else 0
        raw_segments = [(i * spacing, i * spacing + seg_len) for i in range(n_segs)]

    # Pick segments to hit target — longest first, then sorted timeline order.
    raw_segments.sort(key=lambda s: s[1] - s[0], reverse=True)
    picked: list[tuple[float, float]] = []
    total = 0.0
    for seg in raw_segments:
        seg_dur = seg[1] - seg[0]
        if total + seg_dur > target_seconds * 1.1:
            continue
        picked.append(seg)
        total += seg_dur
        if total >= target_seconds * 0.9:
            break

    if not picked:
        picked = raw_segments[:1]

    picked.sort(key=lambda s: s[0])

    # Build the Project
    clips: list[Clip] = []
    for i, (a, b) in enumerate(picked):
        filters: list[Filter] = []
        transition_in = None
        if i == 0:
            filters.append(Filter(type=FilterType.fade_in, duration=0.5))
        else:
            transition_in = Transition(type=TransitionType(transition), duration=crossfade_duration)
        if i == len(picked) - 1:
            filters.append(Filter(type=FilterType.fade_out, duration=0.5))
        clip_kwargs = {
            "asset": str(in_path),
            "start": 0 if i == 0 else "auto",
            "trim_in": round(a, 3),
            "trim_out": round(b, 3),
        }
        if filters:
            clip_kwargs["filters"] = filters
        if transition_in is not None:
            clip_kwargs["transition_in"] = transition_in
        clips.append(Clip(**clip_kwargs))

    project = Project(
        version="1.0",
        settings=Settings(
            resolution=(info.width or 1920, info.height or 1080),
            fps=int(info.fps or 30),
            background="#000000",
        ),
        timeline=Timeline(tracks=[Track(id="main", clips=clips)]),
        output=Output(path=str(out_path), quality=Quality.medium),
    )

    project_path: Optional[str] = None
    project_dir = in_path.parent
    if write_project:
        project_path = write_project_json(project, out_path.with_suffix(".project.json"))

    success, _ = render_project(project, project_dir)
    if not success:
        return CutdownResult(success=False, error="render failed")

    # Probe the rendered output for true duration
    try:
        out_info = probe_mod.probe(str(out_path))
        rendered_dur = float(out_info.duration)
    except Exception:  # noqa: BLE001
        rendered_dur = project_duration(project, project_dir) or 0.0

    return CutdownResult(
        success=True,
        output_path=str(out_path),
        duration_seconds=rendered_dur,
        source_duration_seconds=duration,
        segments=[CutdownSegment(start=a, end=b) for a, b in picked],
        fallback_used=fallback_used,
        project_path=project_path,
        elapsed_ms=int((time.time() - started) * 1000),
    )
