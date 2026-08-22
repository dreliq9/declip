"""Compile normalized Declip projects into MLT XML.

The MLT compiler is deliberately conservative: it only advertises semantics it
can currently lower faithfully. Unsupported project features raise a compilation
error instead of silently disappearing from the render.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import Element, ElementTree, SubElement, indent

from declip.compilers.render_plan import RenderPlan, build_render_plan, resolve_asset
from declip.filters.mlt import add_audio_track_filters, add_clip_filters, add_property, seconds_to_frames
from declip.schema import AudioTrack, FilterType, OutputCodec, Project, Quality

_BITRATE = {
    Quality.low: "2M",
    Quality.medium: "5M",
    Quality.high: "10M",
    Quality.lossless: "50M",
}
_ENCODER = {
    OutputCodec.h264: "libx264",
    OutputCodec.h265: "libx265",
    OutputCodec.prores: "prores_ks",
    OutputCodec.vp9: "libvpx-vp9",
}
_SUPPORTED_CLIP_FILTERS = {
    FilterType.fade_in,
    FilterType.fade_out,
    FilterType.brightness,
    FilterType.contrast,
    FilterType.saturation,
    FilterType.greyscale,
    FilterType.blur,
    FilterType.volume,
    FilterType.audio_fade_in,
    FilterType.audio_fade_out,
    FilterType.text,
    FilterType.lut,
}
_SUPPORTED_AUDIO_FILTERS = {
    FilterType.volume,
    FilterType.audio_fade_in,
    FilterType.audio_fade_out,
}


class CompilationError(ValueError):
    """The project asks the MLT compiler to preserve unsupported semantics."""


@dataclass(frozen=True)
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


def unsupported_reasons(project: Project, tolerance: float = 1e-3) -> tuple[str, ...]:
    """Return semantic reasons the current MLT compiler cannot preserve."""
    reasons: list[str] = []

    for track in project.timeline.tracks:
        clips = sorted(track.clips, key=lambda clip: float(clip.start))
        previous_end: float | None = None
        for index, clip in enumerate(clips):
            label = f"track '{track.id}' clip {index}"
            start = float(clip.start)
            duration = float(clip.duration or 0.0)

            if previous_end is not None and start < previous_end - tolerance:
                reasons.append(
                    f"{label} overlaps the preceding clip; same-track overlap requires a real MLT mix lowering"
                )
            previous_end = max(previous_end or 0.0, start + duration)

            if clip.transition_in is not None:
                reasons.append(
                    f"{label} uses transition_in; MLT transitions blend distinct tracks and the old same-track lowering was invalid"
                )
            if clip.position is not None:
                reasons.append(
                    f"{label} uses position; positioned-track sizing semantics are not yet explicit in the MLT IR"
                )
            if clip.reverse:
                reasons.append(f"{label} uses reverse, which is not lowered by the MLT compiler")
            if clip.freeze_frame is not None:
                reasons.append(f"{label} uses freeze_frame, which is not lowered by the MLT compiler")

            for filter_spec in clip.filters:
                if filter_spec.type not in _SUPPORTED_CLIP_FILTERS:
                    reasons.append(
                        f"{label} uses unsupported MLT filter '{filter_spec.type.value}'"
                    )

    for index, audio in enumerate(project.timeline.audio):
        if audio.duck_on_speech:
            reasons.append(
                f"audio track {index} requests duck_on_speech, which is not lowered by the MLT compiler"
            )
        for filter_spec in audio.filters:
            if filter_spec.type not in _SUPPORTED_AUDIO_FILTERS:
                reasons.append(
                    f"audio track {index} uses unsupported MLT filter '{filter_spec.type.value}'"
                )

    return tuple(dict.fromkeys(reasons))


def can_handle(project: Project) -> bool:
    return not unsupported_reasons(project)


def _frame_span(start_seconds: float, duration_seconds: float, fps: int) -> tuple[int, int]:
    start = seconds_to_frames(start_seconds, fps)
    length = max(1, seconds_to_frames(duration_seconds, fps))
    return start, start + length - 1


def _build_producer(root: Element, asset: str, producer_id: str, project_dir: Path) -> str:
    producer = SubElement(root, "producer", id=producer_id)
    add_property(producer, "resource", resolve_asset(asset, project_dir))
    return producer_id


def _compile_normalized(project: Project, project_dir: Path) -> ElementTree:
    reasons = unsupported_reasons(project)
    if reasons:
        raise CompilationError("MLT cannot preserve this project: " + "; ".join(reasons))

    fps = project.settings.fps
    width, height = project.settings.resolution
    root = Element("mlt")
    root.set("LC_NUMERIC", "C")

    # MLT profile fields are XML attributes, not <property> children.
    SubElement(
        root,
        "profile",
        description="Declip",
        width=str(width),
        height=str(height),
        progressive="1",
        sample_aspect_num="1",
        sample_aspect_den="1",
        display_aspect_num=str(width),
        display_aspect_den=str(height),
        frame_rate_num=str(fps),
        frame_rate_den="1",
        colorspace="709",
    )

    background = SubElement(root, "producer", id="bg_color")
    add_property(background, "mlt_service", "color")
    add_property(background, "resource", project.settings.background)
    add_property(background, "length", "999999")

    producer_map: dict[str, str] = {}
    producer_index = 0
    sorted_tracks: dict[str, list] = {}
    for track in project.timeline.tracks:
        clips = sorted(track.clips, key=lambda clip: float(clip.start))
        sorted_tracks[track.id] = clips
        for clip_index, clip in enumerate(clips):
            producer_id = f"producer{producer_index}"
            producer_map[f"{track.id}:{clip_index}"] = _build_producer(
                root,
                clip.asset,
                producer_id,
                project_dir,
            )
            producer_index += 1

    audio_producers: list[str] = []
    for index, audio in enumerate(project.timeline.audio):
        producer_id = f"audio_producer{index}"
        audio_producers.append(
            _build_producer(root, audio.asset, producer_id, project_dir)
        )

    background_playlist = SubElement(root, "playlist", id="playlist_bg")
    SubElement(background_playlist, "entry", producer="bg_color")
    playlist_ids = ["playlist_bg"]

    for track in project.timeline.tracks:
        playlist_id = f"playlist_{track.id}"
        playlist = SubElement(root, "playlist", id=playlist_id)
        playlist_ids.append(playlist_id)
        cursor = 0

        for clip_index, clip in enumerate(sorted_tracks[track.id]):
            clip_start = seconds_to_frames(float(clip.start), fps)
            if clip_start > cursor:
                SubElement(playlist, "blank", length=str(clip_start - cursor))

            entry = SubElement(
                playlist,
                "entry",
                producer=producer_map[f"{track.id}:{clip_index}"],
            )
            source_in, source_out = _frame_span(
                float(clip.trim_in),
                float(clip.duration or 0.0),
                fps,
            )
            entry.set("in", str(source_in))
            entry.set("out", str(source_out))
            add_clip_filters(entry, clip, fps)
            cursor = clip_start + max(1, seconds_to_frames(float(clip.duration or 0.0), fps))

    for audio_index, (audio, producer_id) in enumerate(
        zip(project.timeline.audio, audio_producers, strict=True)
    ):
        playlist_id = f"playlist_audio{audio_index}"
        playlist = SubElement(root, "playlist", id=playlist_id)
        playlist_ids.append(playlist_id)
        start_frame = seconds_to_frames(audio.start, fps)
        if start_frame > 0:
            SubElement(playlist, "blank", length=str(start_frame))

        entry = SubElement(playlist, "entry", producer=producer_id)
        source_in = seconds_to_frames(audio.trim_in, fps)
        entry.set("in", str(source_in))
        if audio.duration is not None:
            _, source_out = _frame_span(audio.trim_in, audio.duration, fps)
            entry.set("out", str(source_out))
        elif audio.trim_out is not None:
            out_frame = max(source_in, seconds_to_frames(audio.trim_out, fps) - 1)
            entry.set("out", str(out_frame))
        add_audio_track_filters(entry, audio, fps)

    tractor = SubElement(root, "tractor", id="main")
    multitrack = SubElement(tractor, "multitrack")
    for playlist_id in playlist_ids:
        SubElement(multitrack, "track", producer=playlist_id)

    video_track_count = len(project.timeline.tracks)
    for video_track_index in range(1, video_track_count + 1):
        composite = SubElement(tractor, "transition")
        add_property(composite, "a_track", "0")
        add_property(composite, "b_track", str(video_track_index))
        add_property(composite, "mlt_service", "frei0r.cairoblend")
        add_property(composite, "always_active", "1")

    # Mix audio from every non-background track into the output. This mirrors
    # the standard MLT/Shotcut pattern of summing each B track against track 0.
    for track_index in range(1, len(playlist_ids)):
        mix = SubElement(tractor, "transition")
        add_property(mix, "a_track", "0")
        add_property(mix, "b_track", str(track_index))
        add_property(mix, "mlt_service", "mix")
        add_property(mix, "always_active", "1")
        add_property(mix, "sum", "1")

    indent(root)
    return ElementTree(root)


def _tree_to_string(tree: ElementTree) -> str:
    buffer = io.BytesIO()
    tree.write(buffer, encoding="utf-8", xml_declaration=True)
    return buffer.getvalue().decode("utf-8")


def compile_project(project: Project, project_dir: Path) -> MLTCompilation:
    plan = build_render_plan(project, project_dir)
    tree = _compile_normalized(plan.project, plan.project_dir)
    return MLTCompilation(plan=plan, tree=tree, xml=_tree_to_string(tree))


def compile_xml(project: Project, project_dir: Path) -> ElementTree:
    return compile_project(project, project_dir).tree


def compile_to_string(project: Project, project_dir: Path) -> str:
    return compile_project(project, project_dir).xml
