"""Shared Pydantic models for structured MCP tool outputs.

FastMCP serializes these as both `content` (human-readable text via __str__)
and `structuredContent` (typed JSON). Agents can read fields like
`result.duration` directly without parsing string output.

Scope (v0.8.0): the four `quick_tools.py` operations — probe, trim, concat,
thumbnail. Other tool modules (analysis, edit, generate, pipeline, project,
media, advanced) still return strings; same envelope pattern applies when
the rest catch up.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Probe
# ---------------------------------------------------------------------------

class ProbeResult(BaseModel):
    """Media file probe — every field defined here, populated when present."""

    path: str
    duration_seconds: float
    file_size_bytes: int

    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    video_codec: Optional[str] = None
    pixel_format: Optional[str] = None
    bit_depth: Optional[int] = None
    is_hdr: bool = False
    video_bitrate_bps: Optional[int] = None
    color_space: Optional[str] = None
    color_primaries: Optional[str] = None
    color_transfer: Optional[str] = None

    audio_codec: Optional[str] = None
    audio_channels: Optional[int] = None
    audio_sample_rate: Optional[int] = None
    audio_bitrate_bps: Optional[int] = None

    error: Optional[str] = Field(default=None, description="Set when probe failed")

    def __str__(self) -> str:
        if self.error:
            return f"Error: {self.error}"
        lines = [f"File: {self.path}", f"Duration: {self.duration_seconds:.1f}s"]
        if self.width:
            vid = f"Video: {self.width}x{self.height} @ {self.fps:.1f}fps ({self.video_codec})"
            if self.pixel_format:
                vid += f", {self.pixel_format}"
            if self.bit_depth and self.bit_depth != 8:
                vid += f", {self.bit_depth}-bit"
            if self.is_hdr:
                vid += " [HDR]"
            if self.video_bitrate_bps:
                vid += f", {self.video_bitrate_bps / 1_000_000:.1f} Mbps"
            lines.append(vid)
            if self.color_space and self.color_space != "unknown":
                lines.append(
                    f"Color: {self.color_space}, primaries={self.color_primaries}, "
                    f"transfer={self.color_transfer}"
                )
        if self.audio_codec:
            aud = f"Audio: {self.audio_codec}, {self.audio_channels}ch, {self.audio_sample_rate}Hz"
            if self.audio_bitrate_bps:
                aud += f", {self.audio_bitrate_bps / 1000:.0f} kbps"
            lines.append(aud)
        lines.append(f"Size: {self.file_size_bytes / 1024 / 1024:.1f} MB")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Trim / Concat / Thumbnail share an output-file envelope
# ---------------------------------------------------------------------------

class FileResult(BaseModel):
    """Generic 'wrote a file' result. Subclasses add tool-specific fields."""

    success: bool
    output_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    error: Optional[str] = Field(default=None, description="Failure reason")

    @property
    def file_size_mb(self) -> Optional[float]:
        if self.file_size_bytes is None:
            return None
        return self.file_size_bytes / 1024 / 1024


class TrimResult(FileResult):
    trim_in_seconds: float
    trim_out_seconds: float
    duration_seconds: float
    smart: bool = False
    re_encoded_head_seconds: Optional[float] = Field(
        default=None,
        description="Re-encoded head duration (smart mode); None if pure stream copy",
    )
    stream_copied_tail_seconds: Optional[float] = Field(default=None)
    fallback_full_re_encode: bool = Field(
        default=False,
        description="True if smart mode fell back to a full re-encode",
    )

    def __str__(self) -> str:
        if not self.success:
            return f"Error: {self.error}"
        head = (
            f"Smart trimmed" if self.smart else "Trimmed"
        )
        line = (
            f"{head} {self.trim_in_seconds}s-{self.trim_out_seconds}s "
            f"({self.duration_seconds:.1f}s)"
        )
        if self.smart and self.re_encoded_head_seconds is not None:
            line += (
                f"\nRe-encoded {self.re_encoded_head_seconds:.2f}s head, "
                f"stream-copied {self.stream_copied_tail_seconds:.1f}s tail"
            )
        elif self.fallback_full_re_encode:
            line += " (fallback re-encode)"
        size_mb = self.file_size_mb
        size_str = f" ({size_mb:.1f} MB)" if size_mb is not None else ""
        line += f"\nOutput: {self.output_path}{size_str}"
        return line


class ConcatResult(FileResult):
    file_count: int = 0
    method: str = Field(
        default="re-encoded",
        description="'stream-copy' (no re-encode) or 're-encoded'",
    )

    def __str__(self) -> str:
        if not self.success:
            return f"Error: {self.error}"
        method_note = "stream copy — no re-encode" if self.method == "stream-copy" else "re-encoded"
        size_mb = self.file_size_mb
        size_str = f" ({size_mb:.1f} MB)" if size_mb is not None else ""
        return (
            f"Concatenated {self.file_count} files ({method_note})\n"
            f"Output: {self.output_path}{size_str}"
        )


class ThumbnailResult(FileResult):
    timestamp_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None

    def __str__(self) -> str:
        if not self.success:
            return f"Error: {self.error}"
        return (
            f"Saved: {self.output_path} ({self.width}x{self.height}, "
            f"t={self.timestamp_seconds:.2f}s)"
        )
