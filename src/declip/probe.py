"""Media file probing via PyAV."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

import av


@dataclass
class AssetInfo:
    path: str
    duration: float          # seconds
    width: int | None        # None for audio-only
    height: int | None
    fps: float | None
    codec: str
    audio_codec: str | None
    audio_channels: int | None
    audio_sample_rate: int | None
    file_size: int           # bytes
    # Extended fields (Phase 3)
    pixel_format: str | None = None       # e.g. yuv420p, yuv420p10le
    bit_depth: int | None = None          # 8, 10, 12
    color_space: str | None = None        # e.g. bt709, bt2020nc
    color_primaries: str | None = None    # e.g. bt709, bt2020
    color_transfer: str | None = None     # e.g. smpte2084 (PQ/HDR10), arib-std-b67 (HLG)
    video_bitrate: int | None = None      # bits per second
    audio_bitrate: int | None = None      # bits per second
    is_hdr: bool = False                  # True if PQ or HLG transfer

    def to_dict(self) -> dict:
        return asdict(self)


def probe(path: str | Path) -> AssetInfo:
    """Probe a media file and return structured info."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Asset not found: {path}")

    container = av.open(str(path))

    try:
        return _probe_container(container, path)
    finally:
        container.close()


def _probe_container(container, path: Path) -> AssetInfo:
    """Extract info from an open PyAV container."""
    width = height = fps = None
    codec = "unknown"
    audio_codec = audio_channels = audio_sample_rate = None
    pixel_format = color_space = color_primaries = color_transfer = None
    bit_depth = video_bitrate = audio_bitrate = None
    is_hdr = False

    if container.streams.video:
        vs = container.streams.video[0]
        cc = vs.codec_context
        width = cc.width
        height = cc.height
        fps = float(vs.average_rate) if vs.average_rate else None
        codec = cc.name

        # Pixel format and bit depth
        if cc.pix_fmt:
            pixel_format = cc.pix_fmt
            # Derive bit depth from pixel format name
            pf = cc.pix_fmt
            if "10le" in pf or "10be" in pf or "p10" in pf:
                bit_depth = 10
            elif "12le" in pf or "12be" in pf or "p12" in pf:
                bit_depth = 12
            else:
                bit_depth = 8

        # Color properties
        try:
            color_space = str(vs.codec_context.color_space) if vs.codec_context.color_space else None
        except Exception:
            pass
        try:
            color_primaries = str(vs.codec_context.color_primaries) if vs.codec_context.color_primaries else None
        except Exception:
            pass
        try:
            color_transfer = str(vs.codec_context.color_trc) if vs.codec_context.color_trc else None
        except Exception:
            pass

        # HDR detection: PQ (HDR10/DV) or HLG
        HDR_TRANSFERS = {"smpte2084", "arib-std-b67"}
        if color_transfer and any(h in color_transfer.lower() for h in HDR_TRANSFERS):
            is_hdr = True

        # Video bitrate
        if vs.bit_rate:
            video_bitrate = vs.bit_rate

    if container.streams.audio:
        aus = container.streams.audio[0]
        audio_codec = aus.codec_context.name
        audio_channels = aus.codec_context.channels
        audio_sample_rate = aus.codec_context.sample_rate
        if aus.bit_rate:
            audio_bitrate = aus.bit_rate

    duration = float(container.duration / av.time_base) if container.duration else 0.0

    return AssetInfo(
        path=str(path),
        duration=duration,
        width=width,
        height=height,
        fps=fps,
        codec=codec,
        audio_codec=audio_codec,
        audio_channels=audio_channels,
        audio_sample_rate=audio_sample_rate,
        file_size=path.stat().st_size,
        pixel_format=pixel_format,
        bit_depth=bit_depth,
        color_space=color_space,
        color_primaries=color_primaries,
        color_transfer=color_transfer,
        video_bitrate=video_bitrate,
        audio_bitrate=audio_bitrate,
        is_hdr=is_hdr,
    )


def probe_all(paths: list[str | Path]) -> list[AssetInfo]:
    """Probe multiple assets."""
    return [probe(p) for p in paths]
