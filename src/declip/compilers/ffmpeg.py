"""Compile normalized Declip projects into FFmpeg argv vectors.

Compilation is pure with one exception: audio-stream detection inspects input media.
No FFmpeg render subprocess is executed here; execution belongs to ``declip.backends``.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from declip.compilers.render_plan import RenderPlan, build_render_plan, resolve_asset
from declip.filters.ffmpeg import build_audio_filters, build_video_filters, get_watermark_config
from declip.schema import Clip, OutputCodec, Project, Quality, TransitionType

_CRF = {Quality.low:"28", Quality.medium:"23", Quality.high:"18", Quality.lossless:"0"}
_ENCODER = {OutputCodec.h264:"libx264", OutputCodec.h265:"libx265", OutputCodec.prores:"prores_ks", OutputCodec.vp9:"libvpx-vp9"}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
_XFADE = {
    "dissolve":"fade", "fade_black":"fadeblack", "fade_white":"fadewhite", "fade_grays":"fadegrays",
    "circle_open":"circleopen", "circle_close":"circleclose", "circle_crop":"circlecrop", "rect_crop":"rectcrop",
    "horz_open":"horzopen", "horz_close":"horzclose", "vert_open":"vertopen", "vert_close":"vertclose",
    "diag_tl":"diagtl", "diag_tr":"diagtr", "diag_bl":"diagbl", "diag_br":"diagbr",
    "hl_slice":"hlslice", "hr_slice":"hrslice", "vu_slice":"vuslice", "vd_slice":"vdslice", "zoom_in":"zoomin",
    "squeeze_h":"squeezeh", "squeeze_v":"squeezev", "hl_wind":"hlwind", "hr_wind":"hrwind", "vu_wind":"vuwind", "vd_wind":"vdwind",
    "wipe_left":"wipeleft", "wipe_right":"wiperight", "wipe_up":"wipeup", "wipe_down":"wipedown",
    "slide_left":"slideleft", "slide_right":"slideright", "slide_up":"slideup", "slide_down":"slidedown",
    "smooth_left":"smoothleft", "smooth_right":"smoothright", "smooth_up":"smoothup", "smooth_down":"smoothdown",
    "cover_left":"coverleft", "cover_right":"coverright", "cover_up":"coverup", "cover_down":"coverdown",
    "reveal_left":"revealleft", "reveal_right":"revealright", "reveal_up":"revealup", "reveal_down":"revealdown",
    "radial":"radial", "distance":"distance", "pixelize":"pixelize",
}


class CompilationError(ValueError):
    """The project requests semantics this compiler cannot preserve."""


@dataclass(frozen=True)
class FFmpegCompilation:
    plan: RenderPlan
    commands: tuple[tuple[str, ...], ...]


def resolve_output_path(project: Project, project_dir: Path) -> str:
    return resolve_asset(project.output.path, project_dir)


def _quality_args(project: Project) -> list[str]:
    encoder = _ENCODER[project.output.codec]
    args = ["-c:v", encoder]
    if project.output.codec in (OutputCodec.h264, OutputCodec.h265):
        args += ["-crf", _CRF[project.output.quality]]
        if project.output.codec == OutputCodec.h264:
            args += ["-preset", "medium"]
    elif project.output.codec == OutputCodec.prores:
        profiles = {"low":"0", "medium":"2", "high":"3", "lossless":"4"}
        args += ["-profile:v", profiles[project.output.quality.value]]
    return args


def _known_duration(clip: Clip) -> float | None:
    if clip.duration is not None:
        return float(clip.duration)
    if clip.trim_out is not None:
        return float(clip.trim_out - clip.trim_in)
    return None


def _sequential_layout(project: Project, tolerance: float = 1e-3) -> bool:
    """Whether the one-track project can be represented by concat/xfade only.

    Arbitrary timeline gaps and overlaps require explicit timeline composition.
    Rather than silently collapsing them, auto backend selection routes those
    projects to MLT. ``start='auto'`` is an explicit request for sequential
    placement and is therefore safe even when source duration must be probed later.
    """
    if len(project.timeline.tracks) != 1:
        return False
    clips = project.timeline.tracks[0].clips
    previous_start: float | None = None
    previous_duration: float | None = None
    for index, clip in enumerate(clips):
        if index == 0:
            if clip.start != "auto" and abs(float(clip.start)) > tolerance:
                return False
            current_start = 0.0 if clip.start == "auto" else float(clip.start)
        elif clip.start == "auto":
            current_start = None
        else:
            if previous_start is None or previous_duration is None:
                return False
            expected = previous_start + previous_duration
            if clip.transition_in is not None:
                expected -= float(clip.transition_in.duration)
            current_start = float(clip.start)
            if abs(current_start - expected) > tolerance:
                return False
        current_duration = _known_duration(clip)
        if current_start is None:
            if previous_start is not None and previous_duration is not None:
                current_start = previous_start + previous_duration
                if clip.transition_in is not None:
                    current_start -= float(clip.transition_in.duration)
            else:
                previous_start = None
                previous_duration = current_duration
                continue
        previous_start = current_start
        previous_duration = current_duration
    return True


def can_handle(project: Project) -> bool:
    if len(project.timeline.tracks) != 1 or project.timeline.audio:
        return False
    if any(clip.position for clip in project.timeline.tracks[0].clips):
        return False
    return _sequential_layout(project)


def _source_duration(clip: Clip) -> float:
    if clip.trim_out is not None:
        return float(clip.trim_out - clip.trim_in)
    return float(clip.duration or 0.0)


def _clip_input_args(clip: Clip, asset: str, fps: int) -> list[str]:
    args: list[str] = []
    is_image = Path(asset).suffix.lower() in _IMAGE_EXTENSIONS
    if is_image:
        args += ["-loop", "1", "-framerate", str(fps)]
    if clip.freeze_frame is not None and not is_image:
        if clip.freeze_frame > 0:
            args += ["-ss", str(clip.freeze_frame)]
        duration = float(clip.duration or 0.0)
    else:
        if clip.trim_in > 0 and not is_image:
            args += ["-ss", str(clip.trim_in)]
        duration = float(clip.duration or 0.0) if is_image else _source_duration(clip)
    if duration > 0:
        args += ["-t", str(duration)]
    return args + ["-i", asset]


def _has_audio(asset_path: str) -> bool:
    if Path(asset_path).suffix.lower() in _IMAGE_EXTENSIONS:
        return False
    try:
        import av
        container = av.open(asset_path)
        try:
            return len(container.streams.audio) > 0
        finally:
            container.close()
    except Exception:
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            return True
        try:
            proc = subprocess.run(
                [ffprobe, "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", asset_path],
                capture_output=True, text=True, timeout=10,
            )
            return proc.returncode == 0 and bool(proc.stdout.strip())
        except Exception:
            return True


def _xfade_name(transition: TransitionType) -> str:
    return _XFADE.get(transition.value, transition.value.replace("_", ""))


def _append_clip_video(parts: list[str], clip: Clip, primary_index: int, watermark_index: int | None, clip_index: int, project: Project) -> str:
    width, height = project.settings.resolution
    filters = build_video_filters(clip, width=width, height=height, fps=project.settings.fps, background=project.settings.background)
    base_label = f"vbase{clip_index}" if watermark_index is not None else f"v{clip_index}"
    parts.append(f"[{primary_index}:v]{','.join(filters)}[{base_label}]")
    if watermark_index is None:
        return base_label
    watermark = get_watermark_config(clip)
    assert watermark is not None
    scaled_width = max(1, int(width * watermark.scale))
    wm_label, output_label = f"wm{clip_index}", f"v{clip_index}"
    parts.append(f"[{watermark_index}:v]scale={scaled_width}:-1,format=rgba,colorchannelmixer=aa={watermark.opacity}[{wm_label}]")
    parts.append(f"[{base_label}][{wm_label}]overlay=x='(W-w)*{watermark.position[0]}':y='(H-h)*{watermark.position[1]}':eof_action=repeat:shortest=0[{output_label}]")
    return output_label


def _append_clip_audio(parts: list[str], clip: Clip, primary_index: int, clip_index: int, has_audio: bool) -> str:
    output_label = f"a{clip_index}"
    if has_audio:
        parts.append(f"[{primary_index}:a]{','.join(build_audio_filters(clip))}[{output_label}]")
    else:
        duration = float(clip.duration or 0.0)
        parts.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={duration},asetpts=PTS-STARTPTS[{output_label}]")
    return output_label


def _chain_video(parts: list[str], clips: list[Clip], labels: list[str]) -> str:
    if len(labels) == 1:
        parts.append(f"[{labels[0]}]null[outv]")
        return "outv"
    previous = labels[0]
    output_duration = float(clips[0].duration or 0.0)
    for index in range(1, len(labels)):
        clip = clips[index]
        output = f"vchain{index}" if index < len(labels) - 1 else "outv"
        if clip.transition_in is not None:
            duration = float(clip.transition_in.duration)
            current_duration = float(clip.duration or 0.0)
            if duration >= output_duration or duration >= current_duration:
                raise CompilationError(
                    f"transition into clip {index} ({duration}s) must be shorter than both adjacent compiled durations ({output_duration}s, {current_duration}s)"
                )
            offset = max(0.0, output_duration - duration)
            parts.append(f"[{previous}][{labels[index]}]xfade=transition={_xfade_name(clip.transition_in.type)}:duration={duration}:offset={offset}[{output}]")
            output_duration = offset + current_duration
        else:
            parts.append(f"[{previous}][{labels[index]}]concat=n=2:v=1:a=0[{output}]")
            output_duration += float(clip.duration or 0.0)
        previous = output
    return previous


def _chain_audio(parts: list[str], clips: list[Clip], labels: list[str]) -> str:
    if len(labels) == 1:
        parts.append(f"[{labels[0]}]anull[outa]")
        return "outa"
    previous = labels[0]
    for index in range(1, len(labels)):
        clip = clips[index]
        output = f"achain{index}" if index < len(labels) - 1 else "outa"
        if clip.transition_in is not None:
            parts.append(f"[{previous}][{labels[index]}]acrossfade=d={float(clip.transition_in.duration)}:c1=tri:c2=tri[{output}]")
        else:
            parts.append(f"[{previous}][{labels[index]}]concat=n=2:v=0:a=1[{output}]")
        previous = output
    return previous


def _timeline_command(project: Project, project_dir: Path) -> list[str]:
    if not can_handle(project):
        raise CompilationError(
            "FFmpeg compiler supports one sequential unpositioned video track and no dedicated audio tracks; use the MLT backend for arbitrary timeline placement"
        )
    clips = list(project.timeline.tracks[0].clips)
    if not clips:
        raise CompilationError("project contains no clips")
    command = ["ffmpeg", "-y"]
    primary_indices: list[int] = []
    asset_paths: list[str] = []
    input_count = 0
    for clip in clips:
        asset = resolve_asset(clip.asset, project_dir)
        asset_paths.append(asset)
        primary_indices.append(input_count)
        command += _clip_input_args(clip, asset, project.settings.fps)
        input_count += 1
    watermark_indices: list[int | None] = []
    for clip in clips:
        watermark = get_watermark_config(clip)
        if watermark is None:
            watermark_indices.append(None)
        else:
            watermark_indices.append(input_count)
            command += ["-i", resolve_asset(watermark.image, project_dir)]
            input_count += 1
    audio_flags = [_has_audio(asset) for asset in asset_paths]
    parts: list[str] = []
    video_labels: list[str] = []
    audio_labels: list[str] = []
    for index, clip in enumerate(clips):
        video_labels.append(_append_clip_video(parts, clip, primary_indices[index], watermark_indices[index], index, project))
        audio_labels.append(_append_clip_audio(parts, clip, primary_indices[index], index, audio_flags[index]))
    _chain_video(parts, clips, video_labels)
    _chain_audio(parts, clips, audio_labels)
    command += ["-filter_complex", ";".join(parts), "-map", "[outv]", "-map", "[outa]"]
    command += _quality_args(project)
    command += ["-c:a", project.output.audio_codec, "-b:a", project.output.audio_bitrate, resolve_output_path(project, project_dir)]
    return command


def compile_project(project: Project, project_dir: Path) -> FFmpegCompilation:
    plan = build_render_plan(project, project_dir)
    return FFmpegCompilation(plan=plan, commands=(tuple(_timeline_command(plan.project, plan.project_dir)),))


def compile_commands(project: Project, project_dir: Path) -> list[list[str]]:
    return [list(command) for command in compile_project(project, project_dir).commands]
