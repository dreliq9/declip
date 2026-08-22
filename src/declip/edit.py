"""Reusable file-based edit capabilities.

This module owns edit semantics that were historically implemented inside the MCP
adapter. Functions return the same human-readable strings for compatibility, but
have no MCP or Click dependency and can be called directly from Python, workflows,
or future adapters.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from declip.filters.ffmpeg import escape_drawtext


def _run_ffmpeg(command: list[str], timeout: int = 300) -> tuple[bool, str]:
    try:
        proc = subprocess.run(command, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"FFmpeg timed out after {timeout}s"
    if proc.returncode != 0:
        error = proc.stderr.decode(errors="replace")[-500:]
        return False, f"FFmpeg error:\n{error}"
    return True, ""


def _output_path(input_file: str, output: str | None, suffix: str) -> str:
    if output:
        return output
    path = Path(input_file)
    if suffix.startswith("."):
        return str(path.with_suffix(suffix))
    return str(path.with_stem(path.stem + suffix))


def _file_info(path: str) -> str:
    file = Path(path)
    if file.exists():
        return f"{path} ({file.stat().st_size / 1024 / 1024:.1f} MB)"
    return path


def _find_font(font_name: str) -> str:
    mac_ttf = f"/System/Library/Fonts/Supplemental/{font_name}.ttf"
    if os.path.exists(mac_ttf):
        return f"fontfile='{mac_ttf}'"
    mac_ttc = f"/System/Library/Fonts/{font_name}.ttc"
    if os.path.exists(mac_ttc):
        return f"fontfile='{mac_ttc}'"
    return f"font='{font_name}'"


def text_overlay(
    input_file: str,
    text: str,
    position: str = "bottom",
    font_size: int = 48,
    font_color: str = "white",
    bg_color: str = "",
    start: float = 0,
    duration: float = 0,
    font: str = "Arial",
    shadow_color: str = "",
    shadow_x: int = 0,
    shadow_y: int = 0,
    outline_width: int = 0,
    outline_color: str = "black",
    output_path: str | None = None,
) -> str:
    if not Path(input_file).exists():
        return f"Error: {input_file} not found"
    if font_size <= 0 or start < 0 or duration < 0:
        return "Error: font_size must be positive and start/duration non-negative"
    output = _output_path(input_file, output_path, "_text")
    positions = {
        "top": "x=(w-text_w)/2:y=50",
        "center": "x=(w-text_w)/2:y=(h-text_h)/2",
        "bottom": "x=(w-text_w)/2:y=h-text_h-50",
        "top-left": "x=50:y=50",
        "top-right": "x=w-text_w-50:y=50",
        "bottom-left": "x=50:y=h-text_h-50",
        "bottom-right": "x=w-text_w-50:y=h-text_h-50",
    }
    if position in positions:
        placement = positions[position]
    elif ":" in position:
        x, y = position.split(":", 1)
        placement = f"x={x}:y={y}"
    else:
        placement = positions["bottom"]
    draw = f"drawtext=text='{escape_drawtext(text)}':{_find_font(font)}:fontsize={font_size}:fontcolor={font_color}:{placement}"
    if bg_color:
        draw += f":box=1:boxcolor={bg_color}@0.7:boxborderw=10"
    if shadow_color:
        draw += f":shadowcolor={shadow_color}:shadowx={shadow_x or 2}:shadowy={shadow_y or 2}"
    if outline_width > 0:
        draw += f":borderw={outline_width}:bordercolor={outline_color}"
    if duration > 0:
        draw += f":enable='between(t,{start},{start + duration})'"
    elif start > 0:
        draw += f":enable='gte(t,{start})'"
    ok, error = _run_ffmpeg(["ffmpeg", "-y", "-i", input_file, "-vf", draw, "-c:a", "copy", output])
    return error if not ok else f"Text overlay added: {_file_info(output)}"


def image_overlay(
    input_file: str,
    image_path: str,
    position: str = "top-right",
    scale: float = 0.15,
    opacity: float = 0.8,
    start: float = 0,
    duration: float = 0,
    output_path: str | None = None,
) -> str:
    for path in (input_file, image_path):
        if not Path(path).exists():
            return f"Error: {path} not found"
    if not 0 < scale <= 1 or not 0 <= opacity <= 1 or start < 0 or duration < 0:
        return "Error: scale must be 0-1, opacity 0-1, and start/duration non-negative"
    from declip.probe import probe
    try:
        width = probe(input_file).width or 1920
    except Exception:
        width = 1920
    overlay_width = max(2, int(width * scale) // 2 * 2)
    positions = {
        "top-left": "20:20", "top-right": "W-w-20:20",
        "bottom-left": "20:H-h-20", "bottom-right": "W-w-20:H-h-20",
        "center": "(W-w)/2:(H-h)/2",
    }
    placement = positions.get(position, position if ":" in position else positions["top-right"])
    enable = ""
    if duration > 0:
        enable = f":enable='between(t,{start},{start + duration})'"
    elif start > 0:
        enable = f":enable='gte(t,{start})'"
    graph = (
        f"[1:v]scale={overlay_width}:-2,format=rgba,colorchannelmixer=aa={opacity}[ovr];"
        f"[0:v][ovr]overlay={placement}{enable}[vout]"
    )
    output = _output_path(input_file, output_path, "_overlay")
    command = ["ffmpeg", "-y", "-i", input_file, "-i", image_path, "-filter_complex", graph, "-map", "[vout]", "-map", "0:a?", "-c:a", "copy", output]
    ok, error = _run_ffmpeg(command)
    return error if not ok else f"Image overlay added: {_file_info(output)}"


_XFADE_TYPES = {
    "fade", "fadeblack", "fadewhite", "fadegrays", "wipeleft", "wiperight", "wipeup", "wipedown",
    "slideleft", "slideright", "slideup", "slidedown", "smoothleft", "smoothright", "smoothup", "smoothdown",
    "circleopen", "circleclose", "circlecrop", "rectcrop", "horzopen", "horzclose", "vertopen", "vertclose",
    "diagtl", "diagtr", "diagbl", "diagbr", "hlslice", "hrslice", "vuslice", "vdslice", "radial", "zoomin",
    "distance", "pixelize", "squeezeh", "squeezev", "hlwind", "hrwind", "vuwind", "vdwind",
    "coverleft", "coverright", "coverup", "coverdown", "revealleft", "revealright", "revealup", "revealdown",
}


def transition(file_a: str, file_b: str, transition: str = "dissolve", duration: float = 1.0, output_path: str = "transition_output.mp4") -> str:
    for path in (file_a, file_b):
        if not Path(path).exists():
            return f"Error: {path} not found"
    if duration <= 0:
        return "Error: transition duration must be positive"
    from declip.probe import probe
    try:
        info_a = probe(file_a)
        info_b = probe(file_b)
        if duration >= info_a.duration or duration >= info_b.duration:
            return "Error: transition must be shorter than both clips"
        offset = info_a.duration - duration
    except Exception as exc:
        return f"Error probing transition inputs: {exc}"
    name = {"dissolve": "fade"}.get(transition, transition)
    if name not in _XFADE_TYPES:
        return f"Error: unknown transition '{transition}'. Use one of: {', '.join(sorted(_XFADE_TYPES | {'dissolve'}))}"
    graph = f"[0:v][1:v]xfade=transition={name}:duration={duration}:offset={offset}[v];[0:a][1:a]acrossfade=d={duration}[a]"
    command = ["ffmpeg", "-y", "-i", file_a, "-i", file_b, "-filter_complex", graph, "-map", "[v]", "-map", "[a]", output_path]
    ok, error = _run_ffmpeg(command)
    if not ok:
        graph = f"[0:v][1:v]xfade=transition={name}:duration={duration}:offset={offset}[v]"
        command = ["ffmpeg", "-y", "-i", file_a, "-i", file_b, "-filter_complex", graph, "-map", "[v]", "-an", output_path]
        ok, error = _run_ffmpeg(command)
    return error if not ok else f"Transition ({transition}, {duration}s): {_file_info(output_path)}"


def speed(input_file: str, speed: float = 2.0, interpolate: bool = False, output_path: str | None = None) -> str:
    from declip.ops import speed as operation
    _, message = operation(input_file, speed, interpolate, output_path)
    return message


def color(
    input_file: str,
    brightness: float = 0.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    greyscale: bool = False,
    temperature: float = 0,
    shadows_r: float = 0, shadows_g: float = 0, shadows_b: float = 0,
    midtones_r: float = 0, midtones_g: float = 0, midtones_b: float = 0,
    highlights_r: float = 0, highlights_g: float = 0, highlights_b: float = 0,
    auto_levels: bool = False,
    output_path: str | None = None,
) -> str:
    if not Path(input_file).exists():
        return f"Error: {input_file} not found"
    filters: list[str] = []
    has_basic = greyscale or brightness != 0 or contrast != 1.0 or saturation != 1.0
    if greyscale:
        filters.append("hue=s=0")
    elif has_basic:
        filters.append(f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}")
    has_balance = any((shadows_r, shadows_g, shadows_b, midtones_r, midtones_g, midtones_b, highlights_r, highlights_g, highlights_b))
    if has_balance:
        filters.append(
            f"colorbalance=rs={shadows_r}:gs={shadows_g}:bs={shadows_b}:"
            f"rm={midtones_r}:gm={midtones_g}:bm={midtones_b}:"
            f"rh={highlights_r}:gh={highlights_g}:bh={highlights_b}"
        )
    if temperature != 0:
        kelvin = max(1000, min(40000, int(6500 - temperature * 4500)))
        filters.append(f"colortemperature=temperature={kelvin}")
    if auto_levels:
        filters.append("normalize")
    if not filters:
        return "Error: provide at least one color parameter"
    output = _output_path(input_file, output_path, "_color")
    ok, error = _run_ffmpeg(["ffmpeg", "-y", "-i", input_file, "-vf", ",".join(filters), "-c:a", "copy", output], timeout=600)
    return error if not ok else f"Color adjusted: {_file_info(output)}"


def crop_resize(input_file: str, width: int = 0, height: int = 0, crop: str = "", aspect: str = "", pad_color: str = "black", output_path: str | None = None) -> str:
    if not Path(input_file).exists():
        return f"Error: {input_file} not found"
    filters: list[str] = []
    if crop:
        filters.append(f"crop={crop}")
    if aspect:
        try:
            aspect_width, aspect_height = (int(value) for value in aspect.split(":", 1))
            if aspect_width <= 0 or aspect_height <= 0:
                raise ValueError
        except ValueError:
            return f"Error: invalid aspect ratio '{aspect}'. Use format like '16:9'"
        if width > 0:
            target_width, target_height = width, int(width * aspect_height / aspect_width)
        elif height > 0:
            target_height, target_width = height, int(height * aspect_width / aspect_height)
        else:
            target_width = 1920
            target_height = int(target_width * aspect_height / aspect_width)
        target_width += target_width % 2
        target_height += target_height % 2
        filters += [
            f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease",
            f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color={pad_color}",
        ]
    elif width > 0 or height > 0:
        filters.append(f"scale={width if width > 0 else -2}:{height if height > 0 else -2}")
    if not filters:
        return "Error: provide width/height, crop, or aspect ratio"
    output = _output_path(input_file, output_path, "_resized")
    ok, error = _run_ffmpeg(["ffmpeg", "-y", "-i", input_file, "-vf", ",".join(filters), "-c:a", "copy", output], timeout=600)
    return error if not ok else f"Resized: {_file_info(output)}"


def subtitle_burn(
    input_file: str,
    subtitle_path: str,
    font_size: int = 24,
    font_color: str = "white",
    outline_width: int = 1,
    shadow_offset: int = 1,
    margin_v: int = 30,
    alignment: int = 2,
    output_path: str | None = None,
) -> str:
    for path in (input_file, subtitle_path):
        if not Path(path).exists():
            return f"Error: {path} not found"
    output = _output_path(input_file, output_path, "_subtitled")
    escaped = subtitle_path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\\''")
    extension = Path(subtitle_path).suffix.lower()
    if extension in {".ass", ".ssa"}:
        video_filter = f"ass='{escaped}'"
    else:
        colors = {"white":"&H00FFFFFF", "yellow":"&H0000FFFF", "red":"&H000000FF", "green":"&H0000FF00", "cyan":"&H00FFFF00"}
        ass_color = colors.get(font_color.lower(), font_color)
        style = f"FontSize={font_size},PrimaryColour={ass_color},OutlineColour=&H00000000,Outline={outline_width},Shadow={shadow_offset},MarginV={margin_v},Alignment={alignment}"
        video_filter = f"subtitles='{escaped}':force_style='{style}'"
    ok, error = _run_ffmpeg(["ffmpeg", "-y", "-i", input_file, "-vf", video_filter, "-c:a", "copy", output], timeout=600)
    return error if not ok else f"Subtitles burned in: {_file_info(output)}"


def reverse(input_file: str, audio: bool = True, chunk_seconds: int = 10, output_path: str | None = None) -> str:
    from declip.ops import reverse as operation
    _, message = operation(input_file, audio, chunk_seconds, output_path)
    return message


def gif(input_file: str, start: float = 0, duration: float = 5, width: int = 480, fps: int = 15, output_path: str | None = None) -> str:
    if not Path(input_file).exists():
        return f"Error: {input_file} not found"
    if start < 0 or duration <= 0 or width <= 0 or fps <= 0:
        return "Error: start must be non-negative; duration, width, and fps must be positive"
    output = _output_path(input_file, output_path, ".gif")
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        palette = handle.name
    filters = f"fps={fps},scale={width}:-1:flags=lanczos"
    try:
        ok, error = _run_ffmpeg(["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", input_file, "-vf", f"{filters},palettegen", palette])
        if not ok:
            return f"Palette generation failed: {error}"
        ok, error = _run_ffmpeg(["ffmpeg", "-y", "-ss", str(start), "-t", str(duration), "-i", input_file, "-i", palette, "-filter_complex", f"{filters}[x];[x][1:v]paletteuse", output])
        return error if not ok else f"GIF created: {_file_info(output)}"
    finally:
        try: os.unlink(palette)
        except OSError: pass


def split_screen(
    files: list[str], layout: str = "horizontal", width: int = 1920, height: int = 1080,
    border: int = 0, border_color: str = "black", audio_from: int = 0,
    pip_scale: float = 0.3, pip_position: str = "bottom-right", output_path: str = "splitscreen.mp4",
) -> str:
    count = len(files)
    if count < 2 or count > 4:
        return "Error: provide 2-4 video files"
    for path in files:
        if not Path(path).exists():
            return f"Error: {path} not found"
    if width <= 0 or height <= 0 or border < 0:
        return "Error: width/height must be positive and border non-negative"
    inputs = [part for path in files for part in ("-i", path)]
    graph_parts: list[str] = []
    if layout == "pip":
        if count != 2:
            return "Error: pip layout needs exactly 2 videos"
        if not 0 < pip_scale <= 1:
            return "Error: pip_scale must be between 0 and 1"
        positions = {
            "top-left": f"{border + 20}:{border + 20}",
            "top-right": f"W-w-{border + 20}:{border + 20}",
            "bottom-left": f"{border + 20}:H-h-{border + 20}",
            "bottom-right": f"W-w-{border + 20}:H-h-{border + 20}",
        }
        position = positions.get(pip_position, positions["bottom-right"])
        pip_width = max(2, int(width * pip_scale) // 2 * 2)
        graph_parts += [
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={border_color}[main]",
            f"[1:v]scale={pip_width}:-2[pip]",
            f"[main][pip]overlay={position}[vout]",
        ]
    else:
        if layout == "horizontal":
            cell_width, cell_height = (width - border * (count - 1)) // count, height
            for index in range(count):
                graph_parts.append(f"[{index}:v]scale={cell_width}:{cell_height}:force_original_aspect_ratio=decrease,pad={cell_width}:{cell_height}:(ow-iw)/2:(oh-ih)/2:color={border_color}[v{index}]")
            labels = "".join(f"[v{index}]" for index in range(count))
            graph_parts.append(f"{labels}hstack=inputs={count}[vout]")
        elif layout == "vertical":
            cell_width, cell_height = width, (height - border * (count - 1)) // count
            for index in range(count):
                graph_parts.append(f"[{index}:v]scale={cell_width}:{cell_height}:force_original_aspect_ratio=decrease,pad={cell_width}:{cell_height}:(ow-iw)/2:(oh-ih)/2:color={border_color}[v{index}]")
            labels = "".join(f"[v{index}]" for index in range(count))
            graph_parts.append(f"{labels}vstack=inputs={count}[vout]")
        elif layout == "grid":
            if count != 4:
                return "Error: grid layout needs exactly 4 videos"
            cell_width, cell_height = (width - border) // 2, (height - border) // 2
            for index in range(4):
                graph_parts.append(f"[{index}:v]scale={cell_width}:{cell_height}:force_original_aspect_ratio=decrease,pad={cell_width}:{cell_height}:(ow-iw)/2:(oh-ih)/2:color={border_color}[v{index}]")
            graph_parts += ["[v0][v1]hstack[top]", "[v2][v3]hstack[bottom]", "[top][bottom]vstack[vout]"]
        else:
            return f"Error: unknown layout '{layout}'. Use: horizontal, vertical, grid, pip"
    maps = ["-map", "[vout]"]
    if audio_from == -1:
        labels = "".join(f"[{index}:a]" for index in range(count))
        graph_parts.append(f"{labels}amix=inputs={count}:normalize=0[aout]")
        maps += ["-map", "[aout]"]
    elif 0 <= audio_from < count:
        maps += ["-map", f"{audio_from}:a?"]
    else:
        maps += ["-an"]
    command = ["ffmpeg", "-y"] + inputs + ["-filter_complex", ";".join(graph_parts)] + maps + [output_path]
    ok, error = _run_ffmpeg(command, timeout=600)
    if not ok:
        return error
    if layout == "pip":
        return f"PIP ({pip_position}, {pip_scale:.0%}): {_file_info(output_path)}"
    return f"Split screen ({layout}, {count} videos): {_file_info(output_path)}"


def freeze_frame(input_file: str, timestamp: float, hold_duration: float = 3.0, fps: int = 0, output_path: str | None = None) -> str:
    if not Path(input_file).exists():
        return f"Error: {input_file} not found"
    if timestamp < 0 or hold_duration <= 0:
        return "Error: timestamp must be non-negative and hold_duration positive"
    if fps <= 0:
        from declip.probe import probe
        try: fps = max(1, round(probe(input_file).fps or 30))
        except Exception: fps = 30
    output = _output_path(input_file, output_path, "_freeze")
    video_filter = f"trim=end_frame=1,loop=loop=-1:size=1:start=0,setpts=N/({fps}*TB),fps={fps}"
    command = ["ffmpeg", "-y", "-ss", str(timestamp), "-i", input_file, "-vf", video_filter, "-t", str(hold_duration), "-an", output]
    ok, error = _run_ffmpeg(command, timeout=600)
    return error if not ok else f"Freeze frame at {timestamp}s, held {hold_duration}s @ {fps}fps: {_file_info(output)}"


def stabilize(input_file: str, shakiness: int = 5, smoothing: int = 10, zoom: float = 0, tripod: bool = False, output_path: str | None = None) -> str:
    from declip.ops import stabilize as operation
    _, message = operation(input_file, shakiness, smoothing, zoom, tripod, output_path)
    return message


def audio_mix(video_file: str, audio_file: str, video_volume: float = 1.0, audio_volume: float = 0.5, audio_start: float = 0, replace: bool = False, output_path: str | None = None) -> str:
    for path in (video_file, audio_file):
        if not Path(path).exists(): return f"Error: {path} not found"
    if video_volume < 0 or audio_volume < 0 or audio_start < 0:
        return "Error: volumes and audio_start must be non-negative"
    output = _output_path(video_file, output_path, "_mixed")
    if replace:
        command = ["ffmpeg", "-y", "-i", video_file, "-i", audio_file, "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-af", f"volume={audio_volume}", "-shortest", output]
    else:
        delay = int(audio_start * 1000)
        graph = f"[0:a]volume={video_volume}[va];[1:a]adelay={delay}|{delay},volume={audio_volume}[aa];[va][aa]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[aout]"
        command = ["ffmpeg", "-y", "-i", video_file, "-i", audio_file, "-filter_complex", graph, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", output]
    ok, error = _run_ffmpeg(command, timeout=600)
    return error if not ok else f"Audio mixed: {_file_info(output)}"


def loop(input_file: str, count: int = 3, output_path: str | None = None) -> str:
    if not Path(input_file).exists(): return f"Error: {input_file} not found"
    if count < 1: return "Error: count must be >= 1"
    output = _output_path(input_file, output_path, f"_loop{count}")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as handle:
        listfile = handle.name
        for _ in range(count): handle.write(f"file '{Path(input_file).resolve()}'\n")
    try:
        ok, error = _run_ffmpeg(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listfile, "-c", "copy", output], timeout=600)
    finally:
        try: os.unlink(listfile)
        except OSError: pass
    return error if not ok else f"Looped {count}x: {_file_info(output)}"


def fade(input_file: str, fade_in: float = 0, fade_out: float = 0, color: str = "black", output_path: str | None = None) -> str:
    if not Path(input_file).exists(): return f"Error: {input_file} not found"
    if fade_in <= 0 and fade_out <= 0: return "Error: provide fade_in and/or fade_out duration"
    from declip.probe import probe
    try:
        info = probe(input_file); duration = info.duration
    except Exception as exc:
        return f"Error probing: {exc}"
    video_filters, audio_filters = [], []
    if fade_in > 0:
        video_filters.append(f"fade=t=in:st=0:d={fade_in}:color={color}"); audio_filters.append(f"afade=t=in:st=0:d={fade_in}")
    if fade_out > 0:
        start = max(0, duration - fade_out)
        video_filters.append(f"fade=t=out:st={start}:d={fade_out}:color={color}"); audio_filters.append(f"afade=t=out:st={start}:d={fade_out}")
    output = _output_path(input_file, output_path, "_faded")
    command = ["ffmpeg", "-y", "-i", input_file, "-vf", ",".join(video_filters)]
    if info.audio_codec:
        command += ["-af", ",".join(audio_filters)]
    command.append(output)
    ok, error = _run_ffmpeg(command, timeout=600)
    return error if not ok else f"Fade applied: {_file_info(output)}"


def sidechain(video_file: str, music_file: str, threshold: float = 0.02, ratio: float = 8.0, attack: float = 200, release: float = 1000, output_path: str | None = None) -> str:
    from declip.ops import sidechain as operation
    _, message = operation(video_file, music_file, threshold, ratio, attack, release, output_path)
    return message


def denoise(input_file: str, strength: str = "medium", method: str = "fft", output_path: str | None = None) -> str:
    from declip.ops import denoise as operation
    _, message = operation(input_file, strength, method, output_path)
    return message
