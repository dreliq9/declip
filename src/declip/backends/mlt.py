"""MLT execution backend.

XML compilation lives in :mod:`declip.compilers.mlt`; this module is the runtime
adapter around the ``melt`` executable and preserves the historical backend API.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from declip.compilers.mlt import (
    CompilationError,
    bitrate_for,
    compile_project,
    compile_to_string,
    compile_xml,
    encoder_for,
    resolve_output_path,
)
from declip.compilers.render_plan import RenderPlanError
from declip.filters.mlt import seconds_to_frames
from declip.output import OutputManager
from declip.schema import Project

__all__ = ["compile_xml", "compile_to_string", "render"]


def _parse_melt_progress(line: str, total_frames: int | None) -> float | None:
    match = re.search(r"Current Frame:\s*(\d+)", line)
    if match and total_frames and total_frames > 0:
        return min(int(match.group(1)) / total_frames, 1.0)
    return None


def render(project: Project, project_dir: Path, out: OutputManager, total_duration: float | None = None) -> bool:
    melt_bin = shutil.which("melt")
    if not melt_bin:
        out.error("render", "melt not found in PATH — install with: brew install mlt")
        return False

    try:
        compiled = compile_project(project, project_dir)
    except (CompilationError, RenderPlanError) as exc:
        out.error("compile", str(exc))
        return False

    for warning in compiled.plan.warnings:
        out.emit("warning", f"  Warning: {warning.message}", code=warning.code, track_id=warning.track_id, clip_index=warning.clip_index)
    out.emit("compile", f"  Compiled MLT XML ({len(compiled.xml)} bytes)", backend="mlt", xml_bytes=len(compiled.xml))

    with tempfile.NamedTemporaryFile(suffix=".mlt", mode="w", delete=False) as handle:
        handle.write(compiled.xml)
        xml_path = handle.name

    normalized = compiled.plan.project
    output_path = resolve_output_path(normalized, compiled.plan.project_dir)
    width, height = normalized.settings.resolution
    command = [
        melt_bin, xml_path,
        "-consumer", f"avformat:{output_path}",
        "real_time=-1",
        f"width={width}", f"height={height}",
        f"vcodec={encoder_for(normalized)}", f"vb={bitrate_for(normalized)}",
        f"acodec={normalized.output.audio_codec}", f"ab={normalized.output.audio_bitrate}",
        "terminate_on_pause=1",
    ]
    out.emit("render", "  Rendering via melt...", command=" ".join(command))
    total_frames = seconds_to_frames(total_duration, normalized.settings.fps) if total_duration else None

    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stderr_lines: list[str] = []
    assert proc.stderr is not None
    for raw_line in proc.stderr:
        line = raw_line.decode(errors="replace")
        stderr_lines.append(line)
        progress = _parse_melt_progress(line, total_frames)
        if progress is not None:
            out.progress(progress)
    proc.wait()
    Path(xml_path).unlink(missing_ok=True)

    if proc.returncode != 0:
        out.error("render", f"melt failed (exit {proc.returncode}): {''.join(stderr_lines[-10:])}")
        return False

    out.progress(1.0)
    size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
    out.emit("complete", f"  Output: {output_path} ({size / 1024 / 1024:.1f} MB)", output=output_path, size_bytes=size)
    return True
