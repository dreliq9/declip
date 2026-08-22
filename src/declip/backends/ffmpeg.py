"""FFmpeg execution backend.

Compilation lives in :mod:`declip.compilers.ffmpeg`; this module only selects the
binary, executes compiled argv, reports progress, and preserves the historical
backend API used by CLI/MCP callers.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from declip.compilers.ffmpeg import CompilationError, can_handle, compile_commands, compile_project, resolve_output_path
from declip.output import OutputManager
from declip.schema import Project

__all__ = ["can_handle", "compile_commands", "render"]

def _parse_ffmpeg_progress(line: str, total_duration: float | None) -> float | None:
    match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
    if match and total_duration and total_duration > 0:
        hours, minutes, seconds = int(match.group(1)), int(match.group(2)), float(match.group(3))
        return min((hours * 3600 + minutes * 60 + seconds) / total_duration, 1.0)
    return None

def render(project: Project, project_dir: Path, out: OutputManager, total_duration: float | None = None) -> bool:
    if not shutil.which("ffmpeg"):
        out.error("render", "ffmpeg not found in PATH")
        return False
    try:
        compiled = compile_project(project, project_dir)
    except CompilationError as exc:
        out.error("compile", str(exc))
        return False
    for warning in compiled.plan.warnings:
        out.emit("warning", f"  Warning: {warning.message}", code=warning.code, track_id=warning.track_id, clip_index=warning.clip_index)
    commands = [list(command) for command in compiled.commands]
    out.emit("compile", f"  Compiled {len(commands)} FFmpeg command(s)", backend="ffmpeg", commands=len(commands))
    for index, command in enumerate(commands):
        out.emit("render", f"  Executing FFmpeg ({index + 1}/{len(commands)})...", step=index + 1, total=len(commands))
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stderr_lines: list[str] = []
        assert proc.stderr is not None
        for raw_line in proc.stderr:
            line = raw_line.decode(errors="replace")
            stderr_lines.append(line)
            progress = _parse_ffmpeg_progress(line, total_duration)
            if progress is not None:
                out.progress(progress)
        proc.wait()
        if proc.returncode != 0:
            out.error("render", f"FFmpeg failed (exit {proc.returncode}): {''.join(stderr_lines[-10:])}")
            return False
    out.progress(1.0)
    output_path = resolve_output_path(compiled.plan.project, compiled.plan.project_dir)
    size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
    out.emit("complete", f"  Output: {output_path} ({size / 1024 / 1024:.1f} MB)", output=output_path, size_bytes=size)
    return True
