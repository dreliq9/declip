"""MLT XML filter lowering for Declip schema filters."""
from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement

from declip.schema import AudioTrack, Clip, FilterType


def add_property(parent: Element, name: str, value: str) -> None:
    prop = SubElement(parent, "property", name=name)
    prop.text = value


def seconds_to_frames(seconds: float, fps: int) -> int:
    return int(seconds * fps)


def clip_length_frames(clip: Clip, fps: int) -> int:
    if clip.duration is None:
        raise ValueError("MLT compiler requires normalized clip durations")
    return seconds_to_frames(float(clip.duration), fps)


def add_clip_filters(parent: Element, clip: Clip, fps: int) -> None:
    clip_frames = clip_length_frames(clip, fps)

    if clip.opacity < 1.0:
        filt = SubElement(parent, "filter")
        add_property(filt, "mlt_service", "brightness")
        add_property(filt, "alpha", str(clip.opacity))

    for spec in clip.filters:
        filt = SubElement(parent, "filter")
        if spec.type == FilterType.fade_in:
            duration = seconds_to_frames(spec.duration or 1.0, fps)
            add_property(filt, "mlt_service", "brightness")
            add_property(filt, "start", "0")
            add_property(filt, "end", "1")
            filt.set("in", "0")
            filt.set("out", str(duration))
        elif spec.type == FilterType.fade_out:
            duration = seconds_to_frames(spec.duration or 1.0, fps)
            add_property(filt, "mlt_service", "brightness")
            add_property(filt, "start", "1")
            add_property(filt, "end", "0")
            filt.set("in", str(max(0, clip_frames - duration)))
            filt.set("out", str(clip_frames))
        elif spec.type == FilterType.greyscale:
            add_property(filt, "mlt_service", "greyscale")
        elif spec.type == FilterType.brightness:
            add_property(filt, "mlt_service", "brightness")
            add_property(filt, "level", str(spec.value or 1.0))
        elif spec.type == FilterType.contrast:
            add_property(filt, "mlt_service", "frei0r.contrast0r")
            value = spec.value if spec.value is not None else 1.0
            add_property(filt, "0", str(value / 2.0))
        elif spec.type == FilterType.saturation:
            add_property(filt, "mlt_service", "frei0r.saturat0r")
            value = spec.value if spec.value is not None else 1.0
            add_property(filt, "0", str(value / 2.0))
        elif spec.type == FilterType.blur:
            add_property(filt, "mlt_service", "boxblur")
            value = int(spec.value or 5)
            add_property(filt, "hori", str(value))
            add_property(filt, "vert", str(value))
        elif spec.type == FilterType.speed:
            value = spec.value if spec.value is not None else 1.0
            if value != 1.0:
                add_property(filt, "mlt_service", "timewarp")
                add_property(filt, "speed", str(value))
            else:
                parent.remove(filt)
        elif spec.type == FilterType.volume:
            add_property(filt, "mlt_service", "volume")
            add_property(filt, "gain", str(spec.value or 1.0))
        elif spec.type == FilterType.audio_fade_in:
            duration = seconds_to_frames(spec.duration or 1.0, fps)
            add_property(filt, "mlt_service", "volume")
            add_property(filt, "gain", f"0=0; {duration}=1")
        elif spec.type == FilterType.audio_fade_out:
            duration = seconds_to_frames(spec.duration or 1.0, fps)
            start = max(0, clip_frames - duration)
            add_property(filt, "mlt_service", "volume")
            add_property(filt, "gain", f"{start}=1; {clip_frames}=0")
        elif spec.type == FilterType.text and spec.text:
            text = spec.text
            add_property(filt, "mlt_service", "dynamictext")
            add_property(filt, "argument", text.content)
            add_property(filt, "font", text.font)
            add_property(filt, "size", str(text.size))
            add_property(filt, "fgcolour", f"#{text.color.lstrip('#')}ff")
            if text.bg_color:
                add_property(filt, "bgcolour", f"#{text.bg_color.lstrip('#')}b3")
            add_property(filt, "halign", "centre")
            add_property(filt, "valign", "bottom" if text.position[1] > 0.7 else "middle")
        elif spec.type == FilterType.lut and spec.path:
            add_property(filt, "mlt_service", "avfilter.lut3d")
            add_property(filt, "av.file", spec.path)
        else:
            parent.remove(filt)


def add_audio_track_filters(parent: Element, audio: AudioTrack, fps: int) -> None:
    if audio.volume != 1.0:
        filt = SubElement(parent, "filter")
        add_property(filt, "mlt_service", "volume")
        add_property(filt, "gain", str(audio.volume))

    for spec in audio.filters:
        filt = SubElement(parent, "filter")
        if spec.type == FilterType.volume:
            add_property(filt, "mlt_service", "volume")
            add_property(filt, "gain", str(spec.value or 1.0))
        elif spec.type == FilterType.audio_fade_in:
            duration = seconds_to_frames(spec.duration or 1.0, fps)
            add_property(filt, "mlt_service", "volume")
            add_property(filt, "gain", f"0=0; {duration}=1")
        elif spec.type == FilterType.audio_fade_out:
            add_property(filt, "mlt_service", "volume")
            add_property(filt, "end", "0")
        else:
            parent.remove(filt)
