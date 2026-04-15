"""MCP tools for quick edits — text, overlays, color, speed, transitions, etc.

All tools operate directly on files via FFmpeg. No project.json needed.
Zero API cost — everything runs locally.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP


def _run_ffmpeg(cmd: list[str], timeout: int = 300) -> tuple[bool, str]:
    """Run an FFmpeg command, return (success, message)."""
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        err = proc.stderr.decode(errors="replace")[-500:]
        return False, f"FFmpeg error:\n{err}"
    return True, ""


def _output_path(input_file: str, output: str | None, suffix: str) -> str:
    if output:
        return output
    p = Path(input_file)
    # If suffix starts with '.', replace extension
    if suffix.startswith("."):
        return str(p.with_suffix(suffix))
    return str(p.with_stem(p.stem + suffix))


def _file_info(path: str) -> str:
    p = Path(path)
    if p.exists():
        mb = p.stat().st_size / 1024 / 1024
        return f"{path} ({mb:.1f} MB)"
    return path


def _escape_drawtext(text: str) -> str:
    """Escape text for FFmpeg drawtext filter."""
    # FFmpeg drawtext escaping: \ : ' must be escaped
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "'\\''")
    text = text.replace(":", "\\:")
    text = text.replace(";", "\\;")
    text = text.replace("%", "%%")
    return text


def _find_font(font_name: str) -> str:
    """Find a font file on macOS, return fontfile arg or font arg."""
    mac_path = f"/System/Library/Fonts/Supplemental/{font_name}.ttf"
    if os.path.exists(mac_path):
        return f"fontfile={mac_path}"
    # Try .ttc variant
    mac_ttc = f"/System/Library/Fonts/{font_name}.ttc"
    if os.path.exists(mac_ttc):
        return f"fontfile={mac_ttc}"
    # Fallback: let FFmpeg find it via fontconfig
    return f"font='{font_name}'"


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def declip_text_overlay(
        input_file: str,
        text: str,
        position: str = "bottom",
        font_size: int = 48,
        font_color: str = "white",
        bg_color: str = "",
        start: float = 0,
        duration: float = 0,
        font: str = "Arial",
        shadow_color: str = "",
        shadow_x: int = 0,
        shadow_y: int = 0,
        outline_width: int = 0,
        outline_color: str = "black",
        output_path: str | None = None,
    ) -> str:
        """Burn a text overlay onto a video. Great for titles, lower thirds, captions.

        Args:
            input_file: Path to input video
            text: Text to display (supports \\n for line breaks)
            position: Placement — top, center, bottom, top-left, top-right, bottom-left, bottom-right, or custom "x:y" in pixels
            font_size: Font size in pixels
            font_color: Font color name or hex (white, yellow, #FF0000)
            bg_color: Background box color (empty = no background)
            start: When to show text (seconds from clip start)
            duration: How long to show (0 = entire clip)
            font: Font family name
            shadow_color: Drop shadow color (empty = no shadow). e.g. "black", "#333333"
            shadow_x: Shadow X offset in pixels (positive = right)
            shadow_y: Shadow Y offset in pixels (positive = down)
            outline_width: Text outline/border width in pixels (0 = no outline)
            outline_color: Outline color (default black)
            output_path: Output file path
        """
        if not Path(input_file).exists():
            return f"Error: {input_file} not found"

        out = _output_path(input_file, output_path, "_text")

        pos_map = {
            "top": "x=(w-text_w)/2:y=50",
            "center": "x=(w-text_w)/2:y=(h-text_h)/2",
            "bottom": "x=(w-text_w)/2:y=h-text_h-50",
            "top-left": "x=50:y=50",
            "top-right": "x=w-text_w-50:y=50",
            "bottom-left": "x=50:y=h-text_h-50",
            "bottom-right": "x=w-text_w-50:y=h-text_h-50",
        }
        if position in pos_map:
            pos_str = pos_map[position]
        elif ":" in position:
            parts = position.split(":")
            pos_str = f"x={parts[0]}:y={parts[1]}"
        else:
            pos_str = pos_map["bottom"]

        escaped = _escape_drawtext(text)
        font_arg = _find_font(font)

        drawtext = f"drawtext=text='{escaped}':{font_arg}:fontsize={font_size}:fontcolor={font_color}:{pos_str}"

        if bg_color:
            drawtext += f":box=1:boxcolor={bg_color}@0.7:boxborderw=10"

        if shadow_color:
            sx = shadow_x if shadow_x else 2
            sy = shadow_y if shadow_y else 2
            drawtext += f":shadowcolor={shadow_color}:shadowx={sx}:shadowy={sy}"

        if outline_width > 0:
            drawtext += f":borderw={outline_width}:bordercolor={outline_color}"

        if duration > 0:
            end_time = start + duration
            drawtext += f":enable='between(t,{start},{end_time})'"
        elif start > 0:
            drawtext += f":enable='gte(t,{start})'"

        cmd = ["ffmpeg", "-y", "-i", input_file, "-vf", drawtext,
               "-c:a", "copy", out]

        ok, err = _run_ffmpeg(cmd)
        if not ok:
            return err
        return f"Text overlay added: {_file_info(out)}"

    @mcp.tool()
    def declip_image_overlay(
        input_file: str,
        image_path: str,
        position: str = "top-right",
        scale: float = 0.15,
        opacity: float = 0.8,
        start: float = 0,
        duration: float = 0,
        output_path: str | None = None,
    ) -> str:
        """Overlay an image (logo, watermark, PIP frame) onto a video.

        Args:
            input_file: Path to input video
            image_path: Path to overlay image (PNG with transparency recommended)
            position: top-left, top-right, bottom-left, bottom-right, center, or "x:y" in pixels
            scale: Image size relative to main video width (0.0-1.0)
            opacity: Transparency (0.0-1.0)
            start: When to show overlay (seconds)
            duration: How long to show (0 = entire clip)
            output_path: Output file path
        """
        if not Path(input_file).exists():
            return f"Error: {input_file} not found"
        if not Path(image_path).exists():
            return f"Error: {image_path} not found"

        out = _output_path(input_file, output_path, "_overlay")

        pos_map = {
            "top-left": "x=20:y=20",
            "top-right": "x=W-w-20:y=20",
            "bottom-left": "x=20:y=H-h-20",
            "bottom-right": "x=W-w-20:y=H-h-20",
            "center": "x=(W-w)/2:y=(H-h)/2",
        }
        if position in pos_map:
            pos_str = pos_map[position]
        elif ":" in position:
            parts = position.split(":")
            pos_str = f"x={parts[0]}:y={parts[1]}"
        else:
            pos_str = pos_map["top-right"]

        # Scale overlay relative to main video width (W), not overlay's own width
        scale_filter = f"[1:v]scale='trunc(main_w*{scale}/2)*2:-2',format=rgba,colorchannelmixer=aa={opacity}[ovr]"
        overlay_str = f"{scale_filter};[0:v][ovr]overlay={pos_str}"

        if duration > 0:
            end_time = start + duration
            overlay_str += f":enable='between(t,{start},{end_time})'"
        elif start > 0:
            overlay_str += f":enable='gte(t,{start})'"

        cmd = ["ffmpeg", "-y", "-i", input_file, "-i", image_path,
               "-filter_complex", overlay_str,
               "-c:a", "copy", out]

        ok, err = _run_ffmpeg(cmd)
        if not ok:
            return err
        return f"Image overlay added: {_file_info(out)}"

    @mcp.tool()
    def declip_transition(
        file_a: str,
        file_b: str,
        transition: str = "dissolve",
        duration: float = 1.0,
        output_path: str = "transition_output.mp4",
    ) -> str:
        """Apply a transition between two video clips.

        Args:
            file_a: First video clip
            file_b: Second video clip
            transition: Type — dissolve, fadeblack, fadewhite, wipeleft, wiperight, wipeup, wipedown, slideleft, slideright, slideup, slidedown, circleopen, circleclose, circlecrop, rectcrop, distance, smoothleft, smoothright, smoothup, smoothdown, horzopen, horzclose, vertopen, vertclose, diagtl, diagtr, diagbl, diagbr, hlslice, hrslice, vuslice, vdslice, radial, zoomin, squeezeh, squeezev, hlwind, hrwind, vuwind, vdwind, coverleft, coverright, coverup, coverdown, revealleft, revealright, revealup, revealdown, pixelize, fadegrays
            duration: Transition duration in seconds
            output_path: Output file path
        """
        for f in [file_a, file_b]:
            if not Path(f).exists():
                return f"Error: {f} not found"

        from declip.probe import probe
        try:
            info_a = probe(file_a)
            offset = max(0, info_a.duration - duration)
        except Exception as e:
            return f"Error probing {file_a}: {e}"

        # All FFmpeg xfade transition types
        XFADE_TYPES = {
            "dissolve", "fade", "fadeblack", "fadewhite", "fadegrays",
            "wipeleft", "wiperight", "wipeup", "wipedown",
            "slideleft", "slideright", "slideup", "slidedown",
            "smoothleft", "smoothright", "smoothup", "smoothdown",
            "circleopen", "circleclose", "circlecrop", "rectcrop",
            "horzopen", "horzclose", "vertopen", "vertclose",
            "diagtl", "diagtr", "diagbl", "diagbr",
            "hlslice", "hrslice", "vuslice", "vdslice",
            "radial", "zoomin", "distance", "pixelize",
            "squeezeh", "squeezev",
            "hlwind", "hrwind", "vuwind", "vdwind",
            "coverleft", "coverright", "coverup", "coverdown",
            "revealleft", "revealright", "revealup", "revealdown",
        }

        name_map = {
            "dissolve": "fade",
            "fadeblack": "fadeblack",
            "fadewhite": "fadewhite",
        }
        xfade_name = name_map.get(transition, transition)

        if xfade_name not in XFADE_TYPES:
            return f"Error: unknown transition '{transition}'. Use one of: {', '.join(sorted(XFADE_TYPES))}"

        # Try with audio crossfade first
        filter_str = f"[0:v][1:v]xfade=transition={xfade_name}:duration={duration}:offset={offset}[v];[0:a][1:a]acrossfade=d={duration}[a]"
        cmd = ["ffmpeg", "-y", "-i", file_a, "-i", file_b,
               "-filter_complex", filter_str,
               "-map", "[v]", "-map", "[a]",
               output_path]

        ok, err = _run_ffmpeg(cmd)
        if not ok:
            # Retry video-only if audio crossfade fails
            filter_str = f"[0:v][1:v]xfade=transition={xfade_name}:duration={duration}:offset={offset}"
            cmd = ["ffmpeg", "-y", "-i", file_a, "-i", file_b,
                   "-filter_complex", filter_str, "-an", output_path]
            ok, err = _run_ffmpeg(cmd)
            if not ok:
                return err
        return f"Transition ({transition}, {duration}s): {_file_info(output_path)}"

    @mcp.tool()
    def declip_speed(
        input_file: str,
        speed: float = 2.0,
        interpolate: bool = False,
        output_path: str | None = None,
    ) -> str:
        """Change video playback speed. <1.0 = slow motion, >1.0 = fast forward.

        With interpolate=True, uses optical-flow frame interpolation (minterpolate)
        for much smoother slow motion instead of frame duplication. Very slow to
        encode but dramatically better quality for slow-mo. Best with speed < 1.0.

        Args:
            input_file: Path to input video
            speed: Speed multiplier (0.25 = quarter speed, 2.0 = double speed)
            interpolate: Use optical-flow interpolation for smooth slow-mo (much slower encoding)
            output_path: Output file path
        """
        from declip.ops import speed as _speed
        ok, msg = _speed(input_file, speed, interpolate, output_path)
        return msg

    @mcp.tool()
    def declip_color(
        input_file: str,
        brightness: float = 0.0,
        contrast: float = 1.0,
        saturation: float = 1.0,
        greyscale: bool = False,
        temperature: float = 0,
        shadows_r: float = 0, shadows_g: float = 0, shadows_b: float = 0,
        midtones_r: float = 0, midtones_g: float = 0, midtones_b: float = 0,
        highlights_r: float = 0, highlights_g: float = 0, highlights_b: float = 0,
        auto_levels: bool = False,
        output_path: str | None = None,
    ) -> str:
        """All-in-one color tool — brightness, contrast, saturation, greyscale, white balance, color balance, and auto-levels.

        Simple adjustments: use brightness, contrast, saturation, or greyscale.
        Advanced grading: use temperature, shadow/midtone/highlight RGB, or auto_levels.
        Can combine both in one call (basic applied first, then grading).

        Args:
            input_file: Path to input video
            brightness: Brightness adjustment (-1.0 to 1.0, 0 = no change)
            contrast: Contrast multiplier (0.5 to 3.0, 1.0 = no change)
            saturation: Saturation multiplier (0.0 to 3.0, 1.0 = no change)
            greyscale: Convert to black and white
            temperature: White balance shift (-1.0 cool/blue to 1.0 warm/orange, 0 = neutral)
            shadows_r: Shadow red (-1.0 to 1.0)
            shadows_g: Shadow green (-1.0 to 1.0)
            shadows_b: Shadow blue (-1.0 to 1.0)
            midtones_r: Midtone red (-1.0 to 1.0)
            midtones_g: Midtone green (-1.0 to 1.0)
            midtones_b: Midtone blue (-1.0 to 1.0)
            highlights_r: Highlight red (-1.0 to 1.0)
            highlights_g: Highlight green (-1.0 to 1.0)
            highlights_b: Highlight blue (-1.0 to 1.0)
            auto_levels: Auto-normalize color levels (stretch histogram)
            output_path: Output file path
        """
        if not Path(input_file).exists():
            return f"Error: {input_file} not found"

        filters = []

        # Basic adjustments (eq filter)
        has_basic = greyscale or brightness != 0 or contrast != 1.0 or saturation != 1.0
        if greyscale:
            filters.append("hue=s=0")
        elif has_basic:
            filters.append(f"eq=brightness={brightness}:contrast={contrast}:saturation={saturation}")

        # Advanced grading (colorbalance, temperature, normalize)
        has_balance = any([shadows_r, shadows_g, shadows_b,
                          midtones_r, midtones_g, midtones_b,
                          highlights_r, highlights_g, highlights_b])
        has_advanced = has_balance or temperature != 0 or auto_levels

        if has_advanced:
            from declip.ops import color_grade as _color_grade
            ok, msg = _color_grade(
                input_file, temperature,
                shadows_r, shadows_g, shadows_b,
                midtones_r, midtones_g, midtones_b,
                highlights_r, highlights_g, highlights_b,
                auto_levels, output_path if not has_basic else None,
            )
            if not has_basic:
                return msg
            # If both basic and advanced, need to chain: apply basic first
            # (advanced already handles its own output)

        if not has_basic and not has_advanced:
            return "Error: provide at least one color parameter"

        if has_basic and not has_advanced:
            out = _output_path(input_file, output_path, "_color")
            cmd = ["ffmpeg", "-y", "-i", input_file, "-vf", ",".join(filters),
                   "-c:a", "copy", out]
            ok, err = _run_ffmpeg(cmd)
            if not ok:
                return err
            return f"Color adjusted: {_file_info(out)}"

        # Both basic + advanced: chain filters
        out = _output_path(input_file, output_path, "_color")
        # Build combined filter
        if has_balance:
            filters.append(
                f"colorbalance="
                f"rs={shadows_r}:gs={shadows_g}:bs={shadows_b}:"
                f"rm={midtones_r}:gm={midtones_g}:bm={midtones_b}:"
                f"rh={highlights_r}:gh={highlights_g}:bh={highlights_b}"
            )
        if temperature != 0:
            kelvin = int(6500 - temperature * 4500)
            kelvin = max(1000, min(40000, kelvin))
            filters.append(f"colortemperature=temperature={kelvin}")
        if auto_levels:
            filters.append("normalize")

        cmd = ["ffmpeg", "-y", "-i", input_file, "-vf", ",".join(filters),
               "-c:a", "copy", out]
        ok, err = _run_ffmpeg(cmd)
        if not ok:
            return err
        return f"Color adjusted: {_file_info(out)}"

    @mcp.tool()
    def declip_crop_resize(
        input_file: str,
        width: int = 0,
        height: int = 0,
        crop: str = "",
        aspect: str = "",
        pad_color: str = "black",
        output_path: str | None = None,
    ) -> str:
        """Crop, resize, or reframe video for different aspect ratios.

        Args:
            input_file: Path to input video
            width: Target width (0 = auto from height)
            height: Target height (0 = auto from width)
            crop: Crop region as "w:h:x:y" in pixels (applied before resize)
            aspect: Target aspect ratio — "16:9", "9:16", "1:1", "4:3". Auto-pads with letterbox/pillarbox
            pad_color: Padding color for aspect ratio conversion
            output_path: Output file path
        """
        if not Path(input_file).exists():
            return f"Error: {input_file} not found"

        out = _output_path(input_file, output_path, "_resized")
        filters = []

        if crop:
            filters.append(f"crop={crop}")

        if aspect:
            try:
                aw, ah = [int(x) for x in aspect.split(":")]
            except ValueError:
                return f"Error: invalid aspect ratio '{aspect}'. Use format like '16:9'"

            if width > 0:
                tw, th = width, int(width * ah / aw)
            elif height > 0:
                th, tw = height, int(height * aw / ah)
            else:
                tw = 1920
                th = int(tw * ah / aw)

            # Ensure even dimensions (required by most codecs)
            tw = tw + (tw % 2)
            th = th + (th % 2)

            filters.append(f"scale={tw}:{th}:force_original_aspect_ratio=decrease")
            filters.append(f"pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:color={pad_color}")
        elif width > 0 or height > 0:
            w = width if width > 0 else -2
            h = height if height > 0 else -2
            filters.append(f"scale={w}:{h}")

        if not filters:
            return "Error: provide width/height, crop, or aspect ratio"

        vf = ",".join(filters)
        cmd = ["ffmpeg", "-y", "-i", input_file, "-vf", vf,
               "-c:a", "copy", out]

        ok, err = _run_ffmpeg(cmd)
        if not ok:
            return err
        return f"Resized: {_file_info(out)}"

    @mcp.tool()
    def declip_subtitle_burn(
        input_file: str,
        subtitle_path: str,
        font_size: int = 24,
        font_color: str = "white",
        outline_width: int = 1,
        shadow_offset: int = 1,
        margin_v: int = 30,
        alignment: int = 2,
        output_path: str | None = None,
    ) -> str:
        """Burn subtitles into a video (hardcoded, always visible). Auto-detects ASS vs SRT format.

        Args:
            input_file: Path to input video
            subtitle_path: Path to .srt or .ass subtitle file
            font_size: Subtitle font size
            font_color: Subtitle color (white, yellow, red, green, cyan, or ASS hex like &H00FFFFFF)
            outline_width: Text outline width in pixels (0 = no outline)
            shadow_offset: Shadow offset in pixels (0 = no shadow)
            margin_v: Vertical margin from bottom in pixels
            alignment: ASS alignment (1=bottom-left, 2=bottom-center, 3=bottom-right, 5=top-left, 6=top-center, 7=top-right, 9=mid-left, 10=mid-center, 11=mid-right)
            output_path: Output file path
        """
        if not Path(input_file).exists():
            return f"Error: {input_file} not found"
        if not Path(subtitle_path).exists():
            return f"Error: {subtitle_path} not found"

        out = _output_path(input_file, output_path, "_subtitled")

        # Auto-detect subtitle format
        sub_ext = Path(subtitle_path).suffix.lower()
        escaped_sub = subtitle_path.replace("\\", "\\\\").replace(":", "\\:").replace("'", "'\\''")

        if sub_ext == ".ass" or sub_ext == ".ssa":
            # ASS files have their own styling — use ass= filter which respects it
            vf = f"ass='{escaped_sub}'"
        else:
            # SRT and other formats — use subtitles= with force_style
            color_map = {
                "white": "&H00FFFFFF",
                "yellow": "&H0000FFFF",
                "red": "&H000000FF",
                "green": "&H0000FF00",
                "cyan": "&H00FFFF00",
            }
            ass_color = color_map.get(font_color.lower(), font_color)

            style = (
                f"FontSize={font_size},"
                f"PrimaryColour={ass_color},"
                f"OutlineColour=&H00000000,"
                f"Outline={outline_width},"
                f"Shadow={shadow_offset},"
                f"MarginV={margin_v},"
                f"Alignment={alignment}"
            )
            vf = f"subtitles='{escaped_sub}':force_style='{style}'"

        cmd = ["ffmpeg", "-y", "-i", input_file, "-vf", vf,
               "-c:a", "copy", out]

        ok, err = _run_ffmpeg(cmd)
        if not ok:
            return err
        return f"Subtitles burned in: {_file_info(out)}"

    @mcp.tool()
    def declip_reverse(
        input_file: str,
        audio: bool = True,
        chunk_seconds: int = 10,
        output_path: str | None = None,
    ) -> str:
        """Reverse a video (play backwards).

        For clips >30s, automatically uses chunked processing: splits into
        segments, reverses each, and concatenates in reverse order. This avoids
        loading the entire video into RAM.

        Args:
            input_file: Path to input video
            audio: Also reverse audio (True) or mute (False)
            chunk_seconds: Segment size for chunked reverse (default 10s)
            output_path: Output file path
        """
        from declip.ops import reverse as _reverse
        ok, msg = _reverse(input_file, audio, chunk_seconds, output_path)
        return msg

    @mcp.tool()
    def declip_gif(
        input_file: str,
        start: float = 0,
        duration: float = 5,
        width: int = 480,
        fps: int = 15,
        output_path: str | None = None,
    ) -> str:
        """Convert a video segment to an animated GIF.

        Args:
            input_file: Path to input video
            start: Start time in seconds
            duration: Duration in seconds
            width: Output width in pixels (height auto-scaled)
            fps: Frames per second (lower = smaller file)
            output_path: Output GIF path
        """
        if not Path(input_file).exists():
            return f"Error: {input_file} not found"

        out = _output_path(input_file, output_path, ".gif")

        # Two-pass for better quality: generate palette then apply it
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            palette = f.name

        filters = f"fps={fps},scale={width}:-1:flags=lanczos"

        try:
            cmd1 = ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration),
                    "-i", input_file,
                    "-vf", f"{filters},palettegen", palette]

            ok, err = _run_ffmpeg(cmd1)
            if not ok:
                return f"Palette generation failed: {err}"

            cmd2 = ["ffmpeg", "-y", "-ss", str(start), "-t", str(duration),
                    "-i", input_file, "-i", palette,
                    "-filter_complex", f"{filters}[x];[x][1:v]paletteuse", out]

            ok, err = _run_ffmpeg(cmd2)
            if not ok:
                return err
        finally:
            try:
                os.unlink(palette)
            except OSError:
                pass

        return f"GIF created: {_file_info(out)}"

    @mcp.tool()
    def declip_split_screen(
        files: list[str],
        layout: str = "horizontal",
        width: int = 1920,
        height: int = 1080,
        border: int = 0,
        border_color: str = "black",
        audio_from: int = 0,
        pip_scale: float = 0.3,
        pip_position: str = "bottom-right",
        output_path: str = "splitscreen.mp4",
    ) -> str:
        """Tile 2-4 videos side by side, in a grid, or picture-in-picture.

        Args:
            files: List of 2-4 video file paths (for PIP: first is main, second is overlay)
            layout: horizontal (side by side), vertical (stacked), grid (2x2), or pip (picture-in-picture)
            width: Total output width in pixels
            height: Total output height in pixels
            border: Border width between panels in pixels (0 = no border)
            border_color: Border/padding color (black, white, gray, or hex)
            audio_from: Which input's audio to use (0-based index, -1 = mix all, default 0 = first)
            pip_scale: PIP overlay size relative to main (0.1-0.5, default 0.3). Only for pip layout.
            pip_position: PIP overlay position: top-left, top-right, bottom-left, bottom-right. Only for pip layout.
            output_path: Output file path
        """
        n = len(files)
        if n < 2 or n > 4:
            return "Error: provide 2-4 video files"

        for f in files:
            if not Path(f).exists():
                return f"Error: {f} not found"

        inputs = []
        for f in files:
            inputs.extend(["-i", f])

        # PIP layout: main video + small overlay
        if layout == "pip":
            if n != 2:
                return "Error: pip layout needs exactly 2 videos"

            pip_pos_map = {
                "top-left": f"x={border + 20}:y={border + 20}",
                "top-right": f"x=W-w-{border + 20}:y={border + 20}",
                "bottom-left": f"x={border + 20}:y=H-h-{border + 20}",
                "bottom-right": f"x=W-w-{border + 20}:y=H-h-{border + 20}",
            }
            pos = pip_pos_map.get(pip_position, pip_pos_map["bottom-right"])

            fc = (
                f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
                f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={border_color}[main];"
                f"[1:v]scale='trunc(main_w*{pip_scale}/2)*2:-2'[pip];"
                f"[main][pip]overlay={pos}"
            )

            # Audio selection
            audio_args = []
            if audio_from == -1:
                fc += ";[0:a][1:a]amix=inputs=2:normalize=0"
            else:
                idx = max(0, min(audio_from, 1))
                audio_args = ["-map", f"{idx}:a?"]

            cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", fc]
            if audio_args:
                cmd += audio_args
            else:
                # amix output is already in filter graph
                pass
            cmd.append(output_path)

            ok, err = _run_ffmpeg(cmd)
            if not ok:
                return err
            return f"PIP ({pip_position}, {pip_scale:.0%}): {_file_info(output_path)}"

        # Tiled layouts: horizontal, vertical, grid
        # Account for border padding between cells
        if layout == "horizontal":
            total_border = border * (n - 1)
            cw = (width - total_border) // n
            ch = height
            scales = ";".join(
                f"[{i}:v]scale={cw}:{ch}:force_original_aspect_ratio=decrease,"
                f"pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2:color={border_color}[v{i}]"
                for i in range(n)
            )
            labels = "".join(f"[v{i}]" for i in range(n))
            stack = f"{labels}hstack=inputs={n}"
            if border > 0:
                # Add border by padding between cells — pad the output
                fc = f"{scales};{stack}[stacked];[stacked]pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={border_color}"
            else:
                fc = f"{scales};{stack}"
        elif layout == "vertical":
            total_border = border * (n - 1)
            cw = width
            ch = (height - total_border) // n
            scales = ";".join(
                f"[{i}:v]scale={cw}:{ch}:force_original_aspect_ratio=decrease,"
                f"pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2:color={border_color}[v{i}]"
                for i in range(n)
            )
            labels = "".join(f"[v{i}]" for i in range(n))
            stack = f"{labels}vstack=inputs={n}"
            if border > 0:
                fc = f"{scales};{stack}[stacked];[stacked]pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={border_color}"
            else:
                fc = f"{scales};{stack}"
        elif layout == "grid":
            if n < 4:
                return "Error: grid layout needs exactly 4 videos"
            total_border_h = border
            total_border_v = border
            cw = (width - total_border_h) // 2
            ch = (height - total_border_v) // 2
            scales = ";".join(
                f"[{i}:v]scale={cw}:{ch}:force_original_aspect_ratio=decrease,"
                f"pad={cw}:{ch}:(ow-iw)/2:(oh-ih)/2:color={border_color}[v{i}]"
                for i in range(4)
            )
            stack = f"[v0][v1]hstack[top];[v2][v3]hstack[bot];[top][bot]vstack"
            if border > 0:
                fc = f"{scales};{stack}[stacked];[stacked]pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color={border_color}"
            else:
                fc = f"{scales};{stack}"
        else:
            return f"Error: unknown layout '{layout}'. Use: horizontal, vertical, grid, pip"

        # Audio handling
        audio_args = []
        if audio_from == -1:
            # Mix all audio tracks
            amix_labels = "".join(f"[{i}:a]" for i in range(n))
            fc += f";{amix_labels}amix=inputs={n}:normalize=0[aout]"
            audio_args = ["-map", "[aout]"]
        elif 0 <= audio_from < n:
            audio_args = ["-map", f"{audio_from}:a?"]
        else:
            audio_args = ["-an"]

        cmd = ["ffmpeg", "-y"] + inputs + ["-filter_complex", fc]
        cmd += audio_args
        cmd.append(output_path)

        ok, err = _run_ffmpeg(cmd)
        if not ok:
            return err
        return f"Split screen ({layout}, {n} videos): {_file_info(output_path)}"

    @mcp.tool()
    def declip_freeze_frame(
        input_file: str,
        timestamp: float,
        hold_duration: float = 3.0,
        fps: int = 0,
        output_path: str | None = None,
    ) -> str:
        """Extract a frame and hold it as a still video for a given duration.

        Args:
            input_file: Path to input video
            timestamp: Time in seconds to freeze
            hold_duration: How long to hold the frame in seconds
            fps: Output FPS (0 = match source)
            output_path: Output file path
        """
        if not Path(input_file).exists():
            return f"Error: {input_file} not found"

        out = _output_path(input_file, output_path, "_freeze")

        # Probe for actual FPS if not specified
        if fps == 0:
            from declip.probe import probe
            try:
                info = probe(input_file)
                fps = round(info.fps) if info.fps else 30
            except Exception:
                fps = 30

        loop_count = int(hold_duration * fps)

        cmd = ["ffmpeg", "-y", "-ss", str(timestamp), "-i", input_file,
               "-frames:v", "1",
               "-vf", f"loop={loop_count}:1:0,fps={fps}",
               "-t", str(hold_duration), "-an", out]

        ok, err = _run_ffmpeg(cmd)
        if not ok:
            return err
        return f"Freeze frame at {timestamp}s, held {hold_duration}s @ {fps}fps: {_file_info(out)}"

    @mcp.tool()
    def declip_stabilize(
        input_file: str,
        shakiness: int = 5,
        smoothing: int = 10,
        zoom: float = 0,
        tripod: bool = False,
        output_path: str | None = None,
    ) -> str:
        """Stabilize shaky video using FFmpeg's vidstab filter (two-pass).

        Args:
            input_file: Path to input video
            shakiness: Detection sensitivity 1-10 (higher = more correction)
            smoothing: Smoothing strength in frames (default 10, higher = smoother but more crop)
            zoom: Zoom percentage to hide black borders (0 = auto, negative zooms out)
            tripod: Lock to a single reference frame (best for fixed-camera footage)
            output_path: Output file path
        """
        from declip.ops import stabilize as _stabilize
        ok, msg = _stabilize(input_file, shakiness, smoothing, zoom, tripod, output_path)
        return msg

    @mcp.tool()
    def declip_audio_mix(
        video_file: str,
        audio_file: str,
        video_volume: float = 1.0,
        audio_volume: float = 0.5,
        audio_start: float = 0,
        replace: bool = False,
        output_path: str | None = None,
    ) -> str:
        """Mix an audio track into a video — add background music, voiceover, sound effects.

        Args:
            video_file: Path to input video
            audio_file: Path to audio file to mix in
            video_volume: Original video audio volume (0.0-2.0)
            audio_volume: New audio track volume (0.0-2.0)
            audio_start: Delay before new audio starts (seconds)
            replace: Replace original audio entirely instead of mixing
            output_path: Output file path
        """
        for f in [video_file, audio_file]:
            if not Path(f).exists():
                return f"Error: {f} not found"

        out = _output_path(video_file, output_path, "_mixed")

        if replace:
            cmd = ["ffmpeg", "-y", "-i", video_file, "-i", audio_file,
                   "-map", "0:v", "-map", "1:a",
                   "-c:v", "copy",
                   "-af", f"volume={audio_volume}",
                   "-shortest", out]
        else:
            delay_ms = int(audio_start * 1000)
            fc = (f"[0:a]volume={video_volume}[va];"
                  f"[1:a]adelay={delay_ms}|{delay_ms},volume={audio_volume}[aa];"
                  f"[va][aa]amix=inputs=2:duration=first:dropout_transition=2:normalize=0")
            cmd = ["ffmpeg", "-y", "-i", video_file, "-i", audio_file,
                   "-filter_complex", fc,
                   "-map", "0:v", "-c:v", "copy", out]

        ok, err = _run_ffmpeg(cmd)
        if not ok:
            return err
        return f"Audio mixed: {_file_info(out)}"

    @mcp.tool()
    def declip_loop(
        input_file: str,
        count: int = 3,
        output_path: str | None = None,
    ) -> str:
        """Loop a video clip N times.

        Args:
            input_file: Path to input video
            count: Number of times to loop (total plays)
            output_path: Output file path
        """
        if not Path(input_file).exists():
            return f"Error: {input_file} not found"
        if count < 1:
            return "Error: count must be >= 1"

        out = _output_path(input_file, output_path, f"_loop{count}")

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            for _ in range(count):
                f.write(f"file '{Path(input_file).resolve()}'\n")
            listfile = f.name

        try:
            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                   "-i", listfile, "-c", "copy", out]
            ok, err = _run_ffmpeg(cmd)
        finally:
            os.unlink(listfile)

        if not ok:
            return err
        return f"Looped {count}x: {_file_info(out)}"

    @mcp.tool()
    def declip_fade(
        input_file: str,
        fade_in: float = 0,
        fade_out: float = 0,
        color: str = "black",
        output_path: str | None = None,
    ) -> str:
        """Add fade in/out to a video.

        Args:
            input_file: Path to input video
            fade_in: Fade-in duration in seconds (0 = no fade in)
            fade_out: Fade-out duration in seconds (0 = no fade out)
            color: Fade color — black or white
            output_path: Output file path
        """
        if fade_in <= 0 and fade_out <= 0:
            return "Error: provide fade_in and/or fade_out duration"
        if not Path(input_file).exists():
            return f"Error: {input_file} not found"

        out = _output_path(input_file, output_path, "_faded")

        from declip.probe import probe
        try:
            info = probe(input_file)
            dur = info.duration
        except Exception as e:
            return f"Error probing: {e}"

        vfilters = []
        afilters = []

        if fade_in > 0:
            vfilters.append(f"fade=t=in:st=0:d={fade_in}:color={color}")
            afilters.append(f"afade=t=in:st=0:d={fade_in}")
        if fade_out > 0:
            fade_start = max(0, dur - fade_out)
            vfilters.append(f"fade=t=out:st={fade_start}:d={fade_out}:color={color}")
            afilters.append(f"afade=t=out:st={fade_start}:d={fade_out}")

        cmd = ["ffmpeg", "-y", "-i", input_file]
        cmd.extend(["-vf", ",".join(vfilters)])
        if afilters:
            cmd.extend(["-af", ",".join(afilters)])
        cmd.append(out)

        ok, err = _run_ffmpeg(cmd)
        if not ok:
            return err
        return f"Fade applied: {_file_info(out)}"

    @mcp.tool()
    def declip_sidechain(
        video_file: str,
        music_file: str,
        threshold: float = 0.02,
        ratio: float = 8.0,
        attack: float = 200,
        release: float = 1000,
        output_path: str | None = None,
    ) -> str:
        """Auto-duck music under speech using sidechain compression.

        The speech audio (from video) controls a compressor on the music track.
        When speech is detected, the music volume automatically drops. Much more
        natural than silence-detection-based volume keyframes.

        Args:
            video_file: Path to video with speech audio (sidechain source)
            music_file: Path to music audio file (will be ducked)
            threshold: Compression threshold (0.0-1.0, lower = more ducking)
            ratio: Compression ratio (higher = harder ducking, 8-20 recommended)
            attack: Attack time in ms (how fast music ducks when speech starts)
            release: Release time in ms (how fast music returns when speech stops)
            output_path: Output file path (video with ducked music mixed in)
        """
        from declip.ops import sidechain as _sidechain
        ok, msg = _sidechain(video_file, music_file, threshold, ratio, attack, release, output_path)
        return msg

    @mcp.tool()
    def declip_denoise(
        input_file: str,
        strength: str = "medium",
        method: str = "fft",
        output_path: str | None = None,
    ) -> str:
        """Reduce audio noise in a video or audio file.

        Good as a pre-processing step before voiceover mixing or transcription.

        Args:
            input_file: Path to input video or audio file
            strength: Noise reduction strength — light, medium, or heavy
            method: Algorithm — fft (FFT-based, better for stationary noise) or nlmeans (non-local means, better for varying noise)
            output_path: Output file path
        """
        from declip.ops import denoise as _denoise
        ok, msg = _denoise(input_file, strength, method, output_path)
        return msg

    # declip_loudnorm removed — merged into declip_loudness (normalize_to param)
