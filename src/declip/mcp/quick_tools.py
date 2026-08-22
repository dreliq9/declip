"""MCP adapter for structured Declip quick operations."""
from __future__ import annotations

from typing import Annotated, Optional
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from declip import quick
from declip.results import ConcatResult, ProbeResult, ThumbnailResult, TrimResult


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def declip_probe(file_path: Annotated[str, Field(description="Path to a video or audio file")]) -> ProbeResult:
        """Probe media properties including duration, codecs, resolution, HDR, and size."""
        return quick.probe(file_path)

    @mcp.tool()
    def declip_trim(
        input_file: Annotated[str, Field(description="Path to the input video file")],
        trim_in: Annotated[float, Field(ge=0, description="Start time in seconds")],
        trim_out: Annotated[float, Field(gt=0, description="End time in seconds")],
        smart: Annotated[bool, Field(description="Use keyframe-aware hybrid cut")] = False,
        output_path: Annotated[Optional[str], Field(default=None, description="Output path")] = None,
    ) -> TrimResult:
        """Trim a media file, optionally re-encoding only around the leading cut."""
        return quick.trim(input_file, trim_in, trim_out, smart, output_path)

    @mcp.tool()
    def declip_concat(
        files: Annotated[list[str], Field(min_length=2, description="Video files in order")],
        output_path: Annotated[str, Field(description="Output file path")] = "concat_output.mp4",
        preset: Annotated[Optional[str], Field(default=None, description="Optional output preset")] = None,
    ) -> ConcatResult:
        """Concatenate compatible inputs by stream copy, otherwise normalize and re-encode."""
        return quick.concat(files, output_path, preset)

    @mcp.tool()
    def declip_thumbnail(
        input_file: Annotated[str, Field(description="Path to the video file")],
        timestamp: Annotated[float, Field(ge=0, description="Time in seconds")]=1.0,
        output_path: Annotated[Optional[str], Field(default=None, description="Output PNG path")]=None,
    ) -> ThumbnailResult:
        """Extract a video frame as PNG."""
        return quick.thumbnail(input_file, timestamp, output_path)
