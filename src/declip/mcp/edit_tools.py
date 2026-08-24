"""MCP adapter for reusable Declip edit capabilities."""
from __future__ import annotations

from mcp.server import MCPServer
from declip import edit


def register(mcp: MCPServer) -> None:
    @mcp.tool()
    def declip_text_overlay(input_file: str, text: str, position: str = "bottom", font_size: int = 48, font_color: str = "white", bg_color: str = "", start: float = 0, duration: float = 0, font: str = "Arial", shadow_color: str = "", shadow_x: int = 0, shadow_y: int = 0, outline_width: int = 0, outline_color: str = "black", output_path: str | None = None) -> str:
        """Burn a configurable text overlay onto a video."""
        return edit.text_overlay(input_file, text, position, font_size, font_color, bg_color, start, duration, font, shadow_color, shadow_x, shadow_y, outline_width, outline_color, output_path)

    @mcp.tool()
    def declip_image_overlay(input_file: str, image_path: str, position: str = "top-right", scale: float = 0.15, opacity: float = 0.8, start: float = 0, duration: float = 0, output_path: str | None = None) -> str:
        """Overlay an image, logo, watermark, or PIP frame onto a video."""
        return edit.image_overlay(input_file, image_path, position, scale, opacity, start, duration, output_path)

    @mcp.tool()
    def declip_transition(file_a: str, file_b: str, transition: str = "dissolve", duration: float = 1.0, output_path: str = "transition_output.mp4") -> str:
        """Apply an FFmpeg xfade transition between two clips."""
        return edit.transition(file_a, file_b, transition, duration, output_path)

    @mcp.tool()
    def declip_speed(input_file: str, speed: float = 2.0, interpolate: bool = False, output_path: str | None = None) -> str:
        """Change playback speed with optional optical-flow slow-motion interpolation."""
        return edit.speed(input_file, speed, interpolate, output_path)

    @mcp.tool()
    def declip_color(input_file: str, brightness: float = 0.0, contrast: float = 1.0, saturation: float = 1.0, greyscale: bool = False, temperature: float = 0, shadows_r: float = 0, shadows_g: float = 0, shadows_b: float = 0, midtones_r: float = 0, midtones_g: float = 0, midtones_b: float = 0, highlights_r: float = 0, highlights_g: float = 0, highlights_b: float = 0, auto_levels: bool = False, output_path: str | None = None) -> str:
        """Adjust basic and advanced video color parameters in one pass."""
        return edit.color(input_file, brightness, contrast, saturation, greyscale, temperature, shadows_r, shadows_g, shadows_b, midtones_r, midtones_g, midtones_b, highlights_r, highlights_g, highlights_b, auto_levels, output_path)

    @mcp.tool()
    def declip_crop_resize(input_file: str, width: int = 0, height: int = 0, crop: str = "", aspect: str = "", pad_color: str = "black", output_path: str | None = None) -> str:
        """Crop, resize, or reframe a video to a target size/aspect."""
        return edit.crop_resize(input_file, width, height, crop, aspect, pad_color, output_path)

    @mcp.tool()
    def declip_subtitle_burn(input_file: str, subtitle_path: str, font_size: int = 24, font_color: str = "white", outline_width: int = 1, shadow_offset: int = 1, margin_v: int = 30, alignment: int = 2, output_path: str | None = None) -> str:
        """Burn SRT/ASS subtitles into a video, preserving ASS styling when present."""
        return edit.subtitle_burn(input_file, subtitle_path, font_size, font_color, outline_width, shadow_offset, margin_v, alignment, output_path)

    @mcp.tool()
    def declip_reverse(input_file: str, audio: bool = True, chunk_seconds: int = 10, output_path: str | None = None) -> str:
        """Reverse video, chunking long inputs to limit memory use."""
        return edit.reverse(input_file, audio, chunk_seconds, output_path)

    @mcp.tool()
    def declip_gif(input_file: str, start: float = 0, duration: float = 5, width: int = 480, fps: int = 15, output_path: str | None = None) -> str:
        """Convert a video segment to an optimized palette GIF."""
        return edit.gif(input_file, start, duration, width, fps, output_path)

    @mcp.tool()
    def declip_split_screen(files: list[str], layout: str = "horizontal", width: int = 1920, height: int = 1080, border: int = 0, border_color: str = "black", audio_from: int = 0, pip_scale: float = 0.3, pip_position: str = "bottom-right", output_path: str = "splitscreen.mp4") -> str:
        """Tile 2-4 videos or create picture-in-picture with selectable audio."""
        return edit.split_screen(files, layout, width, height, border, border_color, audio_from, pip_scale, pip_position, output_path)

    @mcp.tool()
    def declip_freeze_frame(input_file: str, timestamp: float, hold_duration: float = 3.0, fps: int = 0, output_path: str | None = None) -> str:
        """Hold a frame from a source video for a requested duration."""
        return edit.freeze_frame(input_file, timestamp, hold_duration, fps, output_path)

    @mcp.tool()
    def declip_stabilize(input_file: str, shakiness: int = 5, smoothing: int = 10, zoom: float = 0, tripod: bool = False, output_path: str | None = None) -> str:
        """Run two-pass vidstab stabilization."""
        return edit.stabilize(input_file, shakiness, smoothing, zoom, tripod, output_path)

    @mcp.tool()
    def declip_audio_mix(video_file: str, audio_file: str, video_volume: float = 1.0, audio_volume: float = 0.5, audio_start: float = 0, replace: bool = False, output_path: str | None = None) -> str:
        """Mix or replace a video's audio track."""
        return edit.audio_mix(video_file, audio_file, video_volume, audio_volume, audio_start, replace, output_path)

    @mcp.tool()
    def declip_loop(input_file: str, count: int = 3, output_path: str | None = None) -> str:
        """Loop a video clip N times."""
        return edit.loop(input_file, count, output_path)

    @mcp.tool()
    def declip_fade(input_file: str, fade_in: float = 0, fade_out: float = 0, color: str = "black", output_path: str | None = None) -> str:
        """Apply synchronized video/audio fade-in and fade-out."""
        return edit.fade(input_file, fade_in, fade_out, color, output_path)

    @mcp.tool()
    def declip_sidechain(video_file: str, music_file: str, threshold: float = 0.02, ratio: float = 8.0, attack: float = 200, release: float = 1000, output_path: str | None = None) -> str:
        """Duck music under speech with sidechain compression."""
        return edit.sidechain(video_file, music_file, threshold, ratio, attack, release, output_path)

    @mcp.tool()
    def declip_denoise(input_file: str, strength: str = "medium", method: str = "fft", output_path: str | None = None) -> str:
        """Reduce audio noise using FFT or non-local-means filtering."""
        return edit.denoise(input_file, strength, method, output_path)
