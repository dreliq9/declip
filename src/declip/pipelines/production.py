"""Transport-neutral production pipelines: captions, TTS, exports, storyboard."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from declip.pipelines.types import PipelineResult


def _run_ffmpeg(command: list[str], timeout: int = 300) -> tuple[bool, str]:
    try:
        proc = subprocess.run(command, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"FFmpeg timed out after {timeout}s"
    if proc.returncode != 0:
        return False, proc.stderr.decode(errors="replace")[-500:]
    return True, ""


def _file_info(path: str) -> str:
    file = Path(path)
    return f"{path} ({file.stat().st_size / 1024 / 1024:.1f} MB)" if file.exists() else path


def _ass_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    remainder = seconds % 60
    return f"{hours}:{minutes:02d}:{remainder:05.2f}"


def generate_ass(words: list[dict], style: str = "bold", resolution: tuple[int, int] = (1920, 1080)) -> str:
    """Generate ASS subtitle text from word-level timestamps."""
    width, height = resolution
    styles = {
        "bold": {"fontname":"Arial","fontsize":64,"primary":"&H00FFFFFF","secondary":"&H0000FFFF","outline":"&H00000000","back":"&H80000000","bold":-1,"outline_w":3,"shadow":2,"alignment":2,"margin_v":60},
        "karaoke": {"fontname":"Arial","fontsize":56,"primary":"&H0000FFFF","secondary":"&H00FFFFFF","outline":"&H00000000","back":"&H00000000","bold":-1,"outline_w":2,"shadow":0,"alignment":2,"margin_v":50},
        "minimal": {"fontname":"Arial","fontsize":42,"primary":"&H00FFFFFF","secondary":"&H00FFFFFF","outline":"&H00000000","back":"&H00000000","bold":0,"outline_w":2,"shadow":1,"alignment":2,"margin_v":40},
        "news": {"fontname":"Arial","fontsize":38,"primary":"&H00FFFFFF","secondary":"&H00FFFFFF","outline":"&H00000000","back":"&H80000000","bold":0,"outline_w":1,"shadow":0,"alignment":1,"margin_v":30},
    }
    selected = styles.get(style, styles["bold"])
    header = f"""[Script Info]\nTitle: Auto-Captions\nScriptType: v4.00+\nPlayResX: {width}\nPlayResY: {height}\nWrapStyle: 0\n\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{selected['fontname']},{selected['fontsize']},{selected['primary']},{selected['secondary']},{selected['outline']},{selected['back']},{selected['bold']},0,0,0,100,100,0,0,1,{selected['outline_w']},{selected['shadow']},{selected['alignment']},20,20,{selected['margin_v']},1\n\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"""
    lines = [header]
    groups = [words[index:index + 6] for index in range(0, len(words), 6)]
    karaoke = style in {"karaoke", "bold"}
    for group in groups:
        if not group:
            continue
        if karaoke:
            text = " ".join(f"{{\\kf{max(1, int((word['end'] - word['start']) * 100))}}}{word['word']}" for word in group)
        else:
            text = " ".join(word["word"] for word in group)
        lines.append(f"Dialogue: 0,{_ass_time(group[0]['start'])},{_ass_time(group[-1]['end'])},Default,,0,0,0,,{text}")
    return "\n".join(lines)


def auto_caption(input_file: str, style: str = "bold", model_size: str = "base", language: str | None = None, output_path: str | None = None, ass_only: bool = False) -> PipelineResult:
    if not Path(input_file).exists():
        return PipelineResult(success=False, message=f"Error: {input_file} not found", error="input not found")
    from declip.analyze import transcribe
    from declip.probe import probe
    try:
        transcription = transcribe(input_file, model_size=model_size, language=language, word_timestamps=True)
    except Exception as exc:
        return PipelineResult(success=False, message=f"Transcription error: {exc}", error=str(exc))
    if not transcription.words:
        return PipelineResult(success=False, message="Error: no words detected in audio", error="no words detected")
    try:
        info = probe(input_file)
        resolution = (info.width or 1920, info.height or 1080)
    except Exception:
        resolution = (1920, 1080)
    words = [{"word": word.word, "start": word.start, "end": word.end, "confidence": word.confidence} for word in transcription.words]
    ass_content = generate_ass(words, style=style, resolution=resolution)
    ass_path = Path(input_file).with_suffix(".ass")
    ass_path.write_text(ass_content, encoding="utf-8")
    if ass_only:
        message = f"ASS file generated: {ass_path}\nWords: {len(words)}, Style: {style}"
        return PipelineResult(success=True, message=message, output_path=str(ass_path), details={"words":len(words),"style":style,"language":transcription.language})
    if not output_path:
        source = Path(input_file)
        output_path = str(source.with_stem(source.stem + "_captioned"))
    escaped = str(ass_path).replace("\\", "\\\\").replace(":", "\\:")
    ok, error = _run_ffmpeg(["ffmpeg", "-y", "-i", input_file, "-vf", f"ass='{escaped}'", "-c:a", "copy", output_path], timeout=600)
    if not ok:
        return PipelineResult(success=False, message=f"Burn-in error: {error}", error=error)
    message = f"Auto-captions applied ({style} style)\nWords: {len(words)}, Language: {transcription.language}\nASS: {ass_path}\nOutput: {_file_info(output_path)}"
    return PipelineResult(success=True, message=message, output_path=output_path, details={"ass_path":str(ass_path),"words":len(words),"style":style,"language":transcription.language})


def tts(text: str, output_path: str = "voiceover.mp3", voice: str = "en-US-GuyNeural", rate: str = "+0%", pitch: str = "+0Hz", output_words: bool = False) -> PipelineResult:
    if not text.strip():
        return PipelineResult(success=False, message="Error: text must not be empty", error="empty text")
    try:
        import edge_tts
    except ImportError as exc:
        return PipelineResult(success=False, message="Error: edge-tts is not installed", error=str(exc))
    async def generate() -> list[dict]:
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        word_data: list[dict] = []
        with open(output_path, "wb") as handle:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    handle.write(chunk["data"])
                elif chunk["type"] == "WordBoundary" and output_words:
                    word_data.append({"word":chunk["text"],"start":chunk["offset"] / 10_000_000,"end":(chunk["offset"] + chunk["duration"]) / 10_000_000})
        return word_data
    try:
        words = asyncio.run(generate())
    except Exception as exc:
        return PipelineResult(success=False, message=f"TTS error: {exc}", error=str(exc))
    if not Path(output_path).exists():
        return PipelineResult(success=False, message="Error: TTS produced no output", error="missing output")
    lines = [f"Voice: {voice}", f"Output: {_file_info(output_path)}"]
    details: dict = {"voice":voice}
    if output_words and words:
        words_path = Path(output_path).with_suffix(".words.json")
        words_path.write_text(json.dumps(words, indent=2), encoding="utf-8")
        lines += [f"Words with timing: {len(words)}", f"Word timing: {words_path}"]
        details.update({"word_count":len(words),"words_path":str(words_path)})
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", output_path], capture_output=True, text=True)
    if probe.returncode == 0:
        try:
            duration = float(probe.stdout.strip()); lines.append(f"Duration: {duration:.1f}s"); details["duration_seconds"] = duration
        except ValueError:
            pass
    return PipelineResult(success=True, message="\n".join(lines), output_path=output_path, details=details)


def tts_voices(language: str = "en") -> PipelineResult:
    try:
        import edge_tts
    except ImportError as exc:
        return PipelineResult(success=False, message="Error: edge-tts is not installed", error=str(exc))
    try:
        voices = asyncio.run(edge_tts.list_voices())
    except Exception as exc:
        return PipelineResult(success=False, message=f"Error: {exc}", error=str(exc))
    filtered = [voice for voice in voices if voice["Locale"].lower().startswith(language.lower())]
    if not filtered:
        return PipelineResult(success=False, message=f"No voices found for language '{language}'", error="no voices")
    lines = [f"Voices for '{language}' ({len(filtered)}):"] + [f"  {voice['ShortName']} — {voice.get('Gender','')}, {voice['Locale']}" for voice in filtered]
    return PipelineResult(success=True, message="\n".join(lines), details={"language":language,"voices":filtered})


PLATFORM_SPECS = {
    "youtube": {"w":1920,"h":1080,"aspect":"16:9","lufs":-14,"label":"YouTube"},
    "youtube-4k": {"w":3840,"h":2160,"aspect":"16:9","lufs":-14,"label":"YouTube 4K"},
    "shorts": {"w":1080,"h":1920,"aspect":"9:16","lufs":-14,"label":"YouTube Shorts"},
    "reels": {"w":1080,"h":1920,"aspect":"9:16","lufs":-11,"label":"Instagram Reels"},
    "tiktok": {"w":1080,"h":1920,"aspect":"9:16","lufs":-11,"label":"TikTok"},
    "twitter": {"w":1280,"h":720,"aspect":"16:9","lufs":-14,"label":"Twitter/X"},
    "linkedin": {"w":1920,"h":1080,"aspect":"16:9","lufs":-14,"label":"LinkedIn"},
    "instagram-feed": {"w":1080,"h":1080,"aspect":"1:1","lufs":-11,"label":"Instagram Feed"},
    "instagram-4x5": {"w":1080,"h":1350,"aspect":"4:5","lufs":-11,"label":"Instagram 4:5"},
}


def _measure_loudness(input_file: str, lufs: int) -> str:
    measure = subprocess.run(["ffmpeg", "-i", input_file, "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11:print_format=json", "-f", "null", "-"], capture_output=True, text=True, timeout=300)
    fallback = f"loudnorm=I={lufs}:TP=-1.5:LRA=11"
    start, end = measure.stderr.rfind("{"), measure.stderr.rfind("}") + 1
    if start < 0 or end <= start:
        return fallback
    try:
        data = json.loads(measure.stderr[start:end])
        return f"loudnorm=I={lufs}:TP=-1.5:LRA=11:measured_I={data['input_i']}:measured_TP={data['input_tp']}:measured_LRA={data['input_lra']}:measured_thresh={data['input_thresh']}:offset={data.get('target_offset','0')}:linear=true"
    except (json.JSONDecodeError, KeyError):
        return fallback


def platform_export(input_file: str, platforms: str = "youtube,shorts,reels", reframe: str = "center_crop", output_dir: str | None = None) -> PipelineResult:
    if not Path(input_file).exists():
        return PipelineResult(success=False, message=f"Error: {input_file} not found", error="input not found")
    if reframe not in {"center_crop", "blur_bg", "letterbox"}:
        return PipelineResult(success=False, message=f"Error: unknown reframe strategy '{reframe}'", error="invalid reframe")
    selected = [platform.strip().lower() for platform in platforms.split(",") if platform.strip()]
    invalid = [platform for platform in selected if platform not in PLATFORM_SPECS]
    if invalid:
        return PipelineResult(success=False, message=f"Unknown platforms: {invalid}\nAvailable: {', '.join(PLATFORM_SPECS)}", error="unknown platforms")
    if not selected:
        return PipelineResult(success=False, message="Error: provide at least one platform", error="no platforms")
    if not output_dir:
        output_dir = str(Path(input_file).stem + "_exports")
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    loudness_filters = {lufs:_measure_loudness(input_file, lufs) for lufs in {PLATFORM_SPECS[platform]["lufs"] for platform in selected}}
    successes, failures, outputs = [], [], {}
    for platform in selected:
        spec = PLATFORM_SPECS[platform]
        width, height = spec["w"], spec["h"]
        if spec["aspect"] == "16:9":
            video_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
            complex_filter = False
        elif reframe == "center_crop":
            video_filter = f"crop=ih*{width}/{height}:ih,scale={width}:{height}"
            complex_filter = False
        elif reframe == "letterbox":
            video_filter = f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black"
            complex_filter = False
        else:
            video_filter = f"[0:v]split[bg][fg];[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=20:5[blurred];[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[sharp];[blurred][sharp]overlay=(W-w)/2:(H-h)/2[vout]"
            complex_filter = True
        output = str(Path(output_dir) / f"{platform}.mp4")
        command = ["ffmpeg", "-y", "-i", input_file]
        if complex_filter:
            command += ["-filter_complex", video_filter, "-map", "[vout]", "-map", "0:a?"]
        else:
            command += ["-vf", video_filter]
        command += ["-af", loudness_filters[spec["lufs"]], "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-c:a", "aac", "-b:a", "192k", output]
        ok, error = _run_ffmpeg(command, timeout=600)
        if ok:
            successes.append(f"  {spec['label']}: {_file_info(output)}"); outputs[platform] = output
        else:
            failures.append(f"  {spec['label']}: FAILED — {error[:100]}")
    lines = [f"Exported {len(successes)}/{len(selected)} platforms → {output_dir}/"] + successes
    if failures:
        lines += ["Errors:"] + failures
    return PipelineResult(success=bool(successes) and not failures, message="\n".join(lines), output_path=output_dir, details={"outputs":outputs,"failures":failures}, error="; ".join(failures) if failures else None)


_TRANSITION_ALIASES = {
    "fadeblack":"fade_black", "fadewhite":"fade_white", "fadegrays":"fade_grays",
    "wipeleft":"wipe_left", "wiperight":"wipe_right", "wipeup":"wipe_up", "wipedown":"wipe_down",
    "slideleft":"slide_left", "slideright":"slide_right", "slideup":"slide_up", "slidedown":"slide_down",
    "smoothleft":"smooth_left", "smoothright":"smooth_right", "smoothup":"smooth_up", "smoothdown":"smooth_down",
    "circleopen":"circle_open", "circleclose":"circle_close", "circlecrop":"circle_crop", "rectcrop":"rect_crop",
    "horzopen":"horz_open", "horzclose":"horz_close", "vertopen":"vert_open", "vertclose":"vert_close",
    "diagtl":"diag_tl", "diagtr":"diag_tr", "diagbl":"diag_bl", "diagbr":"diag_br",
    "hlslice":"hl_slice", "hrslice":"hr_slice", "vuslice":"vu_slice", "vdslice":"vd_slice", "zoomin":"zoom_in",
    "squeezeh":"squeeze_h", "squeezev":"squeeze_v", "hlwind":"hl_wind", "hrwind":"hr_wind", "vuwind":"vu_wind", "vdwind":"vd_wind",
    "coverleft":"cover_left", "coverright":"cover_right", "coverup":"cover_up", "coverdown":"cover_down",
    "revealleft":"reveal_left", "revealright":"reveal_right", "revealup":"reveal_up", "revealdown":"reveal_down",
}


def _schema_transition(name: str) -> str:
    return _TRANSITION_ALIASES.get(name, name)


def _mix_music(video_file: str, music_file: str, volume: float, output_path: str) -> tuple[bool, str]:
    graph = f"[1:a]volume={volume}[music];[music][0:a]sidechaincompress=threshold=0.02:ratio=8:attack=200:release=1000:level_sc=1[ducked];[ducked][0:a]amix=inputs=2:duration=first:normalize=0[aout]"
    command = ["ffmpeg", "-y", "-i", video_file, "-i", music_file, "-filter_complex", graph, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", output_path]
    return _run_ffmpeg(command, timeout=600)


def storyboard(
    shots: str,
    output_path: str = "storyboard_output.mp4",
    voice: str = "",
    music: str = "",
    music_volume: float = 0.3,
    caption_style: str = "",
    transition: str = "dissolve",
    transition_duration: float = 0.5,
) -> PipelineResult:
    try:
        shot_list = json.loads(shots)
    except json.JSONDecodeError as exc:
        return PipelineResult(success=False, message=f"Error parsing shots JSON: {exc}", error=str(exc))
    if not isinstance(shot_list, list) or not shot_list:
        return PipelineResult(success=False, message="Error: shots must be a non-empty JSON array", error="invalid shots")
    if transition_duration <= 0 or music_volume < 0:
        return PipelineResult(success=False, message="Error: transition_duration must be positive and music_volume non-negative", error="invalid parameters")
    for index, shot in enumerate(shot_list):
        if not isinstance(shot, dict) or not shot.get("asset"):
            return PipelineResult(success=False, message=f"Error: shot {index} requires an asset", error="missing asset")
        if not Path(shot["asset"]).exists():
            return PipelineResult(success=False, message=f"Error: {shot['asset']} not found", error="missing asset")
    from declip.probe import probe
    from declip.schema import Project
    from declip.backends import ffmpeg as ffmpeg_backend
    from declip.output import OutputManager
    from declip import edit
    warnings: list[str] = []
    with tempfile.TemporaryDirectory(prefix="declip_storyboard_") as directory:
        work = Path(directory)
        for index, shot in enumerate(shot_list):
            if shot.get("narration") and voice:
                narration_path = str(work / f"narration_{index}.mp3")
                narration = tts(shot["narration"], narration_path, voice)
                if narration.success:
                    shot["_narration_audio"] = narration_path
                    try: narration_duration = probe(narration_path).duration
                    except Exception: narration_duration = narration.details.get("duration_seconds", 0)
                    if "duration" not in shot and narration_duration:
                        shot["duration"] = narration_duration + 0.5
                else:
                    warnings.append(f"TTS failed for shot {index}: {narration.message}")
            if "duration" not in shot:
                try: shot["duration"] = probe(shot["asset"]).duration
                except Exception: shot["duration"] = 5.0; warnings.append(f"Duration probe failed for shot {index}; using 5.0s")
        clips = []
        for index, shot in enumerate(shot_list):
            clip: dict = {"asset":str(Path(shot["asset"]).resolve()),"start":0 if index == 0 else "auto","duration":float(shot.get("duration",5.0)),"filters":[]}
            if index > 0:
                clip["transition_in"] = {"type":_schema_transition(shot.get("transition",transition)),"duration":transition_duration}
            if shot.get("text"):
                clip["filters"].append({"type":"text","text":{"content":shot["text"],"size":48,"color":"#FFFFFF","position":[0.5,0.85]}})
            clips.append(clip)
        visual_output = str(work / "visuals.mp4") if voice or music or caption_style else str(Path(output_path).resolve())
        project = Project.model_validate({"version":"1.0","timeline":{"tracks":[{"id":"main","clips":clips}],"audio":[]},"output":{"path":visual_output}})
        out = OutputManager(json_mode=False, quiet=True)
        if not ffmpeg_backend.render(project, Path("."), out, total_duration=None):
            return PipelineResult(success=False, message="Error: storyboard visual render failed", error=out.get_log())
        normalized = __import__("declip.compilers.render_plan", fromlist=["build_render_plan"]).build_render_plan(project, Path(".")).project
        resolved_clips = normalized.timeline.tracks[0].clips
        current = visual_output
        for index, shot in enumerate(shot_list):
            narration = shot.get("_narration_audio")
            if not narration:
                continue
            mixed = str(work / f"narrated_{index}.mp4")
            message = edit.audio_mix(current, narration, video_volume=1.0, audio_volume=1.0, audio_start=float(resolved_clips[index].start), replace=False, output_path=mixed)
            if message.startswith("Error") or not Path(mixed).exists():
                warnings.append(f"Narration mix failed for shot {index}: {message}")
            else:
                current = mixed
        final_pre_caption = str(Path(output_path).resolve())
        if music:
            if not Path(music).exists():
                warnings.append(f"Music file not found: {music}")
                shutil.copy2(current, final_pre_caption)
            else:
                ok, error = _mix_music(current, str(Path(music).resolve()), music_volume, final_pre_caption)
                if not ok:
                    warnings.append(f"Music mix failed: {error}"); shutil.copy2(current, final_pre_caption)
        elif current != final_pre_caption:
            shutil.copy2(current, final_pre_caption)
        if caption_style:
            captioned = str(work / "captioned.mp4")
            caption_result = auto_caption(final_pre_caption, style=caption_style, output_path=captioned)
            if caption_result.success:
                os.replace(captioned, final_pre_caption)
            else:
                warnings.append(f"Caption warning: {caption_result.message}")
        duration = max(float(clip.start) + float(clip.duration or 0) for clip in resolved_clips)
        lines = [f"Storyboard assembled: {len(shot_list)} shots", f"Duration: {duration:.1f}s"]
        if voice:
            lines.append(f"Narration: {sum(1 for shot in shot_list if shot.get('_narration_audio'))} shots voiced ({voice})")
        if music:
            lines.append(f"Music: {Path(music).name} at {music_volume} volume")
        if caption_style:
            lines.append(f"Captions: {caption_style} style requested")
        lines.extend(f"Warning: {warning}" for warning in warnings)
        lines.append(f"Output: {_file_info(final_pre_caption)}")
        return PipelineResult(success=True, message="\n".join(lines), output_path=final_pre_caption, details={"shots":len(shot_list),"duration_seconds":duration,"warnings":warnings})
