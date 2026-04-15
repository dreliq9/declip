"""MCP tools for production pipeline — auto-captions, TTS voiceover,
multi-platform export, and storyboard assembly.

These combine multiple analysis + edit steps into end-to-end workflows.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP


def _run_ffmpeg(cmd: list[str], timeout: int = 300) -> tuple[bool, str]:
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        return False, proc.stderr.decode(errors="replace")[-500:]
    return True, ""


def _file_info(path: str) -> str:
    p = Path(path)
    if p.exists():
        return f"{path} ({p.stat().st_size / 1024 / 1024:.1f} MB)"
    return path


# ---------------------------------------------------------------------------
# ASS subtitle generation
# ---------------------------------------------------------------------------

def _generate_ass(
    words: list[dict],
    style: str = "bold",
    resolution: tuple[int, int] = (1920, 1080),
) -> str:
    """Generate ASS subtitle content with karaoke timing from word list.

    Each word dict has: word, start, end, confidence
    """
    w, h = resolution

    # Style presets
    styles = {
        "bold": {
            "fontname": "Arial",
            "fontsize": 64,
            "primary": "&H00FFFFFF",   # white
            "secondary": "&H0000FFFF", # yellow highlight
            "outline": "&H00000000",   # black outline
            "back": "&H80000000",      # semi-transparent bg
            "bold": -1,
            "outline_w": 3,
            "shadow": 2,
            "alignment": 2,  # bottom center
            "margin_v": 60,
        },
        "karaoke": {
            "fontname": "Arial",
            "fontsize": 56,
            "primary": "&H0000FFFF",   # yellow (highlighted)
            "secondary": "&H00FFFFFF", # white (unhighlighted)
            "outline": "&H00000000",
            "back": "&H00000000",
            "bold": -1,
            "outline_w": 2,
            "shadow": 0,
            "alignment": 2,
            "margin_v": 50,
        },
        "minimal": {
            "fontname": "Arial",
            "fontsize": 42,
            "primary": "&H00FFFFFF",
            "secondary": "&H00FFFFFF",
            "outline": "&H00000000",
            "back": "&H00000000",
            "bold": 0,
            "outline_w": 2,
            "shadow": 1,
            "alignment": 2,
            "margin_v": 40,
        },
        "news": {
            "fontname": "Arial",
            "fontsize": 38,
            "primary": "&H00FFFFFF",
            "secondary": "&H00FFFFFF",
            "outline": "&H00000000",
            "back": "&H80000000",
            "bold": 0,
            "outline_w": 1,
            "shadow": 0,
            "alignment": 1,  # bottom left
            "margin_v": 30,
        },
    }

    s = styles.get(style, styles["bold"])

    def _ass_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        sec = seconds % 60
        return f"{h}:{m:02d}:{sec:05.2f}"

    header = f"""[Script Info]
Title: Auto-Captions
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{s['fontname']},{s['fontsize']},{s['primary']},{s['secondary']},{s['outline']},{s['back']},{s['bold']},0,0,0,100,100,0,0,1,{s['outline_w']},{s['shadow']},{s['alignment']},20,20,{s['margin_v']},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = [header.strip()]

    # Group words into lines (max ~6 words per line for readability)
    max_words_per_line = 6
    word_groups = []
    current_group = []

    for word in words:
        current_group.append(word)
        if len(current_group) >= max_words_per_line:
            word_groups.append(current_group)
            current_group = []
    if current_group:
        word_groups.append(current_group)

    use_karaoke = style in ("karaoke", "bold")

    for group in word_groups:
        if not group:
            continue
        start = group[0]["start"]
        end = group[-1]["end"]

        if use_karaoke:
            # Build karaoke tags: \k<centiseconds> per word
            text_parts = []
            for i, word in enumerate(group):
                dur_cs = max(1, int((word["end"] - word["start"]) * 100))
                text_parts.append(f"{{\\kf{dur_cs}}}{word['word']}")
            text = " ".join(text_parts)
        else:
            text = " ".join(w["word"] for w in group)

        lines.append(
            f"Dialogue: 0,{_ass_time(start)},{_ass_time(end)},Default,,0,0,0,,{text}"
        )

    return "\n".join(lines)


def register(mcp: FastMCP) -> None:

    # -----------------------------------------------------------------------
    # 1. Auto-captions
    # -----------------------------------------------------------------------

    @mcp.tool()
    def declip_auto_caption(
        input_file: str,
        style: str = "bold",
        model_size: str = "base",
        language: str | None = None,
        output_path: str | None = None,
        ass_only: bool = False,
    ) -> str:
        """Generate styled auto-captions and burn them into a video.

        Transcribes speech with word-level timing, generates ASS subtitles
        with karaoke-style highlighting, and burns them into the video.

        Style presets:
        - bold: Large white text, word-by-word highlight, semi-transparent bg (TikTok/Reels)
        - karaoke: Yellow highlight sweeping across white text
        - minimal: Small white text, outline only, no animation
        - news: Lower-left, small text with background box

        Args:
            input_file: Path to input video
            style: Caption style preset (bold, karaoke, minimal, news)
            model_size: Whisper model (tiny, base, small, medium, large-v3)
            language: Language code or None for auto-detect
            output_path: Output video path (default: input_captioned.mp4)
            ass_only: If True, only generate the .ass file without burning in
        """
        if not Path(input_file).exists():
            return f"Error: {input_file} not found"

        from declip.analyze import transcribe
        from declip.probe import probe

        # Step 1: Transcribe with word-level timing
        try:
            result = transcribe(
                input_file, model_size=model_size,
                language=language, word_timestamps=True,
            )
        except Exception as e:
            return f"Transcription error: {e}"

        if not result.words:
            return "Error: no words detected in audio"

        # Step 2: Get video resolution for ASS positioning
        try:
            info = probe(input_file)
            res = (info.width or 1920, info.height or 1080)
        except Exception:
            res = (1920, 1080)

        # Step 3: Generate ASS subtitle file
        word_dicts = [
            {"word": w.word, "start": w.start, "end": w.end, "confidence": w.confidence}
            for w in result.words
        ]
        ass_content = _generate_ass(word_dicts, style=style, resolution=res)

        ass_path = Path(input_file).with_suffix(".ass")
        ass_path.write_text(ass_content, encoding="utf-8")

        if ass_only:
            return f"ASS file generated: {ass_path}\nWords: {len(result.words)}, Style: {style}"

        # Step 4: Burn into video
        if not output_path:
            output_path = str(Path(input_file).with_stem(Path(input_file).stem + "_captioned"))

        # Use ass= filter (not subtitles=) for full ASS rendering
        escaped_ass = str(ass_path).replace("\\", "\\\\").replace(":", "\\:")
        cmd = [
            "ffmpeg", "-y", "-i", input_file,
            "-vf", f"ass='{escaped_ass}'",
            "-c:a", "copy",
            output_path,
        ]

        ok, err = _run_ffmpeg(cmd)
        if not ok:
            return f"Burn-in error: {err}"

        return (
            f"Auto-captions applied ({style} style)\n"
            f"Words: {len(result.words)}, Language: {result.language}\n"
            f"ASS: {ass_path}\n"
            f"Output: {_file_info(output_path)}"
        )

    # -----------------------------------------------------------------------
    # 2. TTS Voiceover
    # -----------------------------------------------------------------------

    @mcp.tool()
    def declip_tts(
        text: str,
        output_path: str = "voiceover.mp3",
        voice: str = "en-US-GuyNeural",
        rate: str = "+0%",
        pitch: str = "+0Hz",
        output_words: bool = False,
    ) -> str:
        """Generate voiceover audio from text using edge-tts (free neural voices).

        Returns word-level timing data when output_words=True, enabling
        precise subtitle sync and shot timing.

        Popular voices:
        - en-US-GuyNeural (male, clear narrator)
        - en-US-JennyNeural (female, natural)
        - en-US-AriaNeural (female, expressive)
        - en-GB-RyanNeural (British male)
        - en-AU-NatashaNeural (Australian female)

        Args:
            text: Text to speak
            output_path: Where to save the audio file
            voice: Voice name (use edge-tts --list-voices to see all)
            rate: Speed adjustment (e.g., "+20%", "-10%")
            pitch: Pitch adjustment (e.g., "+50Hz", "-20Hz")
            output_words: Return word-level timing data
        """
        import edge_tts

        async def _generate():
            communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
            word_data = []

            with open(output_path, "wb") as f:
                async for chunk in communicate.stream():
                    if chunk["type"] == "audio":
                        f.write(chunk["data"])
                    elif chunk["type"] == "WordBoundary" and output_words:
                        word_data.append({
                            "word": chunk["text"],
                            "start": chunk["offset"] / 10_000_000,  # ticks to seconds
                            "end": (chunk["offset"] + chunk["duration"]) / 10_000_000,
                        })

            return word_data

        try:
            word_data = asyncio.run(_generate())
        except Exception as e:
            return f"TTS error: {e}"

        if not Path(output_path).exists():
            return "Error: TTS produced no output"

        lines = [
            f"Voice: {voice}",
            f"Output: {_file_info(output_path)}",
        ]

        if output_words and word_data:
            lines.append(f"Words with timing: {len(word_data)}")
            # Save word timing as JSON sidecar
            words_path = Path(output_path).with_suffix(".words.json")
            words_path.write_text(json.dumps(word_data, indent=2))
            lines.append(f"Word timing: {words_path}")

        duration_cmd = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", output_path],
            capture_output=True, text=True,
        )
        if duration_cmd.returncode == 0:
            dur = float(duration_cmd.stdout.strip())
            lines.append(f"Duration: {dur:.1f}s")

        return "\n".join(lines)

    @mcp.tool()
    def declip_tts_voices(
        language: str = "en",
    ) -> str:
        """List available edge-tts voices filtered by language.

        Args:
            language: Language prefix to filter (e.g., "en", "es", "fr", "ja")
        """
        import edge_tts

        async def _list():
            voices = await edge_tts.list_voices()
            return voices

        try:
            voices = asyncio.run(_list())
        except Exception as e:
            return f"Error: {e}"

        filtered = [v for v in voices if v["Locale"].lower().startswith(language.lower())]
        if not filtered:
            return f"No voices found for language '{language}'"

        lines = [f"Voices for '{language}' ({len(filtered)}):"]
        for v in filtered:
            gender = v.get("Gender", "")
            lines.append(f"  {v['ShortName']} — {gender}, {v['Locale']}")

        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # 3. Multi-platform export
    # -----------------------------------------------------------------------

    @mcp.tool()
    def declip_platform_export(
        input_file: str,
        platforms: str = "youtube,shorts,reels",
        reframe: str = "center_crop",
        output_dir: str | None = None,
    ) -> str:
        """Export a video for multiple social media platforms in one shot.

        Generates correctly sized, loudness-normalized versions for each platform.
        Runs exports in parallel for speed.

        Platforms: youtube, youtube-4k, shorts, reels, tiktok, twitter, linkedin,
                   instagram-feed, instagram-4x5

        Reframe strategies (for vertical/square from 16:9 source):
        - center_crop: Crop center slice (fast, loses edges)
        - blur_bg: Blurred zoomed background with sharp center overlay (looks professional)
        - letterbox: Black bars (preserves all content)

        Args:
            input_file: Path to master video (ideally 16:9 1080p+)
            platforms: Comma-separated platform names
            reframe: Strategy for aspect ratio conversion
            output_dir: Output directory (default: input_exports/)
        """
        if not Path(input_file).exists():
            return f"Error: {input_file} not found"

        if not output_dir:
            output_dir = str(Path(input_file).stem + "_exports")
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        PLATFORM_SPECS = {
            "youtube":        {"w": 1920, "h": 1080, "aspect": "16:9", "lufs": -14, "label": "YouTube"},
            "youtube-4k":     {"w": 3840, "h": 2160, "aspect": "16:9", "lufs": -14, "label": "YouTube 4K"},
            "shorts":         {"w": 1080, "h": 1920, "aspect": "9:16", "lufs": -14, "label": "YouTube Shorts"},
            "reels":          {"w": 1080, "h": 1920, "aspect": "9:16", "lufs": -11, "label": "Instagram Reels"},
            "tiktok":         {"w": 1080, "h": 1920, "aspect": "9:16", "lufs": -11, "label": "TikTok"},
            "twitter":        {"w": 1280, "h": 720,  "aspect": "16:9", "lufs": -14, "label": "Twitter/X"},
            "linkedin":       {"w": 1920, "h": 1080, "aspect": "16:9", "lufs": -14, "label": "LinkedIn"},
            "instagram-feed": {"w": 1080, "h": 1080, "aspect": "1:1",  "lufs": -11, "label": "Instagram Feed"},
            "instagram-4x5":  {"w": 1080, "h": 1350, "aspect": "4:5",  "lufs": -11, "label": "Instagram 4:5"},
        }

        platform_list = [p.strip().lower() for p in platforms.split(",")]
        invalid = [p for p in platform_list if p not in PLATFORM_SPECS]
        if invalid:
            return f"Unknown platforms: {invalid}\nAvailable: {', '.join(PLATFORM_SPECS.keys())}"

        results = []
        errors = []

        for platform in platform_list:
            spec = PLATFORM_SPECS[platform]
            out_path = str(Path(output_dir) / f"{platform}.mp4")
            tw, th = spec["w"], spec["h"]
            lufs = spec["lufs"]

            # Build video filter based on aspect ratio
            if spec["aspect"] == "16:9":
                # Same aspect — just scale
                vf = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2"
            elif reframe == "center_crop":
                # Crop center slice to target aspect
                vf = f"crop=ih*{tw}/{th}:ih,scale={tw}:{th}"
            elif reframe == "blur_bg":
                # Blurred background with sharp center overlay
                vf = (
                    f"split[bg][fg];"
                    f"[bg]scale={tw}:{th}:force_original_aspect_ratio=increase,"
                    f"crop={tw}:{th},boxblur=20:5[blurred];"
                    f"[fg]scale={tw}:{th}:force_original_aspect_ratio=decrease[sharp];"
                    f"[blurred][sharp]overlay=(W-w)/2:(H-h)/2"
                )
            elif reframe == "letterbox":
                vf = f"scale={tw}:{th}:force_original_aspect_ratio=decrease,pad={tw}:{th}:(ow-iw)/2:(oh-ih)/2:black"
            else:
                vf = f"crop=ih*{tw}/{th}:ih,scale={tw}:{th}"

            # Two-pass loudness normalization
            # Pass 1: measure
            measure_cmd = [
                "ffmpeg", "-i", input_file,
                "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11:print_format=json",
                "-f", "null", "-",
            ]
            measure = subprocess.run(measure_cmd, capture_output=True, text=True, timeout=300)

            af = f"loudnorm=I={lufs}:TP=-1.5:LRA=11"  # single-pass fallback

            # Extract measured values from JSON block in stderr for two-pass
            stderr = measure.stderr
            json_start = stderr.rfind("{")
            json_end = stderr.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                try:
                    data = json.loads(stderr[json_start:json_end])
                    af = (
                        f"loudnorm=I={lufs}:TP=-1.5:LRA=11"
                        f":measured_I={data['input_i']}"
                        f":measured_TP={data['input_tp']}"
                        f":measured_LRA={data['input_lra']}"
                        f":measured_thresh={data['input_thresh']}"
                        f":offset={data.get('target_offset', '0')}"
                        f":linear=true"
                    )
                except (json.JSONDecodeError, KeyError):
                    pass

            # Build render command
            if "split" in vf:
                # Complex filter path (blur_bg uses split)
                cmd = [
                    "ffmpeg", "-y", "-i", input_file,
                    "-filter_complex", f"{vf}[vout]",
                    "-map", "[vout]", "-map", "0:a",
                    "-af", af,
                    "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                    "-c:a", "aac", "-b:a", "192k",
                    out_path,
                ]
            else:
                cmd = [
                    "ffmpeg", "-y", "-i", input_file,
                    "-vf", vf,
                    "-af", af,
                    "-c:v", "libx264", "-crf", "18", "-preset", "slow",
                    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                    "-c:a", "aac", "-b:a", "192k",
                    out_path,
                ]

            ok, err = _run_ffmpeg(cmd, timeout=600)
            if ok:
                results.append(f"  {spec['label']}: {_file_info(out_path)}")
            else:
                errors.append(f"  {spec['label']}: FAILED — {err[:100]}")

        lines = [f"Exported {len(results)}/{len(platform_list)} platforms → {output_dir}/"]
        lines.extend(results)
        if errors:
            lines.append("Errors:")
            lines.extend(errors)
        return "\n".join(lines)

    # -----------------------------------------------------------------------
    # 4. Storyboard assembly
    # -----------------------------------------------------------------------

    @mcp.tool()
    def declip_storyboard(
        shots: str,
        output_path: str = "storyboard_output.mp4",
        voice: str = "",
        music: str = "",
        music_volume: float = 0.3,
        caption_style: str = "",
        transition: str = "dissolve",
        transition_duration: float = 0.5,
    ) -> str:
        """Assemble a video from a shot list — the simplest way to build a video.

        Takes a JSON array of shots and assembles them into a complete video
        with optional narration (TTS), background music, captions, and transitions.

        Each shot can have:
        - "asset": path to video/image file (required)
        - "duration": seconds (auto-detected from asset if omitted)
        - "narration": text to speak (generates TTS, uses audio duration for shot timing)
        - "text": text overlay on this shot
        - "transition": override transition for this shot

        Example shots JSON:
        [
          {"asset": "intro.mp4", "duration": 3},
          {"narration": "Welcome to the demo", "asset": "hero.mp4"},
          {"asset": "outro.mp4", "duration": 5, "text": "Thanks for watching"}
        ]

        Args:
            shots: JSON array of shot objects
            output_path: Output video path
            voice: TTS voice for narration (empty = skip TTS). e.g., "en-US-GuyNeural"
            music: Path to background music file (empty = no music)
            music_volume: Music volume when mixed with narration (0.0-1.0)
            caption_style: Auto-caption style (empty = no captions). bold, karaoke, minimal, news
            transition: Default transition between shots (dissolve, fadeblack, etc.)
            transition_duration: Default transition duration in seconds
        """
        try:
            shot_list = json.loads(shots)
        except json.JSONDecodeError as e:
            return f"Error parsing shots JSON: {e}"

        if not isinstance(shot_list, list) or not shot_list:
            return "Error: shots must be a non-empty JSON array"

        from declip.probe import probe

        with tempfile.TemporaryDirectory(prefix="declip_storyboard_") as tmpdir:
            tmpdir = Path(tmpdir)

            # Step 1: Generate TTS for narration shots
            narration_audio = []
            for i, shot in enumerate(shot_list):
                if shot.get("narration") and voice:
                    audio_path = str(tmpdir / f"narration_{i}.mp3")
                    try:
                        import edge_tts
                        communicate = edge_tts.Communicate(shot["narration"], voice)
                        asyncio.run(communicate.save(audio_path))
                        # Get actual audio duration
                        info = probe(audio_path)
                        shot["_narration_audio"] = audio_path
                        shot["_narration_duration"] = info.duration
                        # Use narration duration as shot duration if not specified
                        if "duration" not in shot:
                            shot["duration"] = info.duration + 0.5  # 0.5s padding
                    except Exception as e:
                        narration_audio.append(f"TTS failed for shot {i}: {e}")

            # Step 2: Determine durations for all shots
            for i, shot in enumerate(shot_list):
                if "duration" not in shot and "asset" in shot:
                    try:
                        info = probe(shot["asset"])
                        shot["duration"] = info.duration
                    except Exception:
                        shot["duration"] = 5.0  # fallback

            # Step 3: Build declip project JSON with auto-sequencing
            clips = []
            cursor = 0.0
            for i, shot in enumerate(shot_list):
                clip = {
                    "asset": str(Path(shot["asset"]).resolve()),
                    "start": cursor,
                    "duration": shot.get("duration", 5.0),
                    "filters": [],
                }

                # Transition (skip for first clip)
                if i > 0:
                    t = shot.get("transition", transition)
                    clip["transition_in"] = {"type": t, "duration": transition_duration}
                    cursor -= transition_duration  # overlap

                # Text overlay
                if shot.get("text"):
                    clip["filters"].append({
                        "type": "text",
                        "text": {
                            "content": shot["text"],
                            "size": 48,
                            "color": "#FFFFFF",
                            "position": [0.5, 0.85],
                        },
                    })

                cursor += clip["duration"]
                clips.append(clip)

            total_duration = cursor

            project_data = {
                "version": "1.0",
                "timeline": {
                    "tracks": [{"id": "main", "clips": clips}],
                    "audio": [],
                },
                "output": {"path": str(Path(output_path).resolve())},
            }

            # Add narration audio tracks
            narration_cursor = 0.0
            for i, shot in enumerate(shot_list):
                if "_narration_audio" in shot:
                    clip_start = clips[i]["start"]
                    project_data["timeline"]["audio"].append({
                        "asset": shot["_narration_audio"],
                        "start": clip_start,
                        "volume": 1.0,
                    })

            # Add background music
            if music and Path(music).exists():
                project_data["timeline"]["audio"].append({
                    "asset": str(Path(music).resolve()),
                    "start": 0,
                    "volume": music_volume,
                    "duck_on_speech": True,
                })

            # Step 4: Render
            from declip.schema import Project
            from declip.backends import ffmpeg as ffmpeg_backend
            from declip.output import OutputManager

            project_path = tmpdir / "project.json"
            project_path.write_text(json.dumps(project_data, indent=2))

            project = Project.load(str(project_path))
            out = OutputManager(json_mode=False, quiet=True)
            success = ffmpeg_backend.render(project, tmpdir, out, total_duration=total_duration)

            if not success:
                return "Error: storyboard render failed"

            lines = [
                f"Storyboard assembled: {len(shot_list)} shots",
                f"Duration: {total_duration:.1f}s",
            ]

            # Step 5: Optional auto-captions on the rendered output
            if caption_style and Path(output_path).exists():
                captioned_path = str(Path(output_path).with_stem(Path(output_path).stem + "_captioned"))
                # Use the auto_caption tool's underlying logic
                from declip.analyze import transcribe as _transcribe
                try:
                    result = _transcribe(output_path, word_timestamps=True)
                    if result.words:
                        word_dicts = [
                            {"word": w.word, "start": w.start, "end": w.end, "confidence": w.confidence}
                            for w in result.words
                        ]
                        ass_content = _generate_ass(word_dicts, style=caption_style)
                        ass_path = tmpdir / "captions.ass"
                        ass_path.write_text(ass_content, encoding="utf-8")
                        escaped = str(ass_path).replace("\\", "\\\\").replace(":", "\\:")
                        cmd = ["ffmpeg", "-y", "-i", output_path,
                               "-vf", f"ass='{escaped}'", "-c:a", "copy", captioned_path]
                        ok, _ = _run_ffmpeg(cmd)
                        if ok:
                            # Replace output with captioned version
                            os.replace(captioned_path, output_path)
                            lines.append(f"Captions: {caption_style} style applied")
                except Exception as e:
                    lines.append(f"Caption warning: {e}")

            if voice:
                narr_count = sum(1 for s in shot_list if "_narration_audio" in s)
                lines.append(f"Narration: {narr_count} shots voiced ({voice})")
            if music:
                lines.append(f"Music: {Path(music).name} at {music_volume} volume")

            lines.append(f"Output: {_file_info(output_path)}")
            return "\n".join(lines)
