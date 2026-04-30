"""Helpers for rendering an in-memory declip Project from a workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from declip.output import OutputManager
from declip.schema import Project


def render_project(
    project: Project,
    project_dir: Path,
    quiet: bool = True,
) -> tuple[bool, OutputManager]:
    """Render an in-memory Project. Returns (success, output_manager).

    The OutputManager is returned for callers that want to inspect events
    (e.g. for verbose mode). When `quiet=True`, no stdout writes happen,
    making this safe to call from MCP tools.
    """
    from declip.backends import ffmpeg as ffmpeg_backend
    from declip.backends import mlt as mlt_backend

    out = OutputManager(json_mode=False, quiet=quiet)
    project.resolve_auto_starts(project_dir)

    use_ffmpeg = ffmpeg_backend.can_handle(project)
    if use_ffmpeg:
        success = ffmpeg_backend.render(project, project_dir, out, None)
    else:
        success = mlt_backend.render(project, project_dir, out, None)

    return success, out


def write_project_json(project: Project, path: str | Path) -> str:
    """Persist a Project to disk as JSON. Returns the absolute path written."""
    p = Path(path).resolve()
    p.parent.mkdir(parents=True, exist_ok=True)
    project.save(p)
    return str(p)


def project_duration(project: Project, project_dir: Path) -> Optional[float]:
    """Best-effort estimate of timeline duration in seconds."""
    project.resolve_auto_starts(project_dir)
    max_end = 0.0
    for track in project.timeline.tracks:
        for clip in track.clips:
            if clip.duration is not None:
                end = float(clip.start) + clip.duration
            elif clip.trim_out is not None:
                end = float(clip.start) + (clip.trim_out - clip.trim_in)
            else:
                continue
            if end > max_end:
                max_end = end
    return max_end if max_end > 0 else None
