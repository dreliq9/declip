"""Helpers for rendering an in-memory Declip Project from a workflow."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from declip.compilers.render_plan import build_render_plan
from declip.output import OutputManager
from declip.schema import Project


def render_project(project: Project, project_dir: Path, quiet: bool = True) -> tuple[bool, OutputManager]:
    """Render an in-memory Project without mutating the caller-owned schema."""
    from declip.backends import ffmpeg as ffmpeg_backend
    from declip.backends import mlt as mlt_backend
    out = OutputManager(json_mode=False, quiet=quiet)
    if ffmpeg_backend.can_handle(project):
        success = ffmpeg_backend.render(project, project_dir, out, None)
    else:
        success = mlt_backend.render(project, project_dir, out, None)
    return success, out

def write_project_json(project: Project, path: str | Path) -> str:
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    project.save(p)
    return str(p)

def project_duration(project: Project, project_dir: Path) -> Optional[float]:
    """Best-effort normalized timeline duration in seconds."""
    plan = build_render_plan(project, project_dir)
    max_end = 0.0
    for track in plan.project.timeline.tracks:
        for clip in track.clips:
            max_end = max(max_end, float(clip.start) + float(clip.duration or 0.0))
    return max_end if max_end > 0 else None
