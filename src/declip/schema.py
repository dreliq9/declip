"""Declip project schema — the public JSON contract."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


def _validate_start(value: Any) -> Any:
    """Accept a numeric start time or the literal string ``auto``."""
    if isinstance(value, (int, float)):
        return float(value)
    if value == "auto":
        return "auto"
    try:
        return float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("start must be a number (seconds) or 'auto'") from exc


class TransitionType(str, Enum):
    # Core transitions
    dissolve = "dissolve"
    fade_black = "fade_black"
    fade_white = "fade_white"
    fade_grays = "fade_grays"
    # Wipes
    wipe_left = "wipe_left"
    wipe_right = "wipe_right"
    wipe_up = "wipe_up"
    wipe_down = "wipe_down"
    # Slides
    slide_left = "slide_left"
    slide_right = "slide_right"
    slide_up = "slide_up"
    slide_down = "slide_down"
    # Smooth
    smooth_left = "smooth_left"
    smooth_right = "smooth_right"
    smooth_up = "smooth_up"
    smooth_down = "smooth_down"
    # Circles and shapes
    circle_open = "circle_open"
    circle_close = "circle_close"
    circle_crop = "circle_crop"
    rect_crop = "rect_crop"
    # Bars
    horz_open = "horz_open"
    horz_close = "horz_close"
    vert_open = "vert_open"
    vert_close = "vert_close"
    # Diagonals
    diag_tl = "diag_tl"
    diag_tr = "diag_tr"
    diag_bl = "diag_bl"
    diag_br = "diag_br"
    # Slices
    hl_slice = "hl_slice"
    hr_slice = "hr_slice"
    vu_slice = "vu_slice"
    vd_slice = "vd_slice"
    # Other
    radial = "radial"
    zoom_in = "zoom_in"
    distance = "distance"
    pixelize = "pixelize"
    squeeze_h = "squeeze_h"
    squeeze_v = "squeeze_v"
    # Wind
    hl_wind = "hl_wind"
    hr_wind = "hr_wind"
    vu_wind = "vu_wind"
    vd_wind = "vd_wind"
    # Cover
    cover_left = "cover_left"
    cover_right = "cover_right"
    cover_up = "cover_up"
    cover_down = "cover_down"
    # Reveal
    reveal_left = "reveal_left"
    reveal_right = "reveal_right"
    reveal_up = "reveal_up"
    reveal_down = "reveal_down"


class FilterType(str, Enum):
    fade_in = "fade_in"
    fade_out = "fade_out"
    brightness = "brightness"
    contrast = "contrast"
    saturation = "saturation"
    greyscale = "greyscale"
    blur = "blur"
    speed = "speed"
    volume = "volume"
    audio_fade_in = "audio_fade_in"
    audio_fade_out = "audio_fade_out"
    text = "text"
    lut = "lut"
    subtitles = "subtitles"
    watermark = "watermark"
    crop_zoom = "crop_zoom"


class OutputCodec(str, Enum):
    h264 = "h264"
    h265 = "h265"
    prores = "prores"
    vp9 = "vp9"


class OutputFormat(str, Enum):
    mp4 = "mp4"
    mov = "mov"
    mkv = "mkv"
    webm = "webm"


class Quality(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    lossless = "lossless"


class TextOverlay(BaseModel):
    """Text to draw on a clip."""

    content: str = Field(..., description="Text string (supports {{var}} template substitution)")
    font: str = Field("Arial", description="Font family name")
    size: int = Field(48, gt=0)
    color: str = Field("#FFFFFF", pattern=r"^#[0-9a-fA-F]{6}$")
    bg_color: str | None = Field(None, pattern=r"^#[0-9a-fA-F]{6}$")
    position: tuple[float, float] = Field((0.5, 0.9), description="(x, y) normalized 0.0-1.0")
    start: float | None = Field(None, ge=0, description="Appear at this time into the clip (seconds)")
    duration: float | None = Field(None, gt=0, description="Show for this duration (seconds)")


class WatermarkConfig(BaseModel):
    """Watermark/logo overlay."""

    image: str = Field(..., description="Path to watermark image (PNG with transparency)")
    position: tuple[float, float] = Field((0.95, 0.05), description="(x, y) normalized, default top-right")
    scale: float = Field(0.1, gt=0, le=1.0, description="Size relative to video width")
    opacity: float = Field(0.7, ge=0, le=1.0)


class CropZoom(BaseModel):
    """Ken Burns effect — animated crop/zoom over a clip's duration."""

    start_rect: tuple[float, float, float, float] = Field(
        ..., description="(x, y, w, h) normalized 0.0-1.0 — initial crop region"
    )
    end_rect: tuple[float, float, float, float] = Field(
        ..., description="(x, y, w, h) normalized 0.0-1.0 — final crop region"
    )


class Filter(BaseModel):
    """A filter/effect applied to a clip."""

    type: FilterType
    duration: float | None = Field(None, description="Duration in seconds (for fades)")
    value: float | None = Field(None, description="Parameter value (brightness=1.0 is neutral)")
    text: TextOverlay | None = Field(None, description="Text config (only for type=text)")
    path: str | None = Field(None, description="File path (for LUT or subtitle files)")
    watermark: WatermarkConfig | None = Field(None, description="Watermark config (only for type=watermark)")
    crop_zoom: CropZoom | None = Field(None, description="Ken Burns config (only for type=crop_zoom)")


class Transition(BaseModel):
    """A transition into a clip from the previous clip on the same track."""

    type: TransitionType = TransitionType.dissolve
    duration: float = Field(0.5, gt=0, description="Transition duration in seconds")


class Clip(BaseModel):
    """A single clip on a track."""

    asset: str = Field(..., description="Path to media file (relative to project file)")
    start: Any = Field(..., description="Start time on the timeline in seconds, or 'auto'")
    duration: float | None = Field(None, gt=0, description="Duration on timeline (defaults to trimmed asset length)")
    trim_in: float = Field(0, ge=0, description="Source in-point in seconds")
    trim_out: float | None = Field(None, description="Source out-point in seconds (None = end of file)")
    filters: list[Filter] = Field(default_factory=list)
    transition_in: Transition | None = Field(None, description="Transition from previous clip")
    position: tuple[float, float] | None = Field(None, description="(x, y) position for overlays, 0.0-1.0 normalized")
    opacity: float = Field(1.0, ge=0, le=1)
    reverse: bool = Field(False, description="Play this clip in reverse")
    freeze_frame: float | None = Field(None, ge=0, description="Freeze at this timestamp (seconds into source) for the clip's duration")

    @field_validator("start", mode="before")
    @classmethod
    def validate_start(cls, value: Any) -> Any:
        return _validate_start(value)

    @model_validator(mode="after")
    def trim_order(self):
        if self.trim_out is not None and self.trim_out <= self.trim_in:
            raise ValueError("trim_out must be greater than trim_in")
        return self


class Track(BaseModel):
    """A single video/image track in the timeline."""

    id: str = Field(..., description="Unique track identifier")
    clips: list[Clip] = Field(..., min_length=1)


class AudioTrack(BaseModel):
    """A dedicated audio track."""

    asset: str
    start: float = Field(0, ge=0)
    duration: float | None = None
    trim_in: float = Field(0, ge=0)
    trim_out: float | None = None
    volume: float = Field(1.0, ge=0, le=2.0)
    duck_on_speech: bool = False
    filters: list[Filter] = Field(default_factory=list)


class Timeline(BaseModel):
    """The full timeline — all tracks."""

    tracks: list[Track] = Field(..., min_length=1)
    audio: list[AudioTrack] = Field(default_factory=list)


class Settings(BaseModel):
    """Global project settings."""

    resolution: tuple[int, int] = (1920, 1080)
    fps: int = Field(30, gt=0, le=120)
    background: str = Field("#000000", pattern=r"^#[0-9a-fA-F]{6}$")


class Output(BaseModel):
    """Render output configuration."""

    path: str = "output.mp4"
    format: OutputFormat = OutputFormat.mp4
    codec: OutputCodec = OutputCodec.h264
    quality: Quality = Quality.high
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"


PRESETS: dict[str, Output] = {
    "youtube-1080p": Output(
        format=OutputFormat.mp4,
        codec=OutputCodec.h264,
        quality=Quality.high,
        audio_codec="aac",
        audio_bitrate="192k",
    ),
    "youtube-4k": Output(
        format=OutputFormat.mp4,
        codec=OutputCodec.h264,
        quality=Quality.high,
        audio_codec="aac",
        audio_bitrate="320k",
    ),
    "instagram-reel": Output(
        format=OutputFormat.mp4,
        codec=OutputCodec.h264,
        quality=Quality.high,
        audio_codec="aac",
        audio_bitrate="128k",
    ),
    "prores-master": Output(
        format=OutputFormat.mov,
        codec=OutputCodec.prores,
        quality=Quality.lossless,
        audio_codec="pcm_s16le",
        audio_bitrate="0",
    ),
    "web-vp9": Output(
        format=OutputFormat.webm,
        codec=OutputCodec.vp9,
        quality=Quality.medium,
        audio_codec="libopus",
        audio_bitrate="128k",
    ),
    "draft": Output(
        format=OutputFormat.mp4,
        codec=OutputCodec.h264,
        quality=Quality.low,
        audio_codec="aac",
        audio_bitrate="96k",
    ),
}

PRESET_RESOLUTIONS: dict[str, tuple[int, int]] = {
    "instagram-reel": (1080, 1920),
}


class Project(BaseModel):
    """A complete Declip project."""

    version: Literal["1.0"] = "1.0"
    settings: Settings = Field(default_factory=Settings)
    timeline: Timeline
    output: Output = Field(default_factory=Output)
    includes: list[str] = Field(
        default_factory=list,
        description="Paths to other project JSON files to pre-render and include as assets",
    )

    @classmethod
    def load(cls, path: str | Path, variables: dict[str, str] | None = None) -> "Project":
        """Load a project from JSON with optional ``{{variable}}`` substitution."""
        import json
        import re
        import sys

        text = Path(path).read_text()
        if variables:
            for key, value in variables.items():
                text = text.replace("{{" + key + "}}", value)
        unresolved = re.findall(r"\{\{(\w+)\}\}", text)
        if unresolved:
            print(
                f"Warning: unresolved template variables: {', '.join(set(unresolved))}",
                file=sys.stderr,
            )
        return cls.model_validate(json.loads(text))

    def save(self, path: str | Path) -> None:
        """Save the project to a JSON file."""
        Path(path).write_text(self.model_dump_json(indent=2, exclude_none=True))

    def resolve_auto_starts(self, project_dir: Path | None = None) -> None:
        """Resolve authoring conveniences in place using the canonical render plan.

        This method remains for backward compatibility with callers that expect
        mutation. The compiler owns the actual normalization rules; keeping this
        method as a thin compatibility adapter prevents CLI/MCP pre-resolution
        from drifting away from backend compilation.
        """
        import warnings

        from declip.compilers.render_plan import build_render_plan

        plan = build_render_plan(self, Path(project_dir or "."))
        for source_track, resolved_track in zip(
            self.timeline.tracks, plan.project.timeline.tracks, strict=True
        ):
            for source_clip, resolved_clip in zip(
                source_track.clips, resolved_track.clips, strict=True
            ):
                source_clip.start = resolved_clip.start
                source_clip.duration = resolved_clip.duration

        for warning in plan.warnings:
            warnings.warn(warning.message, RuntimeWarning, stacklevel=2)
