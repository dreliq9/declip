"""FFmpeg filter lowering for Declip clip semantics.

This module contains no subprocess execution and no MCP/CLI concerns. It lowers a
normalized schema ``Clip`` into FFmpeg video/audio filter expressions.
"""
from __future__ import annotations

from declip.schema import Clip, FilterType, WatermarkConfig


def hex_to_ffmpeg_color(hex_color: str) -> str:
    return "0x" + hex_color.lstrip("#")


def escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace("'", "'\\''")
        .replace(":", "\\:")
        .replace(";", "\\;")
        .replace("%", "%%")
    )


def get_watermark_config(clip: Clip) -> WatermarkConfig | None:
    for filt in clip.filters:
        if filt.type == FilterType.watermark and filt.watermark:
            return filt.watermark
    return None


def _atempo_chain(speed: float) -> list[str]:
    if speed <= 0:
        raise ValueError("speed filter value must be positive")
    filters: list[str] = []
    remaining = float(speed)
    while remaining > 100.0:
        filters.append("atempo=100.0")
        remaining /= 100.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining *= 2.0
    filters.append(f"atempo={remaining}")
    return filters


def build_video_filters(
    clip: Clip,
    width: int,
    height: int,
    fps: int,
    background: str,
) -> list[str]:
    """Lower clip video semantics to a filter chain."""

    clip_duration = float(clip.duration or 0.0)
    bg = hex_to_ffmpeg_color(background)

    if clip.freeze_frame is not None:
        if clip_duration <= 0:
            raise ValueError("freeze-frame clips require an explicit duration")
        filters = [
            "trim=start_frame=0:end_frame=1",
            "loop=loop=-1:size=1:start=0",
            f"setpts=N/({fps}*TB)",
            f"trim=duration={clip_duration}",
        ]
    else:
        filters = ["setpts=PTS-STARTPTS"]

    filters.extend(
        [
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={bg}",
            f"fps={fps}",
            "settb=AVTB",
        ]
    )

    if clip.opacity < 1.0:
        filters.append(f"colorchannelmixer=aa={clip.opacity}")

    for filt in clip.filters:
        if filt.type == FilterType.fade_in:
            duration = filt.duration or 1.0
            filters.append(f"fade=t=in:st=0:d={duration}")
        elif filt.type == FilterType.fade_out:
            duration = filt.duration or 1.0
            start = max(0.0, clip_duration - duration)
            filters.append(f"fade=t=out:st={start}:d={duration}")
        elif filt.type == FilterType.brightness:
            value = filt.value if filt.value is not None else 0.0
            filters.append(f"eq=brightness={value}")
        elif filt.type == FilterType.contrast:
            value = filt.value if filt.value is not None else 1.0
            filters.append(f"eq=contrast={value}")
        elif filt.type == FilterType.saturation:
            value = filt.value if filt.value is not None else 1.0
            filters.append(f"eq=saturation={value}")
        elif filt.type == FilterType.greyscale:
            filters.append("hue=s=0")
        elif filt.type == FilterType.blur:
            value = filt.value if filt.value is not None else 5.0
            filters.append(f"boxblur={value}")
        elif filt.type == FilterType.speed:
            value = filt.value if filt.value is not None else 1.0
            if value <= 0:
                raise ValueError("speed filter value must be positive")
            if value != 1.0:
                filters.append(f"setpts={1 / value}*PTS")
        elif filt.type == FilterType.text and filt.text:
            text = filt.text
            x_expr = f"(w*{text.position[0]}-tw/2)"
            y_expr = f"(h*{text.position[1]}-th/2)"
            color = hex_to_ffmpeg_color(text.color)
            draw = (
                f"drawtext=text='{escape_drawtext(text.content)}':font='{text.font}'"
                f":fontsize={text.size}:fontcolor={color}:x={x_expr}:y={y_expr}"
            )
            if text.bg_color:
                draw += (
                    f":box=1:boxcolor={hex_to_ffmpeg_color(text.bg_color)}@0.7"
                    ":boxborderw=8"
                )
            if text.start is not None:
                draw += (
                    f":enable='between(t,{text.start},"
                    f"{text.start + (text.duration or 9999)})'"
                )
            elif text.duration is not None:
                draw += f":enable='between(t,0,{text.duration})'"
            filters.append(draw)
        elif filt.type == FilterType.lut and filt.path:
            filters.append(f"lut3d={filt.path}")
        elif filt.type == FilterType.subtitles and filt.path:
            escaped = filt.path.replace("\\", "\\\\").replace(":", "\\:")
            filters.append(f"subtitles='{escaped}'")
        elif filt.type == FilterType.crop_zoom and filt.crop_zoom:
            crop = filt.crop_zoom
            sx, sy, sw, sh = crop.start_rect
            ex, ey, ew, eh = crop.end_rect
            if clip_duration > 0:
                filters.append(
                    "crop="
                    f"w='lerp({sw}*iw,{ew}*iw,t/{clip_duration})':"
                    f"h='lerp({sh}*ih,{eh}*ih,t/{clip_duration})':"
                    f"x='lerp({sx}*iw,{ex}*iw,t/{clip_duration})':"
                    f"y='lerp({sy}*ih,{ey}*ih,t/{clip_duration})',"
                    f"scale={width}:{height}"
                )

    if clip.reverse:
        filters.append("reverse")

    return filters


def build_audio_filters(clip: Clip) -> list[str]:
    """Lower clip audio semantics to a filter chain."""

    clip_duration = float(clip.duration or 0.0)
    filters = ["asetpts=PTS-STARTPTS"]

    if clip.freeze_frame is not None and clip_duration > 0:
        filters.extend([f"atrim=duration={clip_duration}", "asetpts=PTS-STARTPTS"])

    for filt in clip.filters:
        if filt.type == FilterType.volume:
            value = filt.value if filt.value is not None else 1.0
            filters.append(f"volume={value}")
        elif filt.type == FilterType.audio_fade_in:
            duration = filt.duration or 1.0
            filters.append(f"afade=t=in:st=0:d={duration}")
        elif filt.type == FilterType.audio_fade_out:
            duration = filt.duration or 1.0
            start = max(0.0, clip_duration - duration)
            filters.append(f"afade=t=out:st={start}:d={duration}")
        elif filt.type == FilterType.speed:
            value = filt.value if filt.value is not None else 1.0
            if value != 1.0:
                filters.extend(_atempo_chain(value))

    if clip.reverse:
        filters.append("areverse")

    return filters
