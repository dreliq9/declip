"""Backward-compatible MCP imports for Declip's transport-neutral results."""

from declip.results import ConcatResult, FileResult, ProbeResult, ThumbnailResult, TrimResult

__all__ = ["ProbeResult", "FileResult", "TrimResult", "ConcatResult", "ThumbnailResult"]
