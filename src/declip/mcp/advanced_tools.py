"""MCP tools for advanced features — transcription, chapters, waveform, ducking, FCPXML, watch, batch."""

from __future__ import annotations

from pathlib import Path

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def declip_transcribe(
        audio_path: str,
        output_srt: str | None = None,
        model_size: str = "base",
        language: str | None = None,
        word_timestamps: bool = False,
    ) -> str:
        """Transcribe speech to text using Whisper. Optionally saves .srt subtitle file.

        Args:
            audio_path: Path to audio or video file
            output_srt: Path to save .srt file (optional)
            model_size: Whisper model: tiny, base, small, medium, large-v3
            language: Language code (e.g., "en") or None for auto-detect
            word_timestamps: Enable per-word timing (needed for auto-captions/karaoke)
        """
        from declip.analyze import transcribe

        try:
            r = transcribe(audio_path, output_srt, model_size, language, word_timestamps)
            lines = [f"Language: {r.language}", f"Segments: {len(r.subtitles)}"]
            if r.srt_path:
                lines.append(f"SRT: {r.srt_path}")
            if r.words:
                lines.append(f"Words with timing: {len(r.words)}")
            lines.append(f"\n{r.full_text[:500]}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_chapters(
        video_path: str,
        scene_threshold: float = 0.3,
        output_path: str | None = None,
    ) -> str:
        """Generate chapter markers from scene cuts. Optionally writes FFmpeg metadata file.

        Args:
            video_path: Path to the video file
            scene_threshold: Scene detection threshold (0.0-1.0)
            output_path: Path to save chapters metadata file (optional)
        """
        from declip.analyze import generate_chapters

        try:
            chapters = generate_chapters(video_path, scene_threshold, output_path)
            lines = [f"Chapters: {len(chapters)}"]
            for ch in chapters:
                lines.append(f"  {ch.index}. {ch.start:.1f}s - {ch.end:.1f}s: {ch.title}")
            if output_path:
                lines.append(f"Metadata: {output_path}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_waveform(
        audio_path: str,
        output_path: str | None = None,
        width: int = 1920,
        height: int = 200,
    ) -> str:
        """Generate a waveform visualization as PNG.

        Args:
            audio_path: Path to audio or video file
            output_path: Where to save the PNG (defaults to input_waveform.png)
            width: Image width in pixels
            height: Image height in pixels
        """
        from declip.analyze import waveform

        if not output_path:
            output_path = str(Path(audio_path).stem + "_waveform.png")

        try:
            result = waveform(audio_path, output_path, width, height)
            return f"Waveform: {result}"
        except Exception as e:
            return f"Error: {e}"

    # declip_duck_filter removed — use declip_sidechain for actual audio ducking

    @mcp.tool()
    def declip_export_fcpxml(
        project_path: str,
        output_path: str | None = None,
    ) -> str:
        """Export a declip project to FCPXML format for Final Cut Pro.

        Args:
            project_path: Path to declip project.json
            output_path: Path to save .fcpxml file (defaults to project_name.fcpxml)
        """
        from declip.analyze import export_fcpxml

        if not output_path:
            output_path = str(Path(project_path).with_suffix(".fcpxml"))

        try:
            result = export_fcpxml(project_path, output_path)
            return f"FCPXML exported: {result}"
        except Exception as e:
            return f"Error: {e}"

    @mcp.tool()
    def declip_batch_render(
        project_files: list[str],
        preset: str | None = None,
    ) -> str:
        """Render multiple project files in sequence.

        Args:
            project_files: List of paths to project.json files
            preset: Optional output preset to apply to all
        """
        from declip.schema import Project, PRESETS, PRESET_RESOLUTIONS
        from declip.backends import ffmpeg as ffmpeg_backend
        from declip.backends import mlt as mlt_backend
        from declip.output import OutputManager

        results = []
        for pf in project_files:
            try:
                project = Project.load(pf)
                project_dir = Path(pf).parent
                project.resolve_auto_starts(project_dir)

                if preset and preset in PRESETS:
                    project.output = PRESETS[preset].model_copy()
                    if preset in PRESET_RESOLUTIONS:
                        project.settings.resolution = PRESET_RESOLUTIONS[preset]

                out = OutputManager(json_mode=False, quiet=True)
                use_ffmpeg = ffmpeg_backend.can_handle(project)
                if use_ffmpeg:
                    success = ffmpeg_backend.render(project, project_dir, out)
                else:
                    success = mlt_backend.render(project, project_dir, out)

                status = "OK" if success else "FAILED"
                results.append(f"{status}: {pf} → {project.output.path}")
            except Exception as e:
                results.append(f"ERROR: {pf}: {e}")

        return "\n".join(results)
