"""Transport-neutral structured result models.

These models belong to the Declip capability layer. MCP, CLI adapters, workflows,
and direct Python callers can share them without depending on an MCP package.
"""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field

class ProbeResult(BaseModel):
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
    @property
    def success(self) -> bool:
        return self.error is None
    def __str__(self) -> str:
        if self.error:
            return f"Error: {self.error}"
        lines = [f"File: {self.path}", f"Duration: {self.duration_seconds:.1f}s"]
        if self.width:
            fps = self.fps or 0.0
            video = f"Video: {self.width}x{self.height} @ {fps:.1f}fps ({self.video_codec})"
            if self.pixel_format: video += f", {self.pixel_format}"
            if self.bit_depth and self.bit_depth != 8: video += f", {self.bit_depth}-bit"
            if self.is_hdr: video += " [HDR]"
            if self.video_bitrate_bps: video += f", {self.video_bitrate_bps / 1_000_000:.1f} Mbps"
            lines.append(video)
            if self.color_space and self.color_space != "unknown":
                lines.append(f"Color: {self.color_space}, primaries={self.color_primaries}, transfer={self.color_transfer}")
        if self.audio_codec:
            audio = f"Audio: {self.audio_codec}, {self.audio_channels}ch, {self.audio_sample_rate}Hz"
            if self.audio_bitrate_bps: audio += f", {self.audio_bitrate_bps / 1000:.0f} kbps"
            lines.append(audio)
        lines.append(f"Size: {self.file_size_bytes / 1024 / 1024:.1f} MB")
        return "\n".join(lines)

class FileResult(BaseModel):
    success: bool
    output_path: Optional[str] = None
    file_size_bytes: Optional[int] = None
    error: Optional[str] = Field(default=None, description="Failure reason")
    @property
    def file_size_mb(self) -> Optional[float]:
        return None if self.file_size_bytes is None else self.file_size_bytes / 1024 / 1024

class TrimResult(FileResult):
    trim_in_seconds: float
    trim_out_seconds: float
    duration_seconds: float
    smart: bool = False
    re_encoded_head_seconds: Optional[float] = Field(default=None, description="Re-encoded head duration (smart mode); None if pure stream copy")
    stream_copied_tail_seconds: Optional[float] = None
    fallback_full_re_encode: bool = Field(default=False, description="True if smart mode fell back to a full re-encode")
    def __str__(self) -> str:
        if not self.success: return f"Error: {self.error}"
        label = "Smart trimmed" if self.smart else "Trimmed"
        text = f"{label} {self.trim_in_seconds}s-{self.trim_out_seconds}s ({self.duration_seconds:.1f}s)"
        if self.smart and self.re_encoded_head_seconds is not None:
            text += f"\nRe-encoded {self.re_encoded_head_seconds:.2f}s head, stream-copied {(self.stream_copied_tail_seconds or 0.0):.1f}s tail"
        elif self.fallback_full_re_encode:
            text += " (fallback re-encode)"
        size = f" ({self.file_size_mb:.1f} MB)" if self.file_size_mb is not None else ""
        return f"{text}\nOutput: {self.output_path}{size}"

class ConcatResult(FileResult):
    file_count: int = 0
    method: str = Field(default="re-encoded", description="'stream-copy' (no re-encode) or 're-encoded'")
    def __str__(self) -> str:
        if not self.success: return f"Error: {self.error}"
        method = "stream copy — no re-encode" if self.method == "stream-copy" else "re-encoded"
        size = f" ({self.file_size_mb:.1f} MB)" if self.file_size_mb is not None else ""
        return f"Concatenated {self.file_count} files ({method})\nOutput: {self.output_path}{size}"

class ThumbnailResult(FileResult):
    timestamp_seconds: Optional[float] = None
    width: Optional[int] = None
    height: Optional[int] = None
    def __str__(self) -> str:
        if not self.success: return f"Error: {self.error}"
        return f"Saved: {self.output_path} ({self.width}x{self.height}, t={(self.timestamp_seconds or 0.0):.2f}s)"
