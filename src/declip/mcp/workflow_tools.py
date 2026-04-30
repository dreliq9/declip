"""MCP tools for high-level declip workflows.

Each tool wraps a `declip.workflows.<name>.run(...)` call and returns the
typed Pydantic Result. FastMCP serializes these as both `content` (via
`__str__`) and `structuredContent` (via the Pydantic schema), so agents can
read fields directly without parsing the human-readable string.
"""

from __future__ import annotations

from typing import Optional

from mcp.server.fastmcp import FastMCP

from declip.workflows.types import (
    BeatSyncResult,
    CutdownResult,
    IngestResult,
    ReviewResult,
    SpeechCleanupResult,
    VerticalResult,
)


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def declip_workflow_ingest(
        input_path: str,
        output_path: Optional[str] = None,
        target: str = "-14",
        grade: bool = False,
    ) -> IngestResult:
        """Normalize a video to a known-good baseline: probe + loudnorm + optional auto-grade.

        Args:
            input_path: Source video.
            output_path: Output .mp4 (defaults to <basename>.normalized.mp4).
            target: Loudnorm target. Accepts a name (youtube/tiktok/podcast/broadcast)
                    or a LUFS number like "-14".
            grade: Apply a neutral auto-grade (slight contrast/saturation lift).
        """
        from declip.workflows import ingest
        return ingest.run(input_path=input_path, output_path=output_path,
                          target=target, grade=grade)

    @mcp.tool()
    def declip_workflow_cutdown(
        input_path: str,
        output_path: Optional[str] = None,
        target_seconds: float = 60.0,
        transition: str = "dissolve",
        crossfade_duration: float = 0.5,
        segment_min: float = 3.0,
        segment_max: float = 10.0,
        scene_threshold: float = 27.0,
    ) -> CutdownResult:
        """Cut a long source down to a short highlight reel via scene/silence detect.

        Args:
            input_path: Source video.
            output_path: Output .mp4 (defaults to <basename>.cutdown.mp4).
            target_seconds: Target highlight duration.
            transition: Transition between clips (dissolve, fade_black, wipe_left, etc).
            crossfade_duration: Transition duration in seconds.
            segment_min: Minimum candidate segment length.
            segment_max: Maximum candidate segment length per clip.
            scene_threshold: PySceneDetect ContentDetector threshold.
        """
        from declip.workflows import cutdown
        return cutdown.run(
            input_path=input_path, output_path=output_path,
            target_seconds=target_seconds, transition=transition,
            crossfade_duration=crossfade_duration,
            segment_min=segment_min, segment_max=segment_max,
            scene_threshold=scene_threshold,
        )

    @mcp.tool()
    def declip_workflow_speech_cleanup(
        input_path: str,
        output_path: Optional[str] = None,
        gap: float = 0.5,
        pad: float = 0.1,
        burn_captions: bool = False,
        whisper_model: str = "base",
    ) -> SpeechCleanupResult:
        """Build a jump-cut edit from a talking-head video.

        Args:
            input_path: Source video.
            output_path: Output .mp4 (defaults to <basename>.cleaned.mp4).
            gap: Drop silent gaps longer than this (seconds).
            pad: Pad each kept segment with this much head/tail (seconds).
            burn_captions: Burn the SRT into the rendered output (requires libass).
            whisper_model: faster-whisper model size (tiny/base/small/medium/large-v3).
        """
        from declip.workflows import speech_cleanup
        return speech_cleanup.run(
            input_path=input_path, output_path=output_path,
            gap=gap, pad=pad, burn_captions=burn_captions, whisper_model=whisper_model,
        )

    @mcp.tool()
    def declip_workflow_beat_sync(
        video_path: str,
        music_path: str,
        output_path: Optional[str] = None,
        stride: int = 1,
        window: Optional[float] = None,
    ) -> BeatSyncResult:
        """Cut video footage on the beats of a music track.

        Args:
            video_path: Source video.
            music_path: Music audio file.
            output_path: Output .mp4 (defaults to <video-basename>.beat.mp4).
            stride: Cut on every Nth beat (default 1 = every beat).
            window: Clip window length in seconds (defaults to inter-beat interval).
        """
        from declip.workflows import beat_sync
        return beat_sync.run(
            video_path=video_path, music_path=music_path,
            output_path=output_path, stride=stride, window=window,
        )

    @mcp.tool()
    def declip_workflow_vertical(
        input_path: str,
        output_path: Optional[str] = None,
        mode: str = "crop",
        width: int = 1080,
        height: int = 1920,
        background: str = "#000000",
        target: str = "-14",
        force: bool = False,
    ) -> VerticalResult:
        """Reframe horizontal video to 9:16 (TikTok / Reels / Shorts).

        Args:
            input_path: Source video.
            output_path: Output .mp4 (defaults to <basename>.vertical.mp4).
            mode: "crop" (zoom in), "pad" (letterbox), or "blur-pad" (blurred bg plate).
            width: Target width (rounded to even).
            height: Target height (rounded to even).
            background: Pad-mode background colour.
            target: Loudnorm target after reframe.
            force: Reframe even if source is already vertical.
        """
        from declip.workflows import vertical
        return vertical.run(
            input_path=input_path, output_path=output_path, mode=mode,
            width=width, height=height, background=background,
            target=target, force=force,
        )

    @mcp.tool()
    def declip_workflow_review(
        input_path: str,
        output_dir: Optional[str] = None,
        frame_count: int = 16,
        scene_threshold: float = 27.0,
    ) -> ReviewResult:
        """Generate a Phase 0–3 QA report pack for a rendered video.

        Args:
            input_path: Video to review.
            output_dir: Report directory (defaults to <basename>-review/).
            frame_count: Sparse-frame count.
            scene_threshold: Scene-detect ContentDetector threshold.
        """
        from declip.workflows import review
        return review.run(
            input_path=input_path, output_dir=output_dir,
            frame_count=frame_count, scene_threshold=scene_threshold,
        )
