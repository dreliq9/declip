"""MCP tools for advanced reusable Declip capabilities."""
from __future__ import annotations

from pathlib import Path
from mcp.server import MCPServer


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    def declip_transcribe(audio_path: str, output_srt: str | None = None, model_size: str = "base", language: str | None = None, word_timestamps: bool = False) -> str:
        """Transcribe speech with Whisper and optionally save SRT."""
        from declip.analyze import transcribe
        try:
            result = transcribe(audio_path, output_srt, model_size, language, word_timestamps)
            lines = [f"Language: {result.language}", f"Segments: {len(result.subtitles)}"]
            if result.srt_path: lines.append(f"SRT: {result.srt_path}")
            if result.words: lines.append(f"Words with timing: {len(result.words)}")
            lines.append(f"\n{result.full_text[:500]}")
            return "\n".join(lines)
        except Exception as exc:
            return f"Error: {exc}"

    @mcp.tool()
    def declip_chapters(video_path: str, scene_threshold: float = 0.3, output_path: str | None = None) -> str:
        """Generate chapter markers from scene cuts."""
        from declip.analyze import generate_chapters
        try:
            chapters = generate_chapters(video_path, scene_threshold, output_path)
            lines = [f"Chapters: {len(chapters)}"] + [f"  {chapter.index}. {chapter.start:.1f}s - {chapter.end:.1f}s: {chapter.title}" for chapter in chapters]
            if output_path: lines.append(f"Metadata: {output_path}")
            return "\n".join(lines)
        except Exception as exc:
            return f"Error: {exc}"

    @mcp.tool()
    def declip_waveform(audio_path: str, output_path: str | None = None, width: int = 1920, height: int = 200) -> str:
        """Generate a waveform visualization as PNG."""
        from declip.analyze import waveform
        output_path = output_path or str(Path(audio_path).stem + "_waveform.png")
        try: return f"Waveform: {waveform(audio_path, output_path, width, height)}"
        except Exception as exc: return f"Error: {exc}"

    @mcp.tool()
    def declip_export_fcpxml(project_path: str, output_path: str | None = None) -> str:
        """Export a Declip project to FCPXML."""
        from declip.analyze import export_fcpxml
        output_path = output_path or str(Path(project_path).with_suffix(".fcpxml"))
        try: return f"FCPXML exported: {export_fcpxml(project_path, output_path)}"
        except Exception as exc: return f"Error: {exc}"

    @mcp.tool()
    def declip_batch_render(project_files: list[str], preset: str | None = None) -> str:
        """Render multiple Declip project files in sequence."""
        from declip.project_ops import batch_render
        return batch_render(project_files, preset)
