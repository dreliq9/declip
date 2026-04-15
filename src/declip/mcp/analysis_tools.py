"""MCP tools for video analysis — scene detection, silence detection, frame extraction, review."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def declip_extract_frames(
        video_path: str,
        output_dir: str | None = None,
        count: int = 16,
        timestamps: str | None = None,
    ) -> str:
        """Extract multiple frames from a video as PNG images.

        Extracts evenly-spaced frames or frames at specific timestamps.

        Args:
            video_path: Path to the video file
            output_dir: Directory to save frames (defaults to videoname_frames/)
            count: Number of evenly-spaced frames (ignored if timestamps provided)
            timestamps: Comma-separated timestamps in seconds (e.g., "1.0,3.5,7.2")
        """
        from declip.analyze import extract_frames

        if not output_dir:
            output_dir = str(Path(video_path).stem + "_frames")

        ts_list = None
        if timestamps:
            ts_list = [float(t.strip()) for t in timestamps.split(",")]

        try:
            frames = extract_frames(video_path, output_dir, count=count, timestamps=ts_list)
            lines = [f"Extracted {len(frames)} frames → {output_dir}/"]
            for f in frames:
                lines.append(f"  {f.timestamp:.2f}s → {Path(f.path).name}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_detect_scenes(
        video_path: str,
        threshold: float = 27.0,
    ) -> str:
        """Detect scene changes/cuts in a video using PySceneDetect (ContentDetector).

        Returns timestamps where significant visual changes occur.
        Uses PySceneDetect if available (recommended), falls back to frame-diff analysis.

        Args:
            video_path: Path to the video file
            threshold: ContentDetector sensitivity (default 27.0; lower = more sensitive, e.g. 20.0 for dissolves)
        """
        from declip.analyze import detect_scenes

        try:
            cuts = detect_scenes(video_path, threshold=threshold)
            if not cuts:
                return "No scene cuts detected"
            lines = [f"Found {len(cuts)} scene cut(s):"]
            for c in cuts:
                lines.append(f"  {c.timestamp:.2f}s (score: {c.score:.3f})")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_detect_audio(
        file_path: str,
        mode: str = "speech",
        noise_threshold: str = "-30dB",
        min_duration: float = 0.5,
        vad_threshold: float = 0.5,
    ) -> str:
        """Detect speech or silence segments in audio/video.

        Mode "speech" uses Silero VAD neural network to find actual human speech
        (best for ducking, segmentation, captioning). Mode "silence" uses FFmpeg
        silencedetect to find quiet sections (best for finding gaps, pauses, dead air).

        Args:
            file_path: Path to audio or video file
            mode: "speech" (find where people talk, Silero VAD) or "silence" (find quiet sections, FFmpeg)
            noise_threshold: Noise floor for silence mode (e.g., "-30dB")
            min_duration: Minimum segment duration in seconds
            vad_threshold: VAD sensitivity for speech mode (0.0-1.0, higher = stricter)
        """
        try:
            if mode == "speech":
                from declip.analyze import detect_speech
                segments = detect_speech(file_path, threshold=vad_threshold,
                                          min_speech_duration=min_duration)
                if not segments:
                    return "No speech detected"
                total = sum(s.duration for s in segments)
                lines = [f"Found {len(segments)} speech segment(s) ({total:.1f}s total):"]
                for s in segments:
                    lines.append(f"  {s.start:.2f}s - {s.end:.2f}s ({s.duration:.1f}s)")
                return "\n".join(lines)
            else:
                from declip.analyze import detect_silence
                segments = detect_silence(file_path, noise_threshold=noise_threshold,
                                           min_duration=min_duration)
                if not segments:
                    return "No silent segments detected"
                lines = [f"Found {len(segments)} silent segment(s):"]
                for s in segments:
                    lines.append(f"  {s.start:.2f}s - {s.end:.2f}s ({s.duration:.1f}s)")
                return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_review(
        video_path: str,
        output_dir: str | None = None,
        frame_count: int = 16,
        scene_threshold: float = 27.0,
    ) -> str:
        """Full self-review pipeline for a rendered video.

        Runs the 4-phase review workflow:
        1. Sparse overview frames (evenly spaced)
        2. Scene detection + silence detection + black frame + freeze frame detection
        3. Targeted frames at detected cut points (0.5s before and after each cut)
        4. Issue summary (flags black frames, frozen frames, long silences)

        Use this after rendering to verify the output without watching it.

        Args:
            video_path: Path to the video to review
            output_dir: Directory for review output (frames, etc.)
            frame_count: Number of overview frames to extract
            scene_threshold: Scene detection sensitivity (default 27.0 for PySceneDetect)
        """
        from declip.analyze import review

        if not output_dir:
            output_dir = str(Path(video_path).stem + "_review")

        try:
            result = review(
                video_path, output_dir,
                frame_count=frame_count,
                scene_threshold=scene_threshold,
            )
            return result.summary()
        except Exception as e:
            return f"Error: {e}"
