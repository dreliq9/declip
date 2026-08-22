"""Compile normalized Declip projects into MLT XML."""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement, indent

from declip.compilers.render_plan import RenderPlan, build_render_plan, resolve_asset
from declip.filters.mlt import add_audio_track_filters, add_clip_filters, add_property, seconds_to_frames
from declip.schema import AudioTrack, Clip, OutputCodec, Project, Quality, TransitionType

_TRANSITION_SERVICE = {
    TransitionType.dissolve: "luma", TransitionType.wipe_left: "luma", TransitionType.wipe_right: "luma",
    TransitionType.wipe_up: "luma", TransitionType.wipe_down: "luma", TransitionType.fade_black: "luma", TransitionType.fade_white: "luma",
}
_WIPE_GEOMETRY = {
    TransitionType.wipe_left: "0=0%/0%:100%x100%:100; -1=-100%/0%:100%x100%:100",
    TransitionType.wipe_right: "0=0%/0%:100%x100%:100; -1=100%/0%:100%x100%:100",
    TransitionType.wipe_up: "0=0%/0%:100%x100%:100; -1=0%/-100%:100%x100%:100",
    TransitionType.wipe_down: "0=0%/0%:100%x100%:100; -1=0%/100%:100%x100%:100",
}
_BITRATE = {Quality.low: "2M", Quality.medium: "5M", Quality.high: "10M", Quality.lossless: "50M"}
_ENCODER = {OutputCodec.h264: "libx264", OutputCodec.h265: "libx265", OutputCodec.prores: "prores_ks", OutputCodec.vp9: "libvpx-vp9"}

@dataclass
class MLTCompilation:
    plan: RenderPlan
    tree: ElementTree
    xml: str

def resolve_output_path(project: Project, project_dir: Path) -> str:
    return resolve_asset(project.output.path, project_dir)
def encoder_for(project: Project) -> str:
    return _ENCODER[project.output.codec]
def bitrate_for(project: Project) -> str:
    return _BITRATE[project.output.quality]

def _build_producer(root: Element, clip: Clip, index: int, project_dir: Path, fps: int) -> str:
    producer_id = f"producer{index}"
    producer = SubElement(root, "producer", id=producer_id)
    add_property(producer, "resource", resolve_asset(clip.asset, project_dir))
    if clip.trim_in > 0:
        producer.set("in", str(seconds_to_frames(clip.trim_in, fps)))
    if clip.trim_out is not None:
        producer.set("out", str(seconds_to_frames(clip.trim_out, fps)))
    return producer_id

def _build_audio_producer(root: Element, audio: AudioTrack, index: int, project_dir: Path, fps: int) -> str:
    producer_id = f"audio_producer{index}"
    producer = SubElement(root, "producer", id=producer_id)
    add_property(producer, "resource", resolve_asset(audio.asset, project_dir))
    if audio.trim_in > 0:
        producer.set("in", str(seconds_to_frames(audio.trim_in, fps)))
    if audio.trim_out is not None:
        producer.set("out", str(seconds_to_frames(audio.trim_out, fps)))
    return producer_id

def _compile_normalized(project: Project, project_dir: Path) -> ElementTree:
    fps = project.settings.fps
    width, height = project.settings.resolution
    root = Element("mlt")
    root.set("LC_NUMERIC", "C")
    profile = SubElement(root, "profile")
    add_property(profile, "width", str(width)); add_property(profile, "height", str(height))
    add_property(profile, "frame_rate_num", str(fps)); add_property(profile, "frame_rate_den", "1")
    background = SubElement(root, "producer", id="bg_color")
    add_property(background, "mlt_service", "color"); add_property(background, "resource", project.settings.background); add_property(background, "length", "999999")

    producer_map: dict[str, str] = {}
    producer_index = 0
    for track in project.timeline.tracks:
        for clip_index, clip in enumerate(sorted(track.clips, key=lambda c: float(c.start))):
            producer_map[f"{track.id}:{clip_index}"] = _build_producer(root, clip, producer_index, project_dir, fps)
            producer_index += 1
    audio_producers = [_build_audio_producer(root, audio, index, project_dir, fps) for index, audio in enumerate(project.timeline.audio)]

    background_playlist = SubElement(root, "playlist", id="playlist_bg")
    SubElement(background_playlist, "entry", producer="bg_color")
    playlist_ids = ["playlist_bg"]
    for track in project.timeline.tracks:
        playlist_id = f"playlist_{track.id}"
        playlist = SubElement(root, "playlist", id=playlist_id)
        playlist_ids.append(playlist_id)
        cursor = 0
        clips = sorted(track.clips, key=lambda c: float(c.start))
        for clip_index, clip in enumerate(clips):
            clip_start = seconds_to_frames(float(clip.start), fps)
            if clip_start > cursor:
                SubElement(playlist, "blank", length=str(clip_start - cursor))
            entry = SubElement(playlist, "entry", producer=producer_map[f"{track.id}:{clip_index}"])
            if clip.trim_in > 0:
                entry.set("in", str(seconds_to_frames(clip.trim_in, fps)))
            if clip.trim_out is not None:
                entry.set("out", str(seconds_to_frames(clip.trim_out, fps)))
            add_clip_filters(entry, clip, fps)
            cursor = clip_start + seconds_to_frames(float(clip.duration or 0.0), fps)

    for audio_index, (audio, producer_id) in enumerate(zip(project.timeline.audio, audio_producers)):
        playlist_id = f"playlist_audio{audio_index}"
        playlist = SubElement(root, "playlist", id=playlist_id)
        playlist_ids.append(playlist_id)
        start_frame = seconds_to_frames(audio.start, fps)
        if start_frame > 0:
            SubElement(playlist, "blank", length=str(start_frame))
        entry = SubElement(playlist, "entry", producer=producer_id)
        if audio.trim_in > 0:
            entry.set("in", str(seconds_to_frames(audio.trim_in, fps)))
        if audio.duration is not None:
            entry.set("out", str(seconds_to_frames(audio.trim_in + audio.duration, fps)))
        elif audio.trim_out is not None:
            entry.set("out", str(seconds_to_frames(audio.trim_out, fps)))
        add_audio_track_filters(entry, audio, fps)

    tractor = SubElement(root, "tractor", id="main")
    multitrack = SubElement(tractor, "multitrack")
    for playlist_id in playlist_ids:
        SubElement(multitrack, "track", producer=playlist_id)
    composite_background = SubElement(tractor, "transition")
    add_property(composite_background, "a_track", "0"); add_property(composite_background, "b_track", "1")
    add_property(composite_background, "mlt_service", "frei0r.cairoblend"); add_property(composite_background, "always_active", "1")

    for track_index, track in enumerate(project.timeline.tracks):
        mlt_track_index = track_index + 1
        clips = sorted(track.clips, key=lambda c: float(c.start))
        for clip_index, clip in enumerate(clips):
            if clip.transition_in is None or clip_index == 0:
                continue
            transition = SubElement(tractor, "transition")
            transition_start = seconds_to_frames(float(clip.start), fps)
            transition_duration = seconds_to_frames(clip.transition_in.duration, fps)
            transition.set("in", str(max(0, transition_start - transition_duration))); transition.set("out", str(transition_start))
            add_property(transition, "a_track", str(mlt_track_index)); add_property(transition, "b_track", str(mlt_track_index))
            add_property(transition, "mlt_service", _TRANSITION_SERVICE.get(clip.transition_in.type, "luma"))
            geometry = _WIPE_GEOMETRY.get(clip.transition_in.type)
            if geometry:
                add_property(transition, "geometry", geometry)

    if len(project.timeline.tracks) > 1:
        for track_index in range(1, len(project.timeline.tracks)):
            overlay_index = track_index + 1
            composite = SubElement(tractor, "transition")
            add_property(composite, "a_track", "1"); add_property(composite, "b_track", str(overlay_index))
            add_property(composite, "mlt_service", "frei0r.cairoblend"); add_property(composite, "always_active", "1")
            positioned = [clip for clip in project.timeline.tracks[track_index].clips if clip.position]
            if positioned:
                service = composite.find("property[@name='mlt_service']")
                if service is not None:
                    service.text = "affine"
                x, y = positioned[0].position
                add_property(composite, "geometry", f"0={int(x * 100)}%/{int(y * 100)}%:50%x50%:100")

    for audio_index in range(len(project.timeline.audio)):
        audio_track_index = len(project.timeline.tracks) + 1 + audio_index
        mix = SubElement(tractor, "transition")
        add_property(mix, "a_track", "1"); add_property(mix, "b_track", str(audio_track_index)); add_property(mix, "mlt_service", "mix"); add_property(mix, "always_active", "1")
    indent(root)
    return ElementTree(root)

def _tree_to_string(tree: ElementTree) -> str:
    buffer = io.BytesIO(); tree.write(buffer, encoding="utf-8", xml_declaration=True); return buffer.getvalue().decode("utf-8")
def compile_project(project: Project, project_dir: Path) -> MLTCompilation:
    plan = build_render_plan(project, project_dir)
    tree = _compile_normalized(plan.project, plan.project_dir)
    return MLTCompilation(plan=plan, tree=tree, xml=_tree_to_string(tree))
def compile_xml(project: Project, project_dir: Path) -> ElementTree:
    return compile_project(project, project_dir).tree
def compile_to_string(project: Project, project_dir: Path) -> str:
    return compile_project(project, project_dir).xml
