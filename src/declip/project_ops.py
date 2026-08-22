"""Reusable project-level operations shared by adapters and workflows."""
from __future__ import annotations

import json
from pathlib import Path

from declip.compilers.render_plan import build_render_plan, resolve_asset
from declip.output import OutputManager
from declip.schema import PRESETS, PRESET_RESOLUTIONS, FilterType, Project


def init_project(directory: str) -> str:
    path = Path(directory) / "project.json"
    if path.exists():
        return f"Error: {path} already exists"
    template = {
        "version":"1.0",
        "settings":{"resolution":[1920,1080],"fps":30,"background":"#000000"},
        "timeline":{"tracks":[{"id":"main","clips":[{"asset":"input.mp4","start":0}]}],"audio":[]},
        "output":{"path":"output.mp4","format":"mp4","codec":"h264","quality":"high"},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(template, indent=2), encoding="utf-8")
    return f"Created {path}"


def _referenced_paths(project: Project, project_dir: Path) -> list[tuple[str, Path]]:
    references: list[tuple[str, Path]] = []
    for track in project.timeline.tracks:
        for clip in track.clips:
            references.append((clip.asset, Path(resolve_asset(clip.asset, project_dir))))
            for filt in clip.filters:
                if filt.type in {FilterType.lut, FilterType.subtitles} and filt.path:
                    references.append((filt.path, Path(resolve_asset(filt.path, project_dir))))
                if filt.type == FilterType.watermark and filt.watermark:
                    references.append((filt.watermark.image, Path(resolve_asset(filt.watermark.image, project_dir))))
    for audio in project.timeline.audio:
        references.append((audio.asset, Path(resolve_asset(audio.asset, project_dir))))
    return references


def validate_project(project_file: str) -> str:
    try:
        project = Project.load(project_file)
    except Exception as exc:
        return f"Validation error: {exc}"
    project_dir = Path(project_file).parent
    missing = [display for display, path in _referenced_paths(project, project_dir) if not path.exists()]
    tracks = len(project.timeline.tracks)
    clips = sum(len(track.clips) for track in project.timeline.tracks)
    result = f"Valid project: {tracks} track(s), {clips} clip(s), {project.settings.resolution[0]}x{project.settings.resolution[1]} @ {project.settings.fps}fps"
    if missing:
        result += f"\nMissing assets: {', '.join(dict.fromkeys(missing))}"
    return result


def _apply_preset(project: Project, preset: str | None) -> str | None:
    if not preset:
        return None
    if preset not in PRESETS:
        return f"Unknown preset '{preset}'. Available: {', '.join(PRESETS)}"
    output_path = project.output.path
    project.output = PRESETS[preset].model_copy()
    project.output.path = output_path
    if preset in PRESET_RESOLUTIONS:
        project.settings.resolution = PRESET_RESOLUTIONS[preset]
    return None


def _duration(project: Project, project_dir: Path) -> float | None:
    plan = build_render_plan(project, project_dir)
    end = max(
        (float(clip.start) + float(clip.duration or 0.0)
         for track in plan.project.timeline.tracks for clip in track.clips),
        default=0.0,
    )
    return end or None


def render_project_file(
    project_file: str,
    backend: str = "auto",
    output_path: str | None = None,
    preset: str | None = None,
    variables: dict[str, str] | None = None,
) -> str:
    from declip.backends import ffmpeg as ffmpeg_backend
    from declip.backends import mlt as mlt_backend
    if backend not in {"auto", "ffmpeg", "mlt"}:
        return "Error: backend must be auto, ffmpeg, or mlt"
    project_dir = Path(project_file).parent
    try:
        project = Project.load(project_file, variables=variables)
    except Exception as exc:
        return f"Error loading project: {exc}"
    preset_error = _apply_preset(project, preset)
    if preset_error:
        return f"Error: {preset_error}"
    if output_path:
        project.output.path = str(Path(output_path).resolve())
    try:
        total_duration = _duration(project, project_dir)
    except Exception as exc:
        return f"Error normalizing project: {exc}"
    if backend == "auto":
        chosen = "ffmpeg" if ffmpeg_backend.can_handle(project) else "mlt"
    else:
        chosen = backend
    if chosen == "ffmpeg" and not ffmpeg_backend.can_handle(project):
        return "Error: FFmpeg backend cannot preserve this project; use backend='mlt' or 'auto'"
    out = OutputManager(json_mode=False, quiet=True)
    success = (
        ffmpeg_backend.render(project, project_dir, out, total_duration)
        if chosen == "ffmpeg"
        else mlt_backend.render(project, project_dir, out, total_duration)
    )
    if not success:
        detail = out.get_log().strip()
        return f"Render failed via {chosen}." + (f"\n{detail}" if detail else "")
    destination = resolve_asset(project.output.path, project_dir)
    size = Path(destination).stat().st_size if Path(destination).exists() else 0
    return f"Rendered successfully via {chosen}\nOutput: {destination} ({size / 1024 / 1024:.1f} MB)"


def export_mlt(project_file: str) -> str:
    from declip.compilers.mlt import compile_to_string
    try:
        project = Project.load(project_file)
    except Exception as exc:
        return f"Error: {exc}"
    return compile_to_string(project, Path(project_file).parent)


def list_presets() -> str:
    lines = []
    for name, preset in PRESETS.items():
        resolution = PRESET_RESOLUTIONS.get(name, (1920, 1080))
        lines.append(f"{name}: {resolution[0]}x{resolution[1]}, {preset.codec.value}, {preset.quality.value}, audio={preset.audio_codec}")
    return "\n".join(lines)


def assets(project_file: str) -> str:
    from declip.probe import probe
    try:
        project = Project.load(project_file)
    except Exception as exc:
        return f"Error: {exc}"
    project_dir = Path(project_file).parent
    seen: set[Path] = set()
    lines: list[str] = []
    total_size = 0
    for display, path in _referenced_paths(project, project_dir):
        canonical = path.resolve()
        if canonical in seen:
            continue
        seen.add(canonical)
        if not path.exists():
            lines.append(f"MISSING: {display}")
            continue
        try:
            info = probe(path)
            total_size += info.file_size
            lines.append(f"OK: {display} ({info.duration:.1f}s, {info.file_size / 1024 / 1024:.1f}MB, {info.codec})")
        except Exception:
            size = path.stat().st_size
            total_size += size
            lines.append(f"OK: {display} ({size / 1024 / 1024:.1f}MB, non-media asset)")
    lines.append(f"\nTotal: {len(seen)} asset(s), {total_size / 1024 / 1024:.1f} MB")
    return "\n".join(lines)


def batch_render(project_files: list[str], preset: str | None = None) -> str:
    results = []
    for project_file in project_files:
        result = render_project_file(project_file, backend="auto", preset=preset)
        status = "OK" if result.startswith("Rendered successfully") else "FAILED"
        first_line = result.splitlines()[0]
        results.append(f"{status}: {project_file}: {first_line}")
    return "\n".join(results)
