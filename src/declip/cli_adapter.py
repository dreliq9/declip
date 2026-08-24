"""Declip CLI adapter.

The command surface lives here; media semantics live in reusable core modules.
This module intentionally owns no subprocess execution.
"""
from __future__ import annotations

import json
import sys
import time
from dataclasses import asdict
from pathlib import Path

import click

from declip import __version__
from declip.output import OutputManager
from declip.schema import PRESETS


def _parse_vars(values: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        if "=" not in value:
            click.echo(f"Warning: ignoring malformed --var '{value}' (expected key=value)", err=True)
            continue
        key, item = value.split("=", 1)
        result[key.strip()] = item.strip()
    return result


def _out(ctx) -> OutputManager:
    return ctx.obj["out"]


def _emit_text(ctx, stage: str, text: str, **data) -> None:
    out = _out(ctx)
    if out.json_mode:
        out.emit(stage, message=text, **data)
    else:
        out._out(text)


def _fail(ctx, stage: str, message: str) -> None:
    _out(ctx).error(stage, message)
    raise click.exceptions.Exit(1)


def _emit_model_result(ctx, stage: str, result) -> None:
    out = _out(ctx)
    if out.json_mode and hasattr(result, "model_dump"):
        out.emit(stage, **result.model_dump())
    else:
        out._out(str(result))
    if hasattr(result, "success") and not result.success:
        raise click.exceptions.Exit(1)


@click.group()
@click.version_option(__version__)
@click.option("--json", "json_mode", is_flag=True, help="Output structured NDJSON")
@click.pass_context
def main(ctx, json_mode):
    """Declip — declarative video editing. JSON in, video out."""
    ctx.ensure_object(dict)
    ctx.obj["out"] = OutputManager(json_mode=json_mode)


# ---------------------------------------------------------------------------
# Project commands
# ---------------------------------------------------------------------------

@main.command()
@click.argument("project_file", type=click.Path(exists=True))
@click.pass_context
def validate(ctx, project_file):
    """Validate a project file without rendering."""
    from declip import project_ops
    result = project_ops.validate_project(project_file)
    if result.startswith("Validation error:"):
        _fail(ctx, "validate", result.removeprefix("Validation error: "))
    if "\nMissing assets:" in result:
        _fail(ctx, "validate", result)
    _emit_text(ctx, "validate", result, valid=True)


@main.command()
@click.argument("project_file", type=click.Path(exists=True))
@click.option("--backend", type=click.Choice(["auto", "ffmpeg", "mlt"]), default="auto", help="Force a specific backend")
@click.option("--dry-run", is_flag=True, help="Show commands without rendering")
@click.option("--output", "-o", "output_path", help="Override output path")
@click.option("--preset", type=click.Choice(list(PRESETS.keys())), help="Use an output preset")
@click.option("--var", "variables", multiple=True, help="Template variable: key=value")
@click.pass_context
def render(ctx, project_file, backend, dry_run, output_path, preset, variables):
    """Render a project file to video."""
    from declip import project_ops
    from declip.compilers import ffmpeg as ffmpeg_compiler
    from declip.compilers import mlt as mlt_compiler

    try:
        prepared = project_ops.prepare_project(
            project_file,
            backend=backend,
            output_path=output_path,
            preset=preset,
            variables=_parse_vars(variables),
        )
    except Exception as exc:
        _fail(ctx, "load", str(exc))

    out = _out(ctx)
    out.emit("load", f"  Loaded: {project_file}", project=project_file)
    out.emit("backend", f"  Backend: {prepared.backend}", backend=prepared.backend)

    if dry_run:
        if prepared.backend == "ffmpeg":
            try:
                commands = ffmpeg_compiler.compile_commands(prepared.project, prepared.project_dir)
            except Exception as exc:
                _fail(ctx, "compile", str(exc))
            for index, command in enumerate(commands, 1):
                out.emit("dry_run", f"  Command {index}: {' '.join(command)}", step=index, command=command)
        else:
            xml = mlt_compiler.compile_to_string(prepared.project, prepared.project_dir)
            out.emit("dry_run", f"  MLT XML ({len(xml)} bytes):\n{xml}", xml=xml)
        return

    if not project_ops.execute_prepared(prepared, out):
        raise click.exceptions.Exit(1)


@main.command()
@click.argument("project_file", type=click.Path(exists=True))
@click.pass_context
def export_mlt(ctx, project_file):
    """Export a project as MLT XML without rendering."""
    from declip import project_ops
    result = project_ops.export_mlt(project_file)
    if result.startswith("Error:"):
        _fail(ctx, "export", result.removeprefix("Error: "))
    if _out(ctx).json_mode:
        _out(ctx).emit("export", xml=result)
    else:
        click.echo(result)


@main.command()
def init():
    """Create a minimal project.json template in the current directory."""
    from declip import project_ops
    result = project_ops.init_project(".")
    if result.startswith("Error:"):
        raise click.ClickException(result.removeprefix("Error: "))
    click.echo(result)


@main.command()
def presets():
    """List available output presets."""
    from declip import project_ops
    click.echo(project_ops.list_presets())


@main.command()
@click.argument("project_file", type=click.Path(exists=True))
@click.pass_context
def assets(ctx, project_file):
    """List all assets referenced by a project."""
    from declip import project_ops
    result = project_ops.assets(project_file)
    if result.startswith("Error:"):
        _fail(ctx, "assets", result.removeprefix("Error: "))
    _emit_text(ctx, "assets", result)


# ---------------------------------------------------------------------------
# Quick commands
# ---------------------------------------------------------------------------

@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--in", "trim_in", type=float, required=True, help="Start time in seconds")
@click.option("--out", "trim_out", type=float, required=True, help="End time in seconds")
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def trim(ctx, input_file, trim_in, trim_out, output_path):
    """Trim a video to a time range."""
    from declip import quick
    result = quick.trim(input_file, trim_in, trim_out, smart=False, output_path=output_path)
    _emit_model_result(ctx, "trim", result)


@main.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", default="concat_output.mp4", help="Output file path")
@click.option("--preset", type=click.Choice(list(PRESETS.keys())), help="Output preset")
@click.pass_context
def concat(ctx, files, output_path, preset):
    """Concatenate multiple videos."""
    from declip import quick
    result = quick.concat(list(files), output_path, preset)
    _emit_model_result(ctx, "concat", result)


@main.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.pass_context
def probe(ctx, files):
    """Probe media files and show their properties."""
    from declip import quick
    out = _out(ctx)
    failed = False
    for file_path in files:
        result = quick.probe(file_path)
        failed = failed or not result.success
        if out.json_mode:
            out.emit("probe", **result.model_dump())
        else:
            out._out(str(result))
    if failed:
        raise click.exceptions.Exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--at", "timestamp", type=float, default=1.0, help="Timestamp in seconds")
@click.option("--output", "-o", "output_path", help="Output PNG path")
@click.pass_context
def thumbnail(ctx, input_file, timestamp, output_path):
    """Extract a single frame as PNG."""
    from declip import quick
    result = quick.thumbnail(input_file, timestamp, output_path)
    _emit_model_result(ctx, "thumbnail", result)


# ---------------------------------------------------------------------------
# Analysis commands
# ---------------------------------------------------------------------------

@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--count", "-n", default=16, help="Number of frames to extract")
@click.option("--output-dir", "-o", help="Output directory for frames")
@click.option("--timestamps", "-t", help="Comma-separated timestamps instead of even spacing")
@click.pass_context
def extract_frames(ctx, input_file, count, output_dir, timestamps):
    """Extract multiple frames from a video."""
    from declip.analyze import extract_frames as do_extract
    output_dir = output_dir or str(Path(input_file).stem + "_frames")
    try:
        ts_list = [float(value.strip()) for value in timestamps.split(",")] if timestamps else None
        frames = do_extract(input_file, output_dir, count=count, timestamps=ts_list)
    except Exception as exc:
        _fail(ctx, "extract_frames", str(exc))
    out = _out(ctx)
    if out.json_mode:
        for frame in frames:
            out.emit("frame", path=frame.path, timestamp=frame.timestamp, width=frame.width, height=frame.height)
    else:
        out._out(f"Extracted {len(frames)} frames → {output_dir}/")
        for frame in frames:
            out._out(f"  {frame.timestamp:.2f}s → {Path(frame.path).name}")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--threshold", default=0.3, help="Scene change threshold (legacy 0.0-1.0 or PySceneDetect scale)")
@click.pass_context
def detect_scenes(ctx, input_file, threshold):
    """Detect scene changes in a video."""
    from declip.analyze import detect_scenes as do_detect
    try:
        cuts = do_detect(input_file, threshold=threshold)
    except Exception as exc:
        _fail(ctx, "detect_scenes", str(exc))
    out = _out(ctx)
    if out.json_mode:
        for cut in cuts:
            out.emit("scene_cut", timestamp=cut.timestamp, score=cut.score)
        out.emit("summary", total_cuts=len(cuts))
    else:
        out._out(f"Found {len(cuts)} scene cut(s):")
        for cut in cuts:
            out._out(f"  {cut.timestamp:.2f}s (score: {cut.score:.3f})")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--threshold", default="-30dB", help="Noise threshold")
@click.option("--min-duration", default=0.5, help="Minimum silence duration")
@click.pass_context
def detect_silence(ctx, input_file, threshold, min_duration):
    """Detect silent segments in audio/video."""
    from declip.analyze import detect_silence as do_detect
    try:
        segments = do_detect(input_file, noise_threshold=threshold, min_duration=min_duration)
    except Exception as exc:
        _fail(ctx, "detect_silence", str(exc))
    out = _out(ctx)
    if out.json_mode:
        for segment in segments:
            out.emit("silence", start=segment.start, end=segment.end, duration=segment.duration)
        out.emit("summary", total_segments=len(segments))
    else:
        out._out(f"Found {len(segments)} silent segment(s):")
        for segment in segments:
            out._out(f"  {segment.start:.2f}s - {segment.end:.2f}s ({segment.duration:.1f}s)")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output-dir", "-o", help="Directory for review output")
@click.option("--frames", "-n", default=16, help="Number of overview frames")
@click.option("--scene-threshold", default=0.3, help="Scene detection threshold")
@click.pass_context
def review(ctx, input_file, output_dir, frames, scene_threshold):
    """Run the full self-review pipeline."""
    from declip.analyze import review as do_review
    output_dir = output_dir or str(Path(input_file).stem + "_review")
    try:
        result = do_review(input_file, output_dir, frame_count=frames, scene_threshold=scene_threshold)
    except Exception as exc:
        _fail(ctx, "review", str(exc))
    if _out(ctx).json_mode:
        _out(ctx).emit("review_complete", **result.to_dict())
    else:
        _out(ctx)._out(result.summary())


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.pass_context
def loudness(ctx, input_file):
    """Analyze audio loudness (EBU R128 / LUFS)."""
    from declip.analyze import analyze_loudness
    try:
        result = analyze_loudness(input_file)
    except Exception as exc:
        _fail(ctx, "loudness", str(exc))
    if _out(ctx).json_mode:
        _out(ctx).emit("loudness", **result.to_dict())
    else:
        lines = [
            f"Integrated: {result.integrated_lufs} LUFS",
            f"Loudness range: {result.loudness_range} LU",
            f"True peak: {result.true_peak_dbtp} dBTP",
        ]
        if result.target_offset is not None:
            direction = "louder" if result.target_offset > 0 else "quieter"
            lines.append(f"Streaming target (-14 LUFS): {abs(result.target_offset):.1f} LU {direction}")
        _out(ctx)._out("\n".join(lines))


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", help="Output file path")
@click.option("--format", "-f", "fmt", default="wav", type=click.Choice(["wav", "mp3", "flac", "aac"]))
@click.option("--sample-rate", "-r", type=int, help="Sample rate")
@click.pass_context
def extract_audio(ctx, input_file, output_path, fmt, sample_rate):
    """Extract the audio track from a media file."""
    from declip.analyze import extract_audio as do_extract
    try:
        result = do_extract(input_file, output_path, format=fmt, sample_rate=sample_rate)
        size = Path(result).stat().st_size
    except Exception as exc:
        _fail(ctx, "extract_audio", str(exc))
    if _out(ctx).json_mode:
        _out(ctx).emit("extract_audio", output=result, size_bytes=size, format=fmt)
    else:
        _out(ctx)._out(f"Extracted: {result} ({size / 1024 / 1024:.1f} MB)")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.pass_context
def detect_beats(ctx, input_file):
    """Detect beats and estimate tempo."""
    from declip.analyze import detect_beats as do_detect
    try:
        result = do_detect(input_file)
    except Exception as exc:
        _fail(ctx, "detect_beats", str(exc))
    if _out(ctx).json_mode:
        _out(ctx).emit("beats", tempo=result.tempo, beat_count=result.beat_count, beat_times=result.beat_times)
    else:
        lines = [f"Tempo: {result.tempo} BPM", f"Beats: {result.beat_count}"]
        shown = result.beat_times if result.beat_count <= 20 else result.beat_times[:10]
        lines += [f"  {value:.3f}s" for value in shown]
        if result.beat_count > len(shown):
            lines.append(f"  ... and {result.beat_count - len(shown)} more")
        _out(ctx)._out("\n".join(lines))


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--at", "timestamp", type=float, help="Single timestamp to OCR")
@click.option("--count", "-n", default=5, help="Number of frames to OCR")
@click.option("--output-dir", "-o", help="Directory for extracted frames")
@click.option("--lang", default="eng", help="Tesseract language code")
@click.pass_context
def ocr(ctx, input_file, timestamp, count, output_dir, lang):
    """Read text from video frames using OCR."""
    from declip.analyze import ocr_frame, ocr_frames
    out = _out(ctx)
    try:
        if timestamp is not None:
            result = ocr_frame(input_file, timestamp, output_dir, lang)
            if out.json_mode:
                out.emit("ocr", timestamp=result.timestamp, text=result.text, frame_path=result.frame_path)
            else:
                out._out(f"Frame at {result.timestamp:.2f}s:\n{result.text or '(no text detected)'}")
        else:
            for result in ocr_frames(input_file, count=count, output_dir=output_dir, lang=lang):
                if out.json_mode:
                    out.emit("ocr", timestamp=result.timestamp, text=result.text, frame_path=result.frame_path)
                else:
                    preview = result.text[:80].replace("\n", " ") if result.text else "(no text)"
                    out._out(f"{result.timestamp:.2f}s: {preview}")
    except Exception as exc:
        _fail(ctx, "ocr", str(exc))


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", help="Output .mid file path")
@click.option("--threshold", default=0.5, help="Pitch confidence threshold")
@click.pass_context
def audio_to_midi(ctx, input_file, output_path, threshold):
    """Transcribe audio to MIDI."""
    from declip.analyze import audio_to_midi as do_convert
    try:
        result = do_convert(input_file, output_path, confidence_threshold=threshold)
    except Exception as exc:
        _fail(ctx, "audio_to_midi", str(exc))
    if _out(ctx).json_mode:
        _out(ctx).emit("midi", note_count=result.note_count, duration=result.duration, output=result.output_path)
    else:
        lines = [f"Notes: {result.note_count}", f"Duration: {result.duration:.1f}s"]
        if result.output_path:
            lines.append(f"MIDI file: {result.output_path}")
        _out(ctx)._out("\n".join(lines))


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.pass_context
def streams(ctx, input_file):
    """List all streams in a media file."""
    from declip.analyze import list_streams
    try:
        result = list_streams(input_file)
    except Exception as exc:
        _fail(ctx, "streams", str(exc))
    out = _out(ctx)
    for stream in result:
        if out.json_mode:
            out.emit("stream", **{key: value for key, value in asdict(stream).items() if value is not None})
        else:
            language = f" [{stream.language}]" if stream.language else ""
            if stream.type == "video":
                out._out(f"#{stream.index} video: {stream.codec} {stream.width}x{stream.height} @ {(stream.fps or 0):.1f}fps{language}")
            elif stream.type == "audio":
                layout = f" ({stream.channel_layout})" if stream.channel_layout else ""
                out._out(f"#{stream.index} audio: {stream.codec} {stream.channels}ch {stream.sample_rate}Hz{layout}{language}")
            else:
                out._out(f"#{stream.index} {stream.type}: {stream.codec}{language}")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", help="Output image path")
@click.option("--columns", default=4, help="Grid columns")
@click.option("--rows", default=4, help="Grid rows")
@click.option("--thumb-width", default=480, help="Thumbnail width")
@click.pass_context
def contact_sheet(ctx, input_file, output_path, columns, rows, thumb_width):
    """Generate a contact sheet from a video."""
    from declip.analyze import contact_sheet as do_sheet
    output_path = output_path or str(Path(input_file).stem + "_contact.png")
    try:
        result = do_sheet(input_file, output_path, columns=columns, rows=rows, thumb_width=thumb_width)
    except Exception as exc:
        _fail(ctx, "contact_sheet", str(exc))
    if _out(ctx).json_mode:
        _out(ctx).emit("contact_sheet", output=result, columns=columns, rows=rows)
    else:
        _out(ctx)._out(f"Contact sheet: {result} ({columns}x{rows} = {columns * rows} thumbnails)")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", "output_srt", help="Output .srt file path")
@click.option("--model", default="base", type=click.Choice(["tiny", "base", "small", "medium", "large-v3"]))
@click.option("--language", "-l", help="Language code")
@click.pass_context
def transcribe(ctx, input_file, output_srt, model, language):
    """Transcribe speech to text with Whisper."""
    from declip.analyze import transcribe as do_transcribe
    output_srt = output_srt or str(Path(input_file).with_suffix(".srt"))
    try:
        result = do_transcribe(input_file, output_srt, model_size=model, language=language)
    except Exception as exc:
        _fail(ctx, "transcribe", str(exc))
    if _out(ctx).json_mode:
        _out(ctx).emit("transcribe", language=result.language, segments=len(result.subtitles), srt=result.srt_path, text=result.full_text[:1000])
    else:
        _out(ctx)._out(f"Language: {result.language}\nSegments: {len(result.subtitles)}\nSRT: {result.srt_path}\nText: {result.full_text[:200]}")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--threshold", default=0.3, help="Scene detection threshold")
@click.option("--output", "-o", help="Save chapters metadata file")
@click.pass_context
def chapters(ctx, input_file, threshold, output):
    """Generate chapter markers from scene cuts."""
    from declip.analyze import generate_chapters
    try:
        result = generate_chapters(input_file, threshold, output)
    except Exception as exc:
        _fail(ctx, "chapters", str(exc))
    if _out(ctx).json_mode:
        for chapter in result:
            _out(ctx).emit("chapter", index=chapter.index, start=chapter.start, end=chapter.end, title=chapter.title)
    else:
        lines = [f"{len(result)} chapter(s):"] + [f"  {chapter.index}. {chapter.start:.1f}s - {chapter.end:.1f}s: {chapter.title}" for chapter in result]
        if output:
            lines.append(f"Metadata: {output}")
        _out(ctx)._out("\n".join(lines))


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", help="Output PNG path")
@click.option("--width", default=1920, help="Image width")
@click.option("--height", default=200, help="Image height")
@click.option("--color", default="#00FF88", help="Waveform color")
@click.pass_context
def waveform(ctx, input_file, output, width, height, color):
    """Generate a waveform visualization as PNG."""
    from declip.analyze import waveform as do_waveform
    output = output or str(Path(input_file).stem + "_waveform.png")
    try:
        result = do_waveform(input_file, output, width, height, color)
    except Exception as exc:
        _fail(ctx, "waveform", str(exc))
    if _out(ctx).json_mode:
        _out(ctx).emit("waveform", output=result)
    else:
        _out(ctx)._out(f"Waveform: {result}")


@main.command()
@click.argument("video_file", type=click.Path(exists=True))
@click.option("--music-vol", default=0.3, help="Volume during speech")
@click.option("--normal-vol", default=1.0, help="Volume during silence")
@click.pass_context
def duck_filter(ctx, video_file, music_vol, normal_vol):
    """Generate an FFmpeg volume-expression ducking filter."""
    from declip.analyze import generate_duck_filter
    try:
        result = generate_duck_filter(video_file, music_vol, normal_vol)
    except Exception as exc:
        _fail(ctx, "duck_filter", str(exc))
    if _out(ctx).json_mode:
        _out(ctx).emit("duck_filter", filter=result)
    else:
        _out(ctx)._out(f"FFmpeg -af filter:\n{result}")


@main.command()
@click.argument("project_file", type=click.Path(exists=True))
@click.option("--output", "-o", help="Output .fcpxml path")
@click.pass_context
def export_fcpxml(ctx, project_file, output):
    """Export a project to FCPXML for Final Cut Pro."""
    from declip.analyze import export_fcpxml as do_export
    output = output or str(Path(project_file).with_suffix(".fcpxml"))
    try:
        result = do_export(project_file, output)
    except Exception as exc:
        _fail(ctx, "export_fcpxml", str(exc))
    if _out(ctx).json_mode:
        _out(ctx).emit("fcpxml", output=result)
    else:
        _out(ctx)._out(f"Exported: {result}")


@main.command()
@click.argument("project_files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--preset", type=click.Choice(list(PRESETS.keys())), help="Output preset")
@click.pass_context
def batch_render(ctx, project_files, preset):
    """Render multiple project files."""
    from declip import project_ops
    result = project_ops.batch_render(list(project_files), preset)
    _emit_text(ctx, "batch_complete", result, total=len(project_files))
    if any(line.startswith("FAILED:") for line in result.splitlines()):
        raise click.exceptions.Exit(1)


@main.command()
@click.argument("project_file", type=click.Path(exists=True))
@click.option("--backend", type=click.Choice(["auto", "ffmpeg", "mlt"]), default="auto")
@click.pass_context
def watch(ctx, project_file, backend):
    """Watch a project file and re-render on change."""
    from declip import project_ops
    out = _out(ctx)
    out.emit("watch", f"  Watching {project_file} for changes... (Ctrl+C to stop)")
    last_mtime = 0.0
    try:
        while True:
            mtime = Path(project_file).stat().st_mtime
            if mtime > last_mtime:
                last_mtime = mtime
                result = project_ops.render_project_file(project_file, backend=backend)
                if result.startswith("Rendered successfully"):
                    out.emit("watch_done", result)
                else:
                    out.emit("watch_error", result)
            time.sleep(1)
    except KeyboardInterrupt:
        out.emit("watch_stop", "  Stopped watching.")


# ---------------------------------------------------------------------------
# AI generation
# ---------------------------------------------------------------------------

@main.command()
@click.argument("prompt")
@click.option("--model", "-m", default="kling-3", help="Model name")
@click.option("--duration", "-d", default=5, type=int, help="Duration in seconds")
@click.option("--output", "-o", "output_path", help="Output file path")
@click.option("--image", "-i", "image_path", type=click.Path(exists=True), help="Start image")
@click.option("--end-image", type=click.Path(exists=True), help="End image")
@click.option("--aspect", default="16:9", type=click.Choice(["16:9", "9:16", "1:1"]))
@click.option("--audio/--no-audio", default=False, help="Generate audio")
@click.option("--negative", help="Negative prompt")
@click.option("--seed", type=int, help="Seed for reproducibility")
@click.option("--resolution", type=click.Choice(["480p", "720p", "1080p"]), help="Resolution")
@click.pass_context
def generate(ctx, prompt, model, duration, output_path, image_path, end_image, aspect, audio, negative, seed, resolution):
    """Generate a video clip using AI via fal.ai."""
    from declip.generate import generate_video
    if not output_path:
        safe = "".join(character if character.isalnum() else "_" for character in prompt[:30])
        output_path = f"gen_{safe}.mp4"
    try:
        result = generate_video(
            prompt=prompt, model=model, duration=duration, aspect_ratio=aspect,
            output_path=output_path, image_path=image_path, end_image_path=end_image,
            negative_prompt=negative, generate_audio=audio, seed=seed, resolution=resolution,
        )
    except Exception as exc:
        _fail(ctx, "generate", str(exc))
    if _out(ctx).json_mode:
        _out(ctx).emit("generated", video_url=result.video_url, local_path=result.local_path, model=result.model, estimated_cost=result.estimated_cost, seed=result.seed)
    else:
        lines = [f"Saved: {result.local_path}", f"Model: {result.model} | ~${result.estimated_cost:.3f}"]
        if result.seed is not None:
            lines.append(f"Seed: {result.seed}")
        _out(ctx)._out("\n".join(lines))


@main.command()
@click.option("--model", "-m", default="kling-3", help="Model name")
@click.option("--duration", "-d", default=5, type=int, help="Duration in seconds")
@click.option("--count", "-n", default=1, type=int, help="Number of clips")
@click.option("--audio/--no-audio", default=False, help="Include audio")
@click.pass_context
def estimate_cost(ctx, model, duration, count, audio):
    """Estimate generation cost without running anything."""
    from declip.generate import estimate_cost as do_estimate
    result = do_estimate(model=model, duration=duration, count=count, audio=audio)
    if _out(ctx).json_mode:
        _out(ctx).emit("estimate", **result)
    else:
        lines = [
            f"Model: {result['model']}",
            f"Duration: {result['duration_sec']}s x {result['clips']} clip(s)",
            f"Per clip: ${result['cost_per_clip']:.3f}",
            f"Total: ${result['total_cost']:.2f}",
        ]
        if result.get("audio_included"):
            lines.append("(includes audio generation)")
        _out(ctx)._out("\n".join(lines))


@main.command()
@click.pass_context
def models(ctx):
    """List available AI generation models and known pricing."""
    from declip.generate import list_models
    result = list_models()
    out = _out(ctx)
    for name, info in result.items():
        if out.json_mode:
            out.emit("model", name=name, **info)
        else:
            kind = {"text-to-video":"t2v", "image-to-video":"i2v", "video-to-video":"v2v"}.get(info.get("type"), "vid")
            cost = info.get("cost_per_sec")
            cost_text = f"${cost:.3f}/sec" if cost is not None else "$?/sec"
            out._out(f"{name:<28s} {kind:<4s} {cost_text}")


# ---------------------------------------------------------------------------
# Edit commands already backed by shared operations
# ---------------------------------------------------------------------------

def _run_op(ctx, stage: str, operation, *args, **kwargs):
    ok, message = operation(*args, **kwargs)
    if not ok:
        _fail(ctx, stage, message)
    _emit_text(ctx, "complete", message)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--target", "-t", default="youtube", help="Platform or LUFS target")
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def loudnorm(ctx, input_file, target, output_path):
    """Normalize audio loudness to a platform target."""
    from declip.ops import loudnorm as operation
    _run_op(ctx, "loudnorm", operation, input_file, target, output_path)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--strength", "-s", default="medium", type=click.Choice(["light", "medium", "heavy"]))
@click.option("--method", "-m", default="fft", type=click.Choice(["fft", "nlmeans"]))
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def denoise(ctx, input_file, strength, method, output_path):
    """Reduce audio noise."""
    from declip.ops import denoise as operation
    _run_op(ctx, "denoise", operation, input_file, strength, method, output_path)


@main.command()
@click.argument("video_file", type=click.Path(exists=True))
@click.argument("music_file", type=click.Path(exists=True))
@click.option("--threshold", default=0.02)
@click.option("--ratio", default=8.0)
@click.option("--attack", default=200.0)
@click.option("--release", default=1000.0)
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def sidechain(ctx, video_file, music_file, threshold, ratio, attack, release, output_path):
    """Auto-duck music under speech using sidechain compression."""
    from declip.ops import sidechain as operation
    _run_op(ctx, "sidechain", operation, video_file, music_file, threshold, ratio, attack, release, output_path)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--speed", "-s", default=2.0, type=float)
@click.option("--interpolate", is_flag=True)
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def speed(ctx, input_file, speed, interpolate, output_path):
    """Change video playback speed."""
    from declip.ops import speed as operation
    _run_op(ctx, "speed", operation, input_file, speed, interpolate, output_path)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--shakiness", default=5, type=int)
@click.option("--smoothing", default=10, type=int)
@click.option("--zoom", default=0.0, type=float)
@click.option("--tripod", is_flag=True)
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def stabilize(ctx, input_file, shakiness, smoothing, zoom, tripod, output_path):
    """Stabilize shaky video."""
    from declip.ops import stabilize as operation
    _run_op(ctx, "stabilize", operation, input_file, shakiness, smoothing, zoom, tripod, output_path)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def reverse(ctx, input_file, output_path):
    """Reverse a video, chunking long inputs."""
    from declip.ops import reverse as operation
    _run_op(ctx, "reverse", operation, input_file, output_path=output_path)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--temperature", default=0.0, type=float)
@click.option("--auto-levels", is_flag=True)
@click.option("--shadows-r", default=0.0, type=float)
@click.option("--shadows-g", default=0.0, type=float)
@click.option("--shadows-b", default=0.0, type=float)
@click.option("--midtones-r", default=0.0, type=float)
@click.option("--midtones-g", default=0.0, type=float)
@click.option("--midtones-b", default=0.0, type=float)
@click.option("--highlights-r", default=0.0, type=float)
@click.option("--highlights-g", default=0.0, type=float)
@click.option("--highlights-b", default=0.0, type=float)
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def color_grade(ctx, input_file, temperature, auto_levels, shadows_r, shadows_g, shadows_b, midtones_r, midtones_g, midtones_b, highlights_r, highlights_g, highlights_b, output_path):
    """Advanced color grading."""
    from declip.ops import color_grade as operation
    _run_op(
        ctx, "color_grade", operation, input_file, temperature,
        shadows_r, shadows_g, shadows_b,
        midtones_r, midtones_g, midtones_b,
        highlights_r, highlights_g, highlights_b,
        auto_levels, output_path,
    )


# ---------------------------------------------------------------------------
# Workflow commands
# ---------------------------------------------------------------------------

@main.group()
def workflow():
    """High-level workflows that orchestrate Declip capabilities."""
    pass


def _emit_workflow_result(ctx, result):
    _emit_model_result(ctx, "workflow", result)


@workflow.command(name="ingest")
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", default=None)
@click.option("--target", default="-14")
@click.option("--grade", is_flag=True)
@click.pass_context
def workflow_ingest(ctx, input_path, output_path, target, grade):
    """Probe + loudnorm + optional auto-grade."""
    from declip.workflows import ingest as module
    _emit_workflow_result(ctx, module.run(input_path=input_path, output_path=output_path, target=target, grade=grade))


@workflow.command(name="cutdown")
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", default=None)
@click.option("--target", "target_seconds", default=60.0, type=float)
@click.option("--transition", default="dissolve")
@click.option("--crossfade", "crossfade_duration", default=0.5, type=float)
@click.option("--segment-min", default=3.0, type=float)
@click.option("--segment-max", default=10.0, type=float)
@click.option("--scene-threshold", default=27.0, type=float)
@click.pass_context
def workflow_cutdown(ctx, input_path, output_path, target_seconds, transition, crossfade_duration, segment_min, segment_max, scene_threshold):
    """Create a highlight cutdown from a long source."""
    from declip.workflows import cutdown as module
    result = module.run(input_path=input_path, output_path=output_path, target_seconds=target_seconds, transition=transition, crossfade_duration=crossfade_duration, segment_min=segment_min, segment_max=segment_max, scene_threshold=scene_threshold)
    _emit_workflow_result(ctx, result)


@workflow.command(name="speech-cleanup")
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", default=None)
@click.option("--gap", default=0.5, type=float)
@click.option("--pad", default=0.1, type=float)
@click.option("--burn-captions", is_flag=True)
@click.option("--whisper-model", default="base")
@click.pass_context
def workflow_speech_cleanup(ctx, input_path, output_path, gap, pad, burn_captions, whisper_model):
    """Remove long speech gaps and optionally burn captions."""
    from declip.workflows import speech_cleanup as module
    _emit_workflow_result(ctx, module.run(input_path=input_path, output_path=output_path, gap=gap, pad=pad, burn_captions=burn_captions, whisper_model=whisper_model))


@workflow.command(name="beat-sync")
@click.argument("video_path", type=click.Path(exists=True))
@click.argument("music_path", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", default=None)
@click.option("--stride", default=1, type=int)
@click.option("--window", default=None, type=float)
@click.pass_context
def workflow_beat_sync(ctx, video_path, music_path, output_path, stride, window):
    """Cut video on the beats of a music track."""
    from declip.workflows import beat_sync as module
    _emit_workflow_result(ctx, module.run(video_path=video_path, music_path=music_path, output_path=output_path, stride=stride, window=window))


@workflow.command(name="vertical")
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", default=None)
@click.option("--mode", default="crop", type=click.Choice(["crop", "pad", "blur-pad"]))
@click.option("--width", default=1080, type=int)
@click.option("--height", default=1920, type=int)
@click.option("--bg", "background", default="#000000")
@click.option("--target", default="-14")
@click.option("--force", is_flag=True)
@click.pass_context
def workflow_vertical(ctx, input_path, output_path, mode, width, height, background, target, force):
    """Reframe video to a vertical target."""
    from declip.workflows import vertical as module
    _emit_workflow_result(ctx, module.run(input_path=input_path, output_path=output_path, mode=mode, width=width, height=height, background=background, target=target, force=force))


@workflow.command(name="review")
@click.argument("input_path", type=click.Path(exists=True))
@click.option("--output", "-o", "output_dir", default=None)
@click.option("--frames", "frame_count", default=16, type=int)
@click.option("--scene-threshold", default=27.0, type=float)
@click.pass_context
def workflow_review(ctx, input_path, output_dir, frame_count, scene_threshold):
    """Generate a QA report pack for a rendered video."""
    from declip.workflows import review as module
    _emit_workflow_result(ctx, module.run(input_path=input_path, output_dir=output_dir, frame_count=frame_count, scene_threshold=scene_threshold))


if __name__ == "__main__":
    main()
