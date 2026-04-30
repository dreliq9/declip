"""Pydantic input/result models for declip workflows.

Each workflow has a `<Name>Result` model that subclasses `WorkflowResult`.
`__str__` produces a human-readable summary mirroring what the equivalent
bash script's tail output would have shown.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class WorkflowResult(BaseModel):
    """Common envelope for every workflow's result."""

    success: bool = True
    error: Optional[str] = Field(default=None, description="Set when the workflow failed")
    output_path: Optional[str] = None
    duration_seconds: Optional[float] = None
    elapsed_ms: int = 0

    def __str__(self) -> str:
        if not self.success:
            return f"Error: {self.error}"
        out = self.output_path or "(no output)"
        if self.duration_seconds is not None:
            return f"OK: {out} ({self.duration_seconds:.1f}s)"
        return f"OK: {out}"


# ---------------------------------------------------------------------------
# Ingest
# ---------------------------------------------------------------------------

class IngestResult(WorkflowResult):
    """Probe + loudness-normalized output."""

    metadata_path: Optional[str] = None
    target_lufs: Optional[float] = None
    graded: bool = False
    skipped_loudnorm: bool = False

    def __str__(self) -> str:
        if not self.success:
            return f"Error: {self.error}"
        lines = [f"Ingest → {self.output_path}"]
        if self.duration_seconds is not None:
            lines.append(f"  Duration: {self.duration_seconds:.1f}s")
        if self.target_lufs is not None and not self.skipped_loudnorm:
            lines.append(f"  Loudnorm target: {self.target_lufs} LUFS")
        if self.skipped_loudnorm:
            lines.append("  Loudnorm skipped (no audio)")
        if self.graded:
            lines.append("  Auto-grade: applied")
        if self.metadata_path:
            lines.append(f"  Metadata: {self.metadata_path}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Cutdown
# ---------------------------------------------------------------------------

class CutdownSegment(BaseModel):
    """One clip in the highlight reel."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


class CutdownResult(WorkflowResult):
    """Long source → highlight reel."""

    project_path: Optional[str] = None
    source_duration_seconds: Optional[float] = None
    segments: list[CutdownSegment] = Field(default_factory=list)
    fallback_used: bool = Field(default=False, description="True when scene-detect produced too little material and even-spaced sampling kicked in")

    def __str__(self) -> str:
        if not self.success:
            return f"Error: {self.error}"
        lines = [f"Cutdown → {self.output_path}"]
        if self.source_duration_seconds and self.duration_seconds:
            ratio = self.duration_seconds / self.source_duration_seconds * 100
            lines.append(f"  {self.source_duration_seconds:.0f}s → {self.duration_seconds:.1f}s ({ratio:.1f}%)")
        if self.segments:
            lines.append(f"  Picked {len(self.segments)} segment(s)")
        if self.fallback_used:
            lines.append("  Fallback: evenly-spaced sampling (scene-detect produced too little material)")
        if self.project_path:
            lines.append(f"  Project: {self.project_path}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Speech cleanup
# ---------------------------------------------------------------------------

class SpeechSegment(BaseModel):
    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


class SpeechCleanupResult(WorkflowResult):
    """Talking-head jump-cut edit."""

    project_path: Optional[str] = None
    srt_path: Optional[str] = None
    captions_burned: bool = False
    source_duration_seconds: Optional[float] = None
    segments_kept: int = 0
    kept_seconds: float = 0.0

    def __str__(self) -> str:
        if not self.success:
            return f"Error: {self.error}"
        lines = [f"Speech cleanup → {self.output_path}"]
        if self.source_duration_seconds:
            pct = (self.kept_seconds / self.source_duration_seconds * 100) if self.source_duration_seconds else 0
            lines.append(f"  {self.source_duration_seconds:.0f}s → {self.kept_seconds:.1f}s ({pct:.0f}%)")
        if self.segments_kept:
            lines.append(f"  Kept {self.segments_kept} speech segment(s)")
        if self.captions_burned:
            lines.append("  Captions: burned in")
        elif self.srt_path:
            lines.append(f"  Captions: sidecar at {self.srt_path}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Beat-sync
# ---------------------------------------------------------------------------

class BeatSyncResult(WorkflowResult):
    """Video cut on music beats."""

    project_path: Optional[str] = None
    bpm: Optional[float] = None
    beat_count: int = 0
    cut_count: int = 0
    stride: int = 1

    def __str__(self) -> str:
        if not self.success:
            return f"Error: {self.error}"
        lines = [f"Beat-sync → {self.output_path}"]
        if self.bpm:
            lines.append(f"  Tempo: {self.bpm:.1f} BPM ({self.beat_count} beats)")
        if self.cut_count:
            label = "every beat" if self.stride == 1 else f"every {self.stride}th beat"
            lines.append(f"  Cuts: {self.cut_count} ({label})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Vertical
# ---------------------------------------------------------------------------

class VerticalResult(WorkflowResult):
    """9:16 reformat."""

    source_resolution: Optional[tuple[int, int]] = None
    target_resolution: Optional[tuple[int, int]] = None
    mode: Optional[str] = None
    skipped_reframe: bool = False

    def __str__(self) -> str:
        if not self.success:
            return f"Error: {self.error}"
        lines = [f"Vertical → {self.output_path}"]
        if self.source_resolution and self.target_resolution:
            sw, sh = self.source_resolution
            tw, th = self.target_resolution
            lines.append(f"  {sw}x{sh} → {tw}x{th} (mode: {self.mode})")
        if self.skipped_reframe:
            lines.append("  Reframe skipped (source already vertical)")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------

class ReviewResult(WorkflowResult):
    """QA report pack."""

    report_path: Optional[str] = None
    scene_cut_count: int = 0
    silent_segment_count: int = 0
    bpm: Optional[float] = None
    integrated_lufs: Optional[float] = None
    sparse_frame_count: int = 0
    cut_frame_count: int = 0

    def __str__(self) -> str:
        if not self.success:
            return f"Error: {self.error}"
        lines = [f"Review → {self.report_path}"]
        if self.duration_seconds is not None:
            lines.append(f"  Source duration: {self.duration_seconds:.1f}s")
        lines.append(f"  Scene cuts: {self.scene_cut_count}")
        lines.append(f"  Silent segments: {self.silent_segment_count}")
        if self.bpm:
            lines.append(f"  Tempo: {self.bpm:.1f} BPM")
        if self.integrated_lufs is not None:
            lines.append(f"  Integrated loudness: {self.integrated_lufs:.1f} LUFS")
        return "\n".join(lines)
