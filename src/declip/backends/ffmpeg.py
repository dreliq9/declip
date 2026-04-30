"""FFmpeg backend — compiles a Project into ffmpeg commands and executes them."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from declip.output import OutputManager
from declip.schema import (
    Clip, FilterType, OutputCodec, Project, Quality, Track, TransitionType,
)

# Quality → CRF mapping for h264/h265
_CRF = {Quality.low: "28", Quality.medium: "23", Quality.high: "18", Quality.lossless: "0"}

# Codec → ffmpeg encoder name
_ENCODER = {
    OutputCodec.h264: "libx264",
    OutputCodec.h265: "libx265",
    OutputCodec.prores: "prores_ks",
    OutputCodec.vp9: "libvpx-vp9",
}


def _resolve_asset(asset: str, project_dir: Path) -> str:
    p = Path(asset)
    if p.is_absolute():
        return str(p)
    return str(project_dir / p)


def _hex_to_ffmpeg_color(hex_color: str) -> str:
    """Convert #RRGGBB to FFmpeg color format."""
    return "0x" + hex_color.lstrip("#")


def _get_clip_duration(clip: Clip) -> float | None:
    """Get the effective clip duration from trim/duration fields, or None if unknown."""
    if clip.duration is not None:
        return clip.duration
    if clip.trim_out is not None:
        return clip.trim_out - clip.trim_in
    return None


def _get_watermark_config(clip: Clip):
    """Extract watermark config from a clip's filters, if any."""
    for f in clip.filters:
        if f.type == FilterType.watermark and f.watermark:
            return f.watermark
    return None


def _watermark_overlay_args(wm, project_dir: Path, w: int, h: int) -> tuple[list[str], str]:
    """Build FFmpeg input args and filter_complex fragment for a watermark overlay.

    Returns (extra_input_args, filter_fragment) where filter_fragment expects
    the main video on [main] and outputs [wmout].
    """
    wm_path = _resolve_asset(wm.image, project_dir)
    inputs = ["-i", wm_path]

    # Scale watermark relative to main video width
    sw = int(w * wm.scale)
    # Position from normalized coords
    x = int(wm.position[0] * w - sw * wm.position[0])
    y = int(wm.position[1] * h)

    filt = (
        f"[wm_in]scale={sw}:-1,format=rgba,"
        f"colorchannelmixer=aa={wm.opacity}[wm_scaled];"
        f"[main][wm_scaled]overlay={x}:{y}[wmout]"
    )
    return inputs, filt


def _build_video_filters(clip: Clip, input_idx: int, w: int, h: int, fps: int, bg_color: str) -> list[str]:
    """Build FFmpeg video filter expressions for a clip."""
    bg = _hex_to_ffmpeg_color(bg_color)
    filters = [
        f"scale={w}:{h}:force_original_aspect_ratio=decrease",
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={bg}",
        f"fps={fps}",
    ]

    clip_dur = _get_clip_duration(clip)

    if clip.opacity < 1.0:
        filters.append(f"colorchannelmixer=aa={clip.opacity}")

    for f in clip.filters:
        if f.type == FilterType.fade_in:
            dur = f.duration or 1.0
            filters.append(f"fade=t=in:st=0:d={dur}")
        elif f.type == FilterType.fade_out:
            dur = f.duration or 1.0
            if clip_dur is not None:
                st = max(0, clip_dur - dur)
            else:
                # Unknown duration — place fade at 0, better than nothing
                # Callers should set trim_out or duration for correct fade_out
                st = 0
            filters.append(f"fade=t=out:st={st}:d={dur}")
        elif f.type == FilterType.brightness:
            val = f.value if f.value is not None else 0.0
            filters.append(f"eq=brightness={val}")
        elif f.type == FilterType.contrast:
            val = f.value if f.value is not None else 1.0
            filters.append(f"eq=contrast={val}")
        elif f.type == FilterType.saturation:
            val = f.value if f.value is not None else 1.0
            filters.append(f"eq=saturation={val}")
        elif f.type == FilterType.greyscale:
            filters.append("hue=s=0")
        elif f.type == FilterType.blur:
            val = f.value if f.value is not None else 5.0
            filters.append(f"boxblur={val}")
        elif f.type == FilterType.speed:
            val = f.value if f.value is not None else 1.0
            if val != 1.0:
                filters.append(f"setpts={1/val}*PTS")
        elif f.type == FilterType.text and f.text:
            t = f.text
            # Position: convert normalized coords to pixel expressions
            x_expr = f"(w*{t.position[0]}-tw/2)"
            y_expr = f"(h*{t.position[1]}-th/2)"
            color = _hex_to_ffmpeg_color(t.color)
            dt = f"drawtext=text='{_escape_drawtext(t.content)}':fontfile='':font={t.font}"
            dt += f":fontsize={t.size}:fontcolor={color}:x={x_expr}:y={y_expr}"
            if t.bg_color:
                dt += f":box=1:boxcolor={_hex_to_ffmpeg_color(t.bg_color)}@0.7:boxborderw=8"
            if t.start is not None:
                dt += f":enable='between(t,{t.start},{t.start + (t.duration or 9999)})'"
            elif t.duration is not None:
                dt += f":enable='between(t,0,{t.duration})'"
            filters.append(dt)
        elif f.type == FilterType.lut and f.path:
            filters.append(f"lut3d={f.path}")
        elif f.type == FilterType.subtitles and f.path:
            # Escape path colons and backslashes for subtitles filter
            esc_path = f.path.replace("\\", "\\\\").replace(":", "\\:")
            filters.append(f"subtitles='{esc_path}'")
        elif f.type == FilterType.watermark and f.watermark:
            # Watermark overlay is applied at the command level, not as an inline filter.
            # See _get_watermark_config() and its callers.
            pass
        elif f.type == FilterType.crop_zoom and f.crop_zoom:
            cz = f.crop_zoom
            sx, sy, sw, sh = cz.start_rect
            ex, ey, ew, eh = cz.end_rect
            # Animated crop using expressions with time variable
            # t goes 0→1 over clip duration
            if clip_dur and clip_dur > 0:
                filters.append(
                    f"crop="
                    f"w='lerp({sw}*iw,{ew}*iw,t/{clip_dur})':"
                    f"h='lerp({sh}*ih,{eh}*ih,t/{clip_dur})':"
                    f"x='lerp({sx}*iw,{ex}*iw,t/{clip_dur})':"
                    f"y='lerp({sy}*ih,{ey}*ih,t/{clip_dur})',"
                    f"scale={w}:{h}"
                )

    # Reverse video (after all other filters)
    if clip.reverse:
        filters.append("reverse")

    # Freeze frame — extract one frame and loop it
    if clip.freeze_frame is not None:
        # Freeze is handled at the input level, not as a filter
        pass

    return filters


def _build_audio_filters(clip: Clip) -> list[str]:
    """Build FFmpeg audio filter expressions for a clip."""
    clip_dur = _get_clip_duration(clip)
    filters = []
    for f in clip.filters:
        if f.type == FilterType.volume:
            val = f.value if f.value is not None else 1.0
            filters.append(f"volume={val}")
        elif f.type == FilterType.audio_fade_in:
            dur = f.duration or 1.0
            filters.append(f"afade=t=in:st=0:d={dur}")
        elif f.type == FilterType.audio_fade_out:
            dur = f.duration or 1.0
            if clip_dur is not None:
                st = max(0, clip_dur - dur)
            else:
                st = 0
            filters.append(f"afade=t=out:st={st}:d={dur}")
        elif f.type == FilterType.speed:
            val = f.value if f.value is not None else 1.0
            if val != 1.0:
                filters.append(f"atempo={val}")
    return filters


def _escape_drawtext(text: str) -> str:
    """Escape special chars for FFmpeg drawtext filter."""
    return text.replace("\\", "\\\\").replace("'", "'\\''").replace(":", "\\:").replace("%", "%%")


def _quality_args(project: Project) -> list[str]:
    """Return codec + quality flags."""
    enc = _ENCODER[project.output.codec]
    args = ["-c:v", enc]
    if project.output.codec in (OutputCodec.h264, OutputCodec.h265):
        args += ["-crf", _CRF[project.output.quality]]
        if project.output.codec == OutputCodec.h264:
            args += ["-preset", "medium"]
    elif project.output.codec == OutputCodec.prores:
        profile = {"low": "0", "medium": "2", "high": "3", "lossless": "4"}
        args += ["-profile:v", profile[project.output.quality.value]]
    return args


def can_handle(project: Project) -> bool:
    """Return True if this project can use the FFmpeg backend.

    FFmpeg backend handles:
    - Single video track
    - Dissolve transitions between clips (via xfade filter)
    - Optional audio tracks
    """
    if len(project.timeline.tracks) > 1:
        return False
    track = project.timeline.tracks[0]
    if any(c.position for c in track.clips):
        return False
    # FFmpeg handles all xfade transition types
    return True


def compile_commands(project: Project, project_dir: Path) -> list[list[str]]:
    """Compile a single-track project into FFmpeg commands."""
    track = project.timeline.tracks[0]
    clips = sorted(track.clips, key=lambda c: c.start)
    w, h = project.settings.resolution
    fps = project.settings.fps
    bg = project.settings.background
    out_path = _resolve_asset(project.output.path, project_dir)

    if len(clips) == 1:
        return [_single_clip_cmd(clips[0], project, project_dir, out_path, w, h, fps, bg)]

    # Use xfade if any clips have transitions
    has_transitions = any(c.transition_in for c in clips)
    if has_transitions:
        return [_xfade_cmd(clips, project, project_dir, out_path, w, h, fps, bg)]

    return [_concat_cmd(clips, project, project_dir, out_path, w, h, fps, bg)]


def _single_clip_cmd(
    clip: Clip, project: Project, project_dir: Path,
    out_path: str, w: int, h: int, fps: int, bg: str,
) -> list[str]:
    asset = _resolve_asset(clip.asset, project_dir)
    cmd = ["ffmpeg", "-y"]

    # Freeze frame: extract single frame, loop it
    if clip.freeze_frame is not None:
        cmd += ["-ss", str(clip.freeze_frame)]
        cmd += ["-i", asset]
        dur = clip.duration or 5.0
        cmd += ["-t", str(dur)]
        vf = [f"loop=loop=-1:size=1:start=0", f"fps={fps}",
              f"scale={w}:{h}:force_original_aspect_ratio=decrease",
              f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"]
        cmd += ["-vf", ",".join(vf)]
        cmd += _quality_args(project)
        cmd += ["-c:a", project.output.audio_codec, "-b:a", project.output.audio_bitrate]
        cmd += [out_path]
        return cmd

    if clip.trim_in > 0:
        cmd += ["-ss", str(clip.trim_in)]
    cmd += ["-i", asset]
    if clip.trim_out is not None:
        duration = clip.trim_out - clip.trim_in
        cmd += ["-t", str(duration)]
    elif clip.duration is not None:
        cmd += ["-t", str(clip.duration)]

    vf = _build_video_filters(clip, 0, w, h, fps, bg)

    # Check for watermark overlay
    wm = _get_watermark_config(clip)
    if wm:
        # Watermark needs filter_complex with overlay (two inputs)
        wm_path = _resolve_asset(wm.image, project_dir)
        cmd += ["-i", wm_path]
        sw = int(w * wm.scale)
        x = int(wm.position[0] * w - sw * wm.position[0])
        y = int(wm.position[1] * h)
        fc = (
            f"[0:v]{','.join(vf)}[main];"
            f"[1:v]scale={sw}:-1,format=rgba,"
            f"colorchannelmixer=aa={wm.opacity}[wm];"
            f"[main][wm]overlay={x}:{y}[outv]"
        )
        cmd += ["-filter_complex", fc, "-map", "[outv]", "-map", "0:a?"]
    else:
        cmd += ["-vf", ",".join(vf)]

    af = _build_audio_filters(clip)
    if af:
        cmd += ["-af", ",".join(af)]

    # Reverse audio too if video is reversed
    if clip.reverse:
        cmd += ["-af", "areverse"]

    cmd += _quality_args(project)
    cmd += ["-c:a", project.output.audio_codec, "-b:a", project.output.audio_bitrate]
    cmd += [out_path]
    return cmd


def _xfade_cmd(
    clips: list[Clip], project: Project, project_dir: Path,
    out_path: str, w: int, h: int, fps: int, bg: str,
) -> list[str]:
    """Build FFmpeg command with xfade transitions between clips."""
    cmd = ["ffmpeg", "-y"]

    # Add all inputs. Both -ss and -t must come BEFORE -i so FFmpeg associates
    # them with this input — otherwise -t leaks onto the next clip's input opts
    # (or onto the output for the final clip), truncating the render.
    for clip in clips:
        asset = _resolve_asset(clip.asset, project_dir)
        if clip.trim_in > 0:
            cmd += ["-ss", str(clip.trim_in)]
        if clip.trim_out is not None:
            cmd += ["-t", str(clip.trim_out - clip.trim_in)]
        elif clip.duration is not None:
            cmd += ["-t", str(clip.duration)]
        cmd += ["-i", asset]

    n = len(clips)
    parts = []

    # Prepare each clip's video
    for i, clip in enumerate(clips):
        vf = _build_video_filters(clip, i, w, h, fps, bg)
        parts.append(f"[{i}:v]{','.join(vf)}[v{i}]")

    # Chain xfade transitions
    # xfade works pairwise: [v0][v1]xfade → [xf0], [xf0][v2]xfade → [xf1], etc.
    # Map enum values to FFmpeg xfade names (most are just underscores removed)
    _special_xfade = {
        "dissolve": "fade",
        "fade_black": "fadeblack",
        "fade_white": "fadewhite",
        "fade_grays": "fadegrays",
        "circle_open": "circleopen", "circle_close": "circleclose",
        "circle_crop": "circlecrop", "rect_crop": "rectcrop",
        "horz_open": "horzopen", "horz_close": "horzclose",
        "vert_open": "vertopen", "vert_close": "vertclose",
        "diag_tl": "diagtl", "diag_tr": "diagtr",
        "diag_bl": "diagbl", "diag_br": "diagbr",
        "hl_slice": "hlslice", "hr_slice": "hrslice",
        "vu_slice": "vuslice", "vd_slice": "vdslice",
        "zoom_in": "zoomin",
        "squeeze_h": "squeezeh", "squeeze_v": "squeezev",
        "hl_wind": "hlwind", "hr_wind": "hrwind",
        "vu_wind": "vuwind", "vd_wind": "vdwind",
        "wipe_left": "wipeleft", "wipe_right": "wiperight",
        "wipe_up": "wipeup", "wipe_down": "wipedown",
        "slide_left": "slideleft", "slide_right": "slideright",
        "slide_up": "slideup", "slide_down": "slidedown",
        "smooth_left": "smoothleft", "smooth_right": "smoothright",
        "smooth_up": "smoothup", "smooth_down": "smoothdown",
        "cover_left": "coverleft", "cover_right": "coverright",
        "cover_up": "coverup", "cover_down": "coverdown",
        "reveal_left": "revealleft", "reveal_right": "revealright",
        "reveal_up": "revealup", "reveal_down": "revealdown",
    }
    xfade_map = {
        getattr(TransitionType, k): v
        for k, v in _special_xfade.items()
        if hasattr(TransitionType, k)
    }

    # Track cumulative offset for xfade timing
    cursor = 0.0
    prev_label = "v0"
    for i in range(1, n):
        clip = clips[i]
        clip_prev = clips[i - 1]
        prev_dur = _get_clip_duration(clip_prev) or 5.0

        if clip.transition_in:
            trans_dur = clip.transition_in.duration
            trans_type = xfade_map.get(clip.transition_in.type, "fade")
            offset = cursor + prev_dur - trans_dur
            out_label = f"xf{i}" if i < n - 1 else "outv"
            parts.append(f"[{prev_label}][v{i}]xfade=transition={trans_type}:duration={trans_dur}:offset={offset}[{out_label}]")
            cursor = offset
        else:
            # No transition — just concat
            out_label = f"xf{i}" if i < n - 1 else "outv"
            offset = cursor + prev_dur
            parts.append(f"[{prev_label}][v{i}]xfade=transition=fade:duration=0.001:offset={offset}[{out_label}]")
            cursor = offset

        prev_label = out_label

    # If only one clip had no transitions at all, just use it directly
    if n == 1:
        parts.append(f"[v0]null[outv]")

    # Audio: crossfade to match video transitions
    audio_flags = [_has_audio(_resolve_asset(c.asset, project_dir)) for c in clips]
    for i, clip in enumerate(clips):
        if audio_flags[i]:
            af = _build_audio_filters(clip)
            if af:
                parts.append(f"[{i}:a]{','.join(af)}[a{i}]")
            else:
                parts.append(f"[{i}:a]acopy[a{i}]")
        else:
            clip_dur = _get_clip_duration(clip) or 10.0
            parts.append(f"aevalsrc=0:d={clip_dur}:s=48000:c=stereo[a{i}]")

    # Chain audio crossfades matching video transitions
    if n == 1:
        parts.append(f"[a0]acopy[outa]")
    else:
        a_prev = "a0"
        a_cursor = 0.0
        for i in range(1, n):
            clip = clips[i]
            clip_prev = clips[i - 1]
            prev_dur = _get_clip_duration(clip_prev) or 5.0
            out_label = f"af{i}" if i < n - 1 else "outa"

            if clip.transition_in:
                trans_dur = clip.transition_in.duration
                parts.append(f"[{a_prev}][a{i}]acrossfade=d={trans_dur}:c1=tri:c2=tri[{out_label}]")
            else:
                # No transition — just concat the two audio streams
                parts.append(f"[{a_prev}][a{i}]concat=n=2:v=0:a=1[{out_label}]")

            a_prev = out_label

    cmd += ["-filter_complex", ";".join(parts)]
    cmd += ["-map", "[outv]", "-map", "[outa]"]
    cmd += _quality_args(project)
    cmd += ["-c:a", project.output.audio_codec, "-b:a", project.output.audio_bitrate]
    cmd += [out_path]
    return cmd


def _has_audio(asset_path: str) -> bool:
    """Check if a media file has an audio stream."""
    try:
        import av
        container = av.open(asset_path)
        has = len(container.streams.audio) > 0
        container.close()
        return has
    except Exception:
        return True  # Assume audio exists; FFmpeg will handle the error


def _concat_cmd(
    clips: list[Clip], project: Project, project_dir: Path,
    out_path: str, w: int, h: int, fps: int, bg: str,
) -> list[str]:
    cmd = ["ffmpeg", "-y"]

    # Track which inputs have audio
    audio_flags = []
    for clip in clips:
        asset = _resolve_asset(clip.asset, project_dir)
        if clip.trim_in > 0:
            cmd += ["-ss", str(clip.trim_in)]
        cmd += ["-i", asset]
        if clip.trim_out is not None:
            cmd += ["-t", str(clip.trim_out - clip.trim_in)]
        elif clip.duration is not None:
            cmd += ["-t", str(clip.duration)]
        audio_flags.append(_has_audio(asset))

    n = len(clips)
    parts = []
    v_streams = []
    a_streams = []

    for i, clip in enumerate(clips):
        vlabel = f"v{i}"
        alabel = f"a{i}"
        vf = _build_video_filters(clip, i, w, h, fps, bg)
        parts.append(f"[{i}:v]{','.join(vf)}[{vlabel}]")
        v_streams.append(f"[{vlabel}]")

        if audio_flags[i]:
            af = _build_audio_filters(clip)
            if af:
                parts.append(f"[{i}:a]{','.join(af)}[{alabel}]")
            else:
                parts.append(f"[{i}:a]acopy[{alabel}]")
        else:
            # Generate silence for inputs without audio
            clip_dur = _get_clip_duration(clip) or 10.0
            parts.append(f"aevalsrc=0:d={clip_dur}:s=48000:c=stereo[{alabel}]")
        a_streams.append(f"[{alabel}]")

    parts.append(f"{''.join(v_streams)}concat=n={n}:v=1:a=0[outv]")
    parts.append(f"{''.join(a_streams)}concat=n={n}:v=0:a=1[outa]")

    cmd += ["-filter_complex", ";".join(parts)]
    cmd += ["-map", "[outv]", "-map", "[outa]"]
    cmd += _quality_args(project)
    cmd += ["-c:a", project.output.audio_codec, "-b:a", project.output.audio_bitrate]
    cmd += [out_path]
    return cmd


def _parse_ffmpeg_progress(line: str, total_duration: float | None) -> float | None:
    """Parse FFmpeg stderr for progress. Returns 0.0-1.0 or None."""
    match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
    if match and total_duration and total_duration > 0:
        h, m, s = int(match.group(1)), int(match.group(2)), float(match.group(3))
        current = h * 3600 + m * 60 + s
        return min(current / total_duration, 1.0)
    return None


def render(project: Project, project_dir: Path, out: OutputManager,
           total_duration: float | None = None) -> bool:
    """Render the project using FFmpeg. Returns True on success."""
    if not shutil.which("ffmpeg"):
        out.error("render", "ffmpeg not found in PATH")
        return False

    commands = compile_commands(project, project_dir)
    out.emit("compile", f"  Compiled {len(commands)} FFmpeg command(s)",
             backend="ffmpeg", commands=len(commands))

    for i, cmd in enumerate(commands):
        out.emit("render", f"  Executing FFmpeg ({i+1}/{len(commands)})...",
                 step=i + 1, total=len(commands))

        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )

        # Stream stderr for progress
        stderr_lines = []
        for raw_line in proc.stderr:
            line = raw_line.decode(errors="replace")
            stderr_lines.append(line)
            pct = _parse_ffmpeg_progress(line, total_duration)
            if pct is not None:
                out.progress(pct)

        proc.wait()
        if proc.returncode != 0:
            err_msg = "".join(stderr_lines[-10:])
            out.error("render", f"FFmpeg failed (exit {proc.returncode}): {err_msg}")
            return False

    out.progress(1.0)
    out_path = _resolve_asset(project.output.path, project_dir)
    size = Path(out_path).stat().st_size if Path(out_path).exists() else 0
    out.emit("complete",
             f"  Output: {out_path} ({size / 1024 / 1024:.1f} MB)",
             output=out_path, size_bytes=size)
    return True
