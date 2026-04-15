"""MCP tools for advanced media analysis — loudness, beats, OCR, MIDI, streams, contact sheets, audio extraction."""

from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def declip_loudness(
        file_path: str,
        normalize_to: str = "",
        time_series: bool = False,
    ) -> str:
        """Analyze audio loudness — and optionally normalize it in one step.

        Without normalize_to: measures and reports integrated LUFS, loudness range,
        true peak, platform compliance, and optional time-series.

        With normalize_to: also normalizes audio to the target using two-pass loudnorm.
        Accepts platform names (youtube, tiktok, podcast, broadcast) or a LUFS number.

        Args:
            file_path: Path to audio or video file
            normalize_to: Platform target to normalize to (e.g., "youtube", "podcast", "-18"). Empty = measure only.
            time_series: If True, include momentary and short-term LUFS measurements
        """
        from declip.analyze import analyze_loudness

        try:
            r = analyze_loudness(file_path, time_series=time_series)
            lines = [
                f"Integrated: {r.integrated_lufs} LUFS",
                f"Loudness range: {r.loudness_range} LU",
                f"True peak: {r.true_peak_dbtp} dBTP",
            ]
            if r.target_offset is not None:
                direction = "louder" if r.target_offset > 0 else "quieter"
                lines.append(f"Streaming target (-14 LUFS): {abs(r.target_offset):.1f} LU {direction}")

            compliance = []
            if r.youtube_ok:
                compliance.append("YouTube (-14)")
            if r.podcast_ok:
                compliance.append("Podcast (-16)")
            if r.broadcast_ok:
                compliance.append("Broadcast (-23)")
            if compliance:
                lines.append(f"Compliant: {', '.join(compliance)}")
            else:
                lines.append("Compliant: none")

            if time_series and r.momentary_lufs:
                # Find loudest and quietest moments
                loudest = max(r.momentary_lufs, key=lambda x: x[1])
                quietest = min((m for m in r.momentary_lufs if m[1] > -70), key=lambda x: x[1], default=None)
                lines.append(f"\nTime series ({len(r.momentary_lufs)} measurements):")
                lines.append(f"  Loudest moment: {loudest[1]:.1f} LUFS at {loudest[0]:.1f}s")
                if quietest:
                    lines.append(f"  Quietest moment: {quietest[1]:.1f} LUFS at {quietest[0]:.1f}s")

                # Flag sections exceeding platform limits
                hot_spots = [(t, v) for t, v in r.momentary_lufs if v > -8]
                if hot_spots:
                    lines.append(f"  ⚠ {len(hot_spots)} samples above -8 LUFS (may clip on platforms)")

                # Summary every ~10s for long files
                if len(r.short_term_lufs or []) > 20:
                    lines.append("  Short-term LUFS (sampled):")
                    step = max(1, len(r.short_term_lufs) // 10)
                    for i in range(0, len(r.short_term_lufs), step):
                        t, v = r.short_term_lufs[i]
                        lines.append(f"    {t:6.1f}s: {v:6.1f} LUFS")

            # Normalize if requested
            if normalize_to:
                from declip.ops import loudnorm as _loudnorm
                ok, norm_msg = _loudnorm(file_path, normalize_to)
                if ok:
                    lines.append(f"\nNormalized: {norm_msg}")
                else:
                    lines.append(f"\nNormalization failed: {norm_msg}")

            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_extract_audio(
        input_file: str,
        output_path: str | None = None,
        format: str = "wav",
        sample_rate: int | None = None,
    ) -> str:
        """Extract the audio track from a video or audio file.

        Args:
            input_file: Source file path
            output_path: Destination path (auto-generated if omitted)
            format: Output format: wav, mp3, flac, or aac
            sample_rate: Optional sample rate (e.g., 44100, 48000)
        """
        from declip.analyze import extract_audio

        try:
            result = extract_audio(input_file, output_path, format=format, sample_rate=sample_rate)
            size = Path(result).stat().st_size
            return f"Extracted: {result} ({size / 1024 / 1024:.1f} MB)"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_detect_beats(file_path: str) -> str:
        """Detect beats and estimate tempo (BPM) using librosa.

        Returns tempo in BPM and a list of beat timestamps.

        Args:
            file_path: Path to audio or video file
        """
        from declip.analyze import detect_beats

        try:
            r = detect_beats(file_path)
            lines = [f"Tempo: {r.tempo} BPM", f"Beats: {r.beat_count}"]
            if r.beat_count <= 30:
                for t in r.beat_times:
                    lines.append(f"  {t:.3f}s")
            else:
                for t in r.beat_times[:15]:
                    lines.append(f"  {t:.3f}s")
                lines.append(f"  ... and {r.beat_count - 15} more")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_ocr(
        video_path: str,
        timestamp: float | None = None,
        count: int = 5,
        lang: str = "eng",
    ) -> str:
        """Read text from video frames using OCR (Tesseract).

        Extract frames and run optical character recognition to read
        on-screen text, captions, overlays, error messages, etc.

        Args:
            video_path: Path to the video file
            timestamp: Specific timestamp to OCR (if omitted, samples multiple frames)
            count: Number of frames to OCR when timestamp not specified
            lang: Tesseract language code (e.g., eng, fra, deu)
        """
        from declip.analyze import ocr_frame, ocr_frames

        try:
            if timestamp is not None:
                r = ocr_frame(video_path, timestamp)
                if r.text:
                    return f"Frame at {r.timestamp:.2f}s:\n{r.text}"
                return f"Frame at {r.timestamp:.2f}s: (no text detected)"
            else:
                results = ocr_frames(video_path, count=count, lang=lang)
                lines = []
                for r in results:
                    text_preview = r.text[:120].replace("\n", " ") if r.text else "(no text)"
                    lines.append(f"{r.timestamp:.2f}s: {text_preview}")
                return "\n".join(lines) if lines else "No frames extracted"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_audio_to_midi(
        audio_path: str,
        output_path: str | None = None,
        confidence_threshold: float = 0.5,
    ) -> str:
        """Transcribe audio to MIDI using pYIN pitch detection.

        Detects musical notes (pitch, timing, velocity) from audio.
        Useful for music analysis, animation timing, beat sync verification.

        Args:
            audio_path: Path to audio or video file
            output_path: Path to save .mid file (optional)
            confidence_threshold: Pitch confidence threshold (0.0-1.0, lower = more notes)
        """
        from declip.analyze import audio_to_midi

        try:
            r = audio_to_midi(audio_path, output_path, confidence_threshold=confidence_threshold)
            lines = [f"Notes: {r.note_count}", f"Duration: {r.duration:.1f}s"]
            if r.output_path:
                lines.append(f"MIDI file: {r.output_path}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_streams(file_path: str) -> str:
        """List all streams in a media file — video, audio, subtitle tracks with details.

        Shows codec, resolution, FPS, channels, sample rate, and language tags.

        Args:
            file_path: Path to media file
        """
        from declip.analyze import list_streams

        try:
            streams = list_streams(file_path)
            lines = []
            for s in streams:
                lang = f" [{s.language}]" if s.language else ""
                if s.type == "video":
                    lines.append(f"#{s.index} video: {s.codec} {s.width}x{s.height} @ {s.fps:.1f}fps{lang}")
                elif s.type == "audio":
                    layout = f" ({s.channel_layout})" if s.channel_layout else ""
                    lines.append(f"#{s.index} audio: {s.codec} {s.channels}ch {s.sample_rate}Hz{layout}{lang}")
                else:
                    lines.append(f"#{s.index} {s.type}: {s.codec}{lang}")
            return "\n".join(lines) if lines else "No streams found"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_contact_sheet(
        video_path: str,
        output_path: str | None = None,
        columns: int = 4,
        rows: int = 4,
        thumb_width: int = 480,
    ) -> str:
        """Generate a contact sheet (thumbnail grid) from a video.

        Creates a single image with a grid of evenly-spaced thumbnails.
        Useful for visual overview and client review.

        Args:
            video_path: Path to the video file
            output_path: Where to save the image (defaults to videoname_contact.png)
            columns: Number of columns in the grid
            rows: Number of rows in the grid
            thumb_width: Width of each thumbnail in pixels
        """
        from declip.analyze import contact_sheet

        if not output_path:
            output_path = str(Path(video_path).stem + "_contact.png")

        try:
            result = contact_sheet(video_path, output_path, columns=columns, rows=rows,
                                    thumb_width=thumb_width)
            total = columns * rows
            return f"Contact sheet: {result} ({columns}x{rows} = {total} thumbnails)"
        except Exception as e:
            return f"Error: {e}"
