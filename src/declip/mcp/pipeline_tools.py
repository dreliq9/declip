"""MCP adapter for Declip production pipelines."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from declip.pipelines import production


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    def declip_auto_caption(input_file: str, style: str = "bold", model_size: str = "base", language: str | None = None, output_path: str | None = None, ass_only: bool = False) -> str:
        """Generate word-timed styled captions and optionally burn them into video."""
        return str(production.auto_caption(input_file, style, model_size, language, output_path, ass_only))

    @mcp.tool()
    def declip_tts(text: str, output_path: str = "voiceover.mp3", voice: str = "en-US-GuyNeural", rate: str = "+0%", pitch: str = "+0Hz", output_words: bool = False) -> str:
        """Generate neural TTS voiceover with optional word timing metadata."""
        return str(production.tts(text, output_path, voice, rate, pitch, output_words))

    @mcp.tool()
    def declip_tts_voices(language: str = "en") -> str:
        """List available edge-tts voices filtered by language prefix."""
        return str(production.tts_voices(language))

    @mcp.tool()
    def declip_platform_export(input_file: str, platforms: str = "youtube,shorts,reels", reframe: str = "center_crop", output_dir: str | None = None) -> str:
        """Export loudness-normalized platform variants with selectable reframing."""
        return str(production.platform_export(input_file, platforms, reframe, output_dir))

    @mcp.tool()
    def declip_storyboard(shots: str, output_path: str = "storyboard_output.mp4", voice: str = "", music: str = "", music_volume: float = 0.3, caption_style: str = "", transition: str = "dissolve", transition_duration: float = 0.5) -> str:
        """Assemble a JSON shot list into a video with optional narration, music, and captions."""
        return str(production.storyboard(shots, output_path, voice, music, music_volume, caption_style, transition, transition_duration))
