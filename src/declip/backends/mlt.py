"""MLT backend — compiles a Project into MLT XML and renders via melt."""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, ElementTree, indent

from declip.output import OutputManager
from declip.schema import (
    AudioTrack, Clip, FilterType, OutputCodec, Project, Quality,
    Track, TransitionType,
)

_TRANSITION_SERVICE = {
    TransitionType.dissolve: "luma",
    TransitionType.wipe_left: "luma",
    TransitionType.wipe_right: "luma",
    TransitionType.wipe_up: "luma",
    TransitionType.wipe_down: "luma",
    TransitionType.fade_black: "luma",
    TransitionType.fade_white: "luma",
}

# Wipe geometry: softness=0 for hard wipe, geometry controls direction
_WIPE_GEOMETRY = {
    TransitionType.wipe_left: "0=0%/0%:100%x100%:100; -1=-100%/0%:100%x100%:100",
    TransitionType.wipe_right: "0=0%/0%:100%x100%:100; -1=100%/0%:100%x100%:100",
    TransitionType.wipe_up: "0=0%/0%:100%x100%:100; -1=0%/-100%:100%x100%:100",
    TransitionType.wipe_down: "0=0%/0%:100%x100%:100; -1=0%/100%:100%x100%:100",
}

_BITRATE = {Quality.low: "2M", Quality.medium: "5M", Quality.high: "10M", Quality.lossless: "50M"}

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


def _seconds_to_frames(seconds: float, fps: int) -> int:
    return int(seconds * fps)


def _add_property(parent: Element, name: str, value: str):
    prop = SubElement(parent, "property", name=name)
    prop.text = value


def _hex_to_rgb(hex_color: str) -> str:
    """Convert #RRGGBB to r,g,b (0-255)."""
    h = hex_color.lstrip("#")
    return f"{int(h[0:2], 16)},{int(h[2:4], 16)},{int(h[4:6], 16)}"


def _build_producer(root: Element, clip: Clip, idx: int, project_dir: Path, fps: int) -> str:
    pid = f"producer{idx}"
    producer = SubElement(root, "producer", id=pid)
    _add_property(producer, "resource", _resolve_asset(clip.asset, project_dir))
    if clip.trim_in > 0:
        producer.set("in", str(_seconds_to_frames(clip.trim_in, fps)))
    if clip.trim_out is not None:
        producer.set("out", str(_seconds_to_frames(clip.trim_out, fps)))
    return pid


def _build_audio_producer(root: Element, audio: AudioTrack, idx: int, project_dir: Path, fps: int) -> str:
    pid = f"audio_producer{idx}"
    producer = SubElement(root, "producer", id=pid)
    _add_property(producer, "resource", _resolve_asset(audio.asset, project_dir))
    if audio.trim_in > 0:
        producer.set("in", str(_seconds_to_frames(audio.trim_in, fps)))
    if audio.trim_out is not None:
        producer.set("out", str(_seconds_to_frames(audio.trim_out, fps)))
    return pid


def _get_clip_length_frames(clip: Clip, fps: int) -> int | None:
    """Get clip length in frames, or None if unknown."""
    if clip.duration is not None:
        return _seconds_to_frames(clip.duration, fps)
    if clip.trim_out is not None:
        return _seconds_to_frames(clip.trim_out - clip.trim_in, fps)
    return None


def _add_clip_filters(parent: Element, clip: Clip, fps: int):
    """Add MLT filters for clip effects."""
    clip_frames = _get_clip_length_frames(clip, fps)

    # Opacity
    if clip.opacity < 1.0:
        filt = SubElement(parent, "filter")
        _add_property(filt, "mlt_service", "brightness")
        _add_property(filt, "alpha", str(clip.opacity))

    for f in clip.filters:
        filt = SubElement(parent, "filter")
        if f.type == FilterType.fade_in:
            dur = _seconds_to_frames(f.duration or 1.0, fps)
            _add_property(filt, "mlt_service", "brightness")
            _add_property(filt, "start", "0")
            _add_property(filt, "end", "1")
            filt.set("in", "0")
            filt.set("out", str(dur))
        elif f.type == FilterType.fade_out:
            dur = _seconds_to_frames(f.duration or 1.0, fps)
            _add_property(filt, "mlt_service", "brightness")
            _add_property(filt, "start", "1")
            _add_property(filt, "end", "0")
            if clip_frames is not None:
                filt.set("in", str(max(0, clip_frames - dur)))
                filt.set("out", str(clip_frames))
        elif f.type == FilterType.greyscale:
            _add_property(filt, "mlt_service", "greyscale")
        elif f.type == FilterType.brightness:
            _add_property(filt, "mlt_service", "brightness")
            _add_property(filt, "level", str(f.value or 1.0))
        elif f.type == FilterType.contrast:
            _add_property(filt, "mlt_service", "frei0r.contrast0r")
            # frei0r contrast: 0.5 = neutral, 0=min, 1=max
            val = f.value if f.value is not None else 1.0
            _add_property(filt, "0", str(val / 2.0))
        elif f.type == FilterType.saturation:
            _add_property(filt, "mlt_service", "frei0r.saturat0r")
            val = f.value if f.value is not None else 1.0
            _add_property(filt, "0", str(val / 2.0))
        elif f.type == FilterType.blur:
            _add_property(filt, "mlt_service", "boxblur")
            _add_property(filt, "hori", str(int(f.value or 5)))
            _add_property(filt, "vert", str(int(f.value or 5)))
        elif f.type == FilterType.speed:
            val = f.value if f.value is not None else 1.0
            if val != 1.0:
                _add_property(filt, "mlt_service", "timewarp")
                _add_property(filt, "speed", str(val))
        elif f.type == FilterType.volume:
            _add_property(filt, "mlt_service", "volume")
            _add_property(filt, "gain", str(f.value or 1.0))
        elif f.type == FilterType.audio_fade_in:
            dur = _seconds_to_frames(f.duration or 1.0, fps)
            _add_property(filt, "mlt_service", "volume")
            _add_property(filt, "gain", f"0=0; {dur}=1")
        elif f.type == FilterType.audio_fade_out:
            dur = _seconds_to_frames(f.duration or 1.0, fps)
            _add_property(filt, "mlt_service", "volume")
            if clip_frames is not None:
                start_frame = max(0, clip_frames - dur)
                _add_property(filt, "gain", f"{start_frame}=1; {clip_frames}=0")
            else:
                _add_property(filt, "gain", "0=1; -1=0")
        elif f.type == FilterType.text and f.text:
            t = f.text
            _add_property(filt, "mlt_service", "dynamictext")
            _add_property(filt, "argument", t.content)
            _add_property(filt, "font", t.font)
            _add_property(filt, "size", str(t.size))
            _add_property(filt, "fgcolour", f"#{t.color.lstrip('#')}ff")
            if t.bg_color:
                _add_property(filt, "bgcolour", f"#{t.bg_color.lstrip('#')}b3")
            _add_property(filt, "halign", "centre")
            _add_property(filt, "valign", "bottom" if t.position[1] > 0.7 else "middle")
        elif f.type == FilterType.lut and f.path:
            _add_property(filt, "mlt_service", "avfilter.lut3d")
            _add_property(filt, "av.file", f.path)
        else:
            # Remove empty filter element if nothing matched
            parent.remove(filt)


def compile_xml(project: Project, project_dir: Path) -> ElementTree:
    """Compile a Project into an MLT XML ElementTree."""
    fps = project.settings.fps
    w, h = project.settings.resolution

    root = Element("mlt")
    root.set("LC_NUMERIC", "C")

    # Profile
    profile = SubElement(root, "profile")
    _add_property(profile, "width", str(w))
    _add_property(profile, "height", str(h))
    _add_property(profile, "frame_rate_num", str(fps))
    _add_property(profile, "frame_rate_den", "1")

    # Background color producer
    bg_producer = SubElement(root, "producer", id="bg_color")
    _add_property(bg_producer, "mlt_service", "color")
    _add_property(bg_producer, "resource", project.settings.background)
    _add_property(bg_producer, "length", "999999")

    # Build all producers
    producer_map: dict[str, str] = {}
    pidx = 0
    for track in project.timeline.tracks:
        for ci, clip in enumerate(sorted(track.clips, key=lambda c: c.start)):
            key = f"{track.id}:{ci}"
            pid = _build_producer(root, clip, pidx, project_dir, fps)
            producer_map[key] = pid
            pidx += 1

    # Audio producers
    audio_pids = []
    for ai, audio in enumerate(project.timeline.audio):
        apid = _build_audio_producer(root, audio, ai, project_dir, fps)
        audio_pids.append(apid)

    # Background playlist
    bg_pl = SubElement(root, "playlist", id="playlist_bg")
    SubElement(bg_pl, "entry", producer="bg_color")

    # Build playlists (one per track)
    playlist_ids = ["playlist_bg"]
    for track in project.timeline.tracks:
        pl_id = f"playlist_{track.id}"
        playlist = SubElement(root, "playlist", id=pl_id)
        playlist_ids.append(pl_id)

        clips = sorted(track.clips, key=lambda c: c.start)
        cursor = 0

        for ci, clip in enumerate(clips):
            clip_start = _seconds_to_frames(clip.start, fps)

            if clip_start > cursor:
                blank = SubElement(playlist, "blank")
                blank.set("length", str(clip_start - cursor))

            key = f"{track.id}:{ci}"
            pid = producer_map[key]
            entry = SubElement(playlist, "entry", producer=pid)

            if clip.trim_in > 0:
                entry.set("in", str(_seconds_to_frames(clip.trim_in, fps)))
            if clip.trim_out is not None:
                entry.set("out", str(_seconds_to_frames(clip.trim_out, fps)))

            _add_clip_filters(entry, clip, fps)

            if clip.duration is not None:
                cursor = clip_start + _seconds_to_frames(clip.duration, fps)
            elif clip.trim_out is not None:
                cursor = clip_start + _seconds_to_frames(clip.trim_out - clip.trim_in, fps)
            else:
                cursor = clip_start

    # Audio playlists
    for ai, (audio, apid) in enumerate(zip(project.timeline.audio, audio_pids)):
        apl_id = f"playlist_audio{ai}"
        apl = SubElement(root, "playlist", id=apl_id)
        playlist_ids.append(apl_id)

        start_frame = _seconds_to_frames(audio.start, fps)
        if start_frame > 0:
            blank = SubElement(apl, "blank")
            blank.set("length", str(start_frame))

        entry = SubElement(apl, "entry", producer=apid)

        if audio.trim_in > 0:
            entry.set("in", str(_seconds_to_frames(audio.trim_in, fps)))
        # duration overrides trim_out if both set
        if audio.duration is not None:
            entry.set("out", str(_seconds_to_frames(audio.trim_in + audio.duration, fps)))
        elif audio.trim_out is not None:
            entry.set("out", str(_seconds_to_frames(audio.trim_out, fps)))

        if audio.volume != 1.0:
            vol_filt = SubElement(entry, "filter")
            _add_property(vol_filt, "mlt_service", "volume")
            _add_property(vol_filt, "gain", str(audio.volume))

        # Audio-specific filters
        for f in audio.filters:
            filt = SubElement(entry, "filter")
            if f.type == FilterType.volume:
                _add_property(filt, "mlt_service", "volume")
                _add_property(filt, "gain", str(f.value or 1.0))
            elif f.type == FilterType.audio_fade_in:
                dur = _seconds_to_frames(f.duration or 1.0, fps)
                _add_property(filt, "mlt_service", "volume")
                _add_property(filt, "gain", f"0=0; {dur}=1")
            elif f.type == FilterType.audio_fade_out:
                _add_property(filt, "mlt_service", "volume")
                _add_property(filt, "end", "0")

    # Tractor
    tractor = SubElement(root, "tractor", id="main")
    multitrack = SubElement(tractor, "multitrack")
    for pl_id in playlist_ids:
        SubElement(multitrack, "track", producer=pl_id)

    # Composite bg onto first video track
    composite_bg = SubElement(tractor, "transition")
    _add_property(composite_bg, "a_track", "0")
    _add_property(composite_bg, "b_track", "1")
    _add_property(composite_bg, "mlt_service", "frei0r.cairoblend")
    _add_property(composite_bg, "always_active", "1")

    # Transitions between clips on same track
    for ti, track in enumerate(project.timeline.tracks):
        track_idx = ti + 1  # offset by bg track
        clips = sorted(track.clips, key=lambda c: c.start)
        for ci, clip in enumerate(clips):
            if clip.transition_in and ci > 0:
                trans = SubElement(tractor, "transition")
                trans_start = _seconds_to_frames(clip.start, fps)
                trans_dur = _seconds_to_frames(clip.transition_in.duration, fps)
                trans.set("in", str(trans_start - trans_dur))
                trans.set("out", str(trans_start))
                _add_property(trans, "a_track", str(track_idx))
                _add_property(trans, "b_track", str(track_idx))
                svc = _TRANSITION_SERVICE.get(clip.transition_in.type, "luma")
                _add_property(trans, "mlt_service", svc)
                # Wipe direction geometry
                geom = _WIPE_GEOMETRY.get(clip.transition_in.type)
                if geom:
                    _add_property(trans, "geometry", geom)

    # Composite overlay tracks onto main track (with position support)
    if len(project.timeline.tracks) > 1:
        for ti in range(1, len(project.timeline.tracks)):
            overlay_idx = ti + 1  # offset by bg track
            composite = SubElement(tractor, "transition")
            _add_property(composite, "a_track", "1")
            _add_property(composite, "b_track", str(overlay_idx))
            _add_property(composite, "mlt_service", "frei0r.cairoblend")
            _add_property(composite, "always_active", "1")

            # Check if any clip on this track has a position
            track = project.timeline.tracks[ti]
            positioned_clips = [c for c in track.clips if c.position]
            if positioned_clips:
                # Use affine for positioning
                composite.find("property[@name='mlt_service']").text = "affine"
                clip = positioned_clips[0]
                x_pct = int(clip.position[0] * 100)
                y_pct = int(clip.position[1] * 100)
                _add_property(composite, "geometry",
                              f"0={x_pct}%/{y_pct}%:50%x50%:100")

    # Mix audio tracks
    for ai in range(len(project.timeline.audio)):
        audio_ti = len(project.timeline.tracks) + 1 + ai  # +1 for bg track
        mix = SubElement(tractor, "transition")
        _add_property(mix, "a_track", "1")
        _add_property(mix, "b_track", str(audio_ti))
        _add_property(mix, "mlt_service", "mix")
        _add_property(mix, "always_active", "1")

    indent(root)
    return ElementTree(root)


def compile_to_string(project: Project, project_dir: Path) -> str:
    import io
    tree = compile_xml(project, project_dir)
    buf = io.BytesIO()
    tree.write(buf, encoding="utf-8", xml_declaration=True)
    return buf.getvalue().decode("utf-8")


def _parse_melt_progress(line: str, total_frames: int | None) -> float | None:
    """Parse melt stderr for progress."""
    match = re.search(r"Current Frame:\s*(\d+)", line)
    if match and total_frames and total_frames > 0:
        return min(int(match.group(1)) / total_frames, 1.0)
    return None


def render(project: Project, project_dir: Path, out: OutputManager,
           total_duration: float | None = None) -> bool:
    """Render via melt CLI."""
    melt_bin = shutil.which("melt")
    if not melt_bin:
        out.error("render", "melt not found in PATH — install with: brew install mlt")
        return False

    xml_str = compile_to_string(project, project_dir)
    out.emit("compile", f"  Compiled MLT XML ({len(xml_str)} bytes)",
             backend="mlt", xml_bytes=len(xml_str))

    with tempfile.NamedTemporaryFile(suffix=".mlt", mode="w", delete=False) as f:
        f.write(xml_str)
        xml_path = f.name

    out_path = _resolve_asset(project.output.path, project_dir)
    encoder = _ENCODER[project.output.codec]
    bitrate = _BITRATE[project.output.quality]
    w, h = project.settings.resolution

    cmd = [
        melt_bin, xml_path,
        "-consumer", f"avformat:{out_path}",
        "real_time=-1",
        f"width={w}", f"height={h}",
        f"vcodec={encoder}", f"vb={bitrate}",
        f"acodec={project.output.audio_codec}",
        f"ab={project.output.audio_bitrate}",
        "terminate_on_pause=1",
    ]

    out.emit("render", "  Rendering via melt...", command=" ".join(cmd))

    total_frames = _seconds_to_frames(total_duration, project.settings.fps) if total_duration else None

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    stderr_lines = []
    for raw_line in proc.stderr:
        line = raw_line.decode(errors="replace")
        stderr_lines.append(line)
        pct = _parse_melt_progress(line, total_frames)
        if pct is not None:
            out.progress(pct)

    proc.wait()
    Path(xml_path).unlink(missing_ok=True)

    if proc.returncode != 0:
        err_msg = "".join(stderr_lines[-10:])
        out.error("render", f"melt failed (exit {proc.returncode}): {err_msg}")
        return False

    out.progress(1.0)
    size = Path(out_path).stat().st_size if Path(out_path).exists() else 0
    out.emit("complete",
             f"  Output: {out_path} ({size / 1024 / 1024:.1f} MB)",
             output=out_path, size_bytes=size)
    return True
