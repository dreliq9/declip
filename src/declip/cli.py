"""Declip CLI — declarative video editing from the command line."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import click

from declip import __version__
from declip.output import OutputManager
from declip.schema import Project, PRESETS, PRESET_RESOLUTIONS


def _parse_vars(var_list: tuple[str, ...]) -> dict[str, str]:
    """Parse --var key=value pairs into a dict."""
    result = {}
    for v in var_list:
        if "=" not in v:
            click.echo(f"Warning: ignoring malformed --var '{v}' (expected key=value)", err=True)
            continue
        key, val = v.split("=", 1)
        result[key.strip()] = val.strip()
    return result


def _estimate_duration(project: Project, project_dir: Path) -> float | None:
    """Rough estimate of timeline duration from clip start + trim info."""
    max_end = 0.0
    for track in project.timeline.tracks:
        for clip in track.clips:
            if clip.duration is not None:
                end = clip.start + clip.duration
            elif clip.trim_out is not None:
                end = clip.start + (clip.trim_out - clip.trim_in)
            else:
                # Try to probe
                try:
                    from declip.probe import probe
                    p = Path(clip.asset)
                    if not p.is_absolute():
                        p = project_dir / p
                    info = probe(p)
                    end = clip.start + info.duration - clip.trim_in
                except Exception:
                    end = clip.start + 10  # guess
            max_end = max(max_end, end)
    return max_end if max_end > 0 else None


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
    out: OutputManager = ctx.obj["out"]
    try:
        project = Project.load(project_file)
    except Exception as e:
        out.error("validate", str(e))
        sys.exit(1)

    project_dir = Path(project_file).parent
    missing = []
    for track in project.timeline.tracks:
        for clip in track.clips:
            asset_path = Path(clip.asset)
            if not asset_path.is_absolute():
                asset_path = project_dir / asset_path
            if not asset_path.exists():
                missing.append(clip.asset)

    for audio in project.timeline.audio:
        asset_path = Path(audio.asset)
        if not asset_path.is_absolute():
            asset_path = project_dir / asset_path
        if not asset_path.exists():
            missing.append(audio.asset)

    if missing:
        out.error("validate", f"Missing assets: {', '.join(missing)}")
        sys.exit(1)

    tracks = len(project.timeline.tracks)
    clips = sum(len(t.clips) for t in project.timeline.tracks)
    out.emit("validate",
             f"Valid project: {tracks} track(s), {clips} clip(s)",
             valid=True, tracks=tracks, clips=clips,
             resolution=list(project.settings.resolution),
             fps=project.settings.fps)


@main.command()
@click.argument("project_file", type=click.Path(exists=True))
@click.option("--backend", type=click.Choice(["auto", "ffmpeg", "mlt"]), default="auto",
              help="Force a specific backend")
@click.option("--dry-run", is_flag=True, help="Show commands without rendering")
@click.option("--output", "-o", "output_path", help="Override output path")
@click.option("--preset", type=click.Choice(list(PRESETS.keys())), help="Use an output preset")
@click.option("--var", "variables", multiple=True, help="Template variable: key=value")
@click.pass_context
def render(ctx, project_file, backend, dry_run, output_path, preset, variables):
    """Render a project file to video."""
    from declip.backends import ffmpeg as ffmpeg_backend
    from declip.backends import mlt as mlt_backend

    out: OutputManager = ctx.obj["out"]
    project_dir = Path(project_file).parent
    var_dict = _parse_vars(variables)

    try:
        project = Project.load(project_file, variables=var_dict)
    except Exception as e:
        out.error("load", str(e))
        sys.exit(1)

    # Apply preset
    if preset:
        project.output = PRESETS[preset].model_copy()
        if preset in PRESET_RESOLUTIONS:
            project.settings.resolution = PRESET_RESOLUTIONS[preset]

    # Override output path (make absolute so _resolve_asset doesn't double it)
    if output_path:
        project.output.path = str(Path(output_path).resolve())

    out.emit("load", f"  Loaded: {project_file}", project=project_file)

    # Resolve any "auto" start values to actual timestamps
    project.resolve_auto_starts(project_dir)

    total_duration = _estimate_duration(project, project_dir)

    # Select backend
    if backend == "auto":
        use_ffmpeg = ffmpeg_backend.can_handle(project)
        chosen = "ffmpeg" if use_ffmpeg else "mlt"
    else:
        chosen = backend
        use_ffmpeg = (chosen == "ffmpeg")

    out.emit("backend", f"  Backend: {chosen}", backend=chosen)

    if dry_run:
        if use_ffmpeg:
            cmds = ffmpeg_backend.compile_commands(project, project_dir)
            for i, cmd in enumerate(cmds):
                out.emit("dry_run", f"  Command {i+1}: {' '.join(cmd)}",
                         step=i+1, command=cmd)
        else:
            xml_str = mlt_backend.compile_to_string(project, project_dir)
            out.emit("dry_run", f"  MLT XML ({len(xml_str)} bytes):\n{xml_str}",
                     xml=xml_str)
        return

    if use_ffmpeg:
        success = ffmpeg_backend.render(project, project_dir, out, total_duration)
    else:
        success = mlt_backend.render(project, project_dir, out, total_duration)

    if not success:
        sys.exit(1)


@main.command()
@click.argument("project_file", type=click.Path(exists=True))
@click.pass_context
def export_mlt(ctx, project_file):
    """Export a project as MLT XML (without rendering)."""
    from declip.backends import mlt as mlt_backend

    out: OutputManager = ctx.obj["out"]
    project_dir = Path(project_file).parent

    try:
        project = Project.load(project_file)
    except Exception as e:
        out.error("load", str(e))
        sys.exit(1)

    project.resolve_auto_starts(project_dir)
    xml_str = mlt_backend.compile_to_string(project, project_dir)
    if out.json_mode:
        out.emit("export", xml=xml_str)
    else:
        print(xml_str)


@main.command()
def init():
    """Create a minimal project.json template in the current directory."""
    template = {
        "version": "1.0",
        "settings": {
            "resolution": [1920, 1080],
            "fps": 30,
            "background": "#000000",
        },
        "timeline": {
            "tracks": [
                {
                    "id": "main",
                    "clips": [
                        {"asset": "input.mp4", "start": 0}
                    ],
                }
            ],
            "audio": [],
        },
        "output": {
            "path": "output.mp4",
            "format": "mp4",
            "codec": "h264",
            "quality": "high",
        },
    }

    out_path = Path("project.json")
    if out_path.exists():
        click.echo("project.json already exists — not overwriting.", err=True)
        sys.exit(1)

    out_path.write_text(json.dumps(template, indent=2))
    click.echo(f"Created {out_path}")


@main.command()
def presets():
    """List available output presets."""
    for name, preset in PRESETS.items():
        res = PRESET_RESOLUTIONS.get(name, (1920, 1080))
        click.echo(f"  {name:<20s} {res[0]}x{res[1]}  {preset.codec.value}  {preset.quality.value}")


# ---------------------------------------------------------------------------
# Quick commands (no JSON needed)
# ---------------------------------------------------------------------------

@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--in", "trim_in", type=float, required=True, help="Start time in seconds")
@click.option("--out", "trim_out", type=float, required=True, help="End time in seconds")
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def trim(ctx, input_file, trim_in, trim_out, output_path):
    """Trim a video to a time range. No project file needed."""
    out: OutputManager = ctx.obj["out"]

    if trim_out <= trim_in:
        out.error("trim", "out must be greater than in")
        sys.exit(1)

    if not output_path:
        p = Path(input_file)
        output_path = str(p.with_stem(p.stem + "_trimmed"))

    duration = trim_out - trim_in
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(trim_in),
        "-i", str(input_file),
        "-t", str(duration),
        "-c", "copy",
        output_path,
    ]

    out.emit("trim", f"  Trimming {trim_in}s - {trim_out}s ({duration:.1f}s)",
             input=input_file, trim_in=trim_in, trim_out=trim_out)

    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        out.error("trim", proc.stderr.decode(errors="replace")[-300:])
        sys.exit(1)

    size = Path(output_path).stat().st_size
    out.emit("complete", f"  Output: {output_path} ({size / 1024 / 1024:.1f} MB)",
             output=output_path, size_bytes=size)


@main.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", default="concat_output.mp4", help="Output file path")
@click.option("--preset", type=click.Choice(list(PRESETS.keys())), help="Output preset")
@click.pass_context
def concat(ctx, files, output_path, preset):
    """Concatenate multiple videos. No project file needed."""
    out: OutputManager = ctx.obj["out"]

    if len(files) < 2:
        out.error("concat", "Need at least 2 files to concatenate")
        sys.exit(1)

    # Build a project dynamically
    clips = []
    cursor = 0.0
    for f in files:
        from declip.probe import probe as probe_file
        try:
            info = probe_file(f)
            dur = info.duration
        except Exception:
            dur = 10.0

        clips.append({
            "asset": str(Path(f).resolve()),
            "start": cursor,
        })
        cursor += dur

    project_data = {
        "version": "1.0",
        "timeline": {"tracks": [{"id": "main", "clips": clips}]},
        "output": {"path": output_path},
    }

    if preset:
        p = PRESETS[preset]
        project_data["output"] = json.loads(p.model_dump_json(exclude_none=True))
        project_data["output"]["path"] = output_path
        if preset in PRESET_RESOLUTIONS:
            project_data["settings"] = {"resolution": list(PRESET_RESOLUTIONS[preset])}

    project = Project.model_validate(project_data)

    from declip.backends import ffmpeg as ffmpeg_backend
    out.emit("concat", f"  Concatenating {len(files)} files...", files=len(files))
    success = ffmpeg_backend.render(project, Path("."), out,
                                     total_duration=cursor)
    if not success:
        sys.exit(1)


# ---------------------------------------------------------------------------
# Media commands
# ---------------------------------------------------------------------------

@main.command()
@click.argument("files", nargs=-1, required=True, type=click.Path(exists=True))
@click.pass_context
def probe(ctx, files):
    """Probe media files and show their properties."""
    from declip.probe import probe as probe_file

    out: OutputManager = ctx.obj["out"]
    for f in files:
        try:
            info = probe_file(f)
            if out.json_mode:
                out.emit("probe", **info.to_dict())
            else:
                print(f"\n  {info.path}")
                print(f"  Duration: {info.duration:.1f}s")
                if info.width:
                    print(f"  Video:    {info.width}x{info.height} @ {info.fps:.1f}fps ({info.codec})")
                if info.audio_codec:
                    print(f"  Audio:    {info.audio_codec}, {info.audio_channels}ch, {info.audio_sample_rate}Hz")
                print(f"  Size:     {info.file_size / 1024 / 1024:.1f} MB")
        except Exception as e:
            out.error("probe", str(e))


@main.command()
@click.argument("project_file", type=click.Path(exists=True))
@click.pass_context
def assets(ctx, project_file):
    """List all assets in a project with their status and properties."""
    from declip.probe import probe as probe_file

    out: OutputManager = ctx.obj["out"]
    project_dir = Path(project_file).parent

    try:
        project = Project.load(project_file)
    except Exception as e:
        out.error("load", str(e))
        sys.exit(1)

    seen = set()
    total_size = 0
    total_duration = 0.0

    for track in project.timeline.tracks:
        for clip in track.clips:
            asset = clip.asset
            if asset in seen:
                continue
            seen.add(asset)

            asset_path = Path(asset)
            if not asset_path.is_absolute():
                asset_path = project_dir / asset_path

            if not asset_path.exists():
                if out.json_mode:
                    out.emit("asset", path=asset, status="missing")
                else:
                    print(f"  MISSING  {asset}")
                continue

            try:
                info = probe_file(asset_path)
                total_size += info.file_size
                total_duration += info.duration
                if out.json_mode:
                    out.emit("asset", status="ok", **info.to_dict())
                else:
                    size_mb = info.file_size / 1024 / 1024
                    print(f"  OK  {asset}  ({info.duration:.1f}s, {size_mb:.1f}MB, {info.codec})")
            except Exception as e:
                if out.json_mode:
                    out.emit("asset", path=asset, status="error", error=str(e))
                else:
                    print(f"  ERROR  {asset}: {e}")

    for audio in project.timeline.audio:
        asset = audio.asset
        if asset in seen:
            continue
        seen.add(asset)
        asset_path = Path(asset)
        if not asset_path.is_absolute():
            asset_path = project_dir / asset_path
        if asset_path.exists():
            try:
                info = probe_file(asset_path)
                total_size += info.file_size
                if out.json_mode:
                    out.emit("asset", status="ok", **info.to_dict())
                else:
                    size_mb = info.file_size / 1024 / 1024
                    print(f"  OK  {asset}  ({info.duration:.1f}s, {size_mb:.1f}MB, {info.audio_codec or 'unknown'})")
            except Exception as e:
                print(f"  ERROR  {asset}: {e}")
        else:
            print(f"  MISSING  {asset}")

    if not out.json_mode:
        print(f"\n  Total: {len(seen)} asset(s), {total_size / 1024 / 1024:.1f} MB, {total_duration:.1f}s source material")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--at", "timestamp", type=float, default=1.0, help="Timestamp in seconds")
@click.option("--output", "-o", "output_path", help="Output PNG path")
@click.pass_context
def thumbnail(ctx, input_file, timestamp, output_path):
    """Extract a single frame as PNG."""
    from declip.analyze import extract_frame

    out: OutputManager = ctx.obj["out"]
    if not output_path:
        output_path = str(Path(input_file).with_suffix(".png"))

    try:
        frame = extract_frame(input_file, timestamp, output_path)
        if out.json_mode:
            out.emit("thumbnail", path=frame.path, timestamp=frame.timestamp,
                     width=frame.width, height=frame.height)
        else:
            print(f"  Saved: {frame.path} ({frame.width}x{frame.height}, t={frame.timestamp:.2f}s)")
    except Exception as e:
        out.error("thumbnail", str(e))
        sys.exit(1)


# ---------------------------------------------------------------------------
# Analysis / review commands
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

    out: OutputManager = ctx.obj["out"]
    if not output_dir:
        output_dir = str(Path(input_file).stem + "_frames")

    ts_list = None
    if timestamps:
        ts_list = [float(t.strip()) for t in timestamps.split(",")]

    try:
        frames = do_extract(input_file, output_dir, count=count, timestamps=ts_list)
        if out.json_mode:
            for f in frames:
                out.emit("frame", path=f.path, timestamp=f.timestamp,
                         width=f.width, height=f.height)
        else:
            print(f"  Extracted {len(frames)} frames → {output_dir}/")
            for f in frames:
                print(f"    {f.timestamp:.2f}s → {Path(f.path).name}")
    except Exception as e:
        out.error("extract_frames", str(e))
        sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--threshold", default=0.3, help="Scene change threshold (0.0-1.0)")
@click.pass_context
def detect_scenes(ctx, input_file, threshold):
    """Detect scene changes in a video."""
    from declip.analyze import detect_scenes as do_detect

    out: OutputManager = ctx.obj["out"]
    try:
        cuts = do_detect(input_file, threshold=threshold)
        if out.json_mode:
            for c in cuts:
                out.emit("scene_cut", timestamp=c.timestamp, score=c.score)
            out.emit("summary", total_cuts=len(cuts))
        else:
            print(f"  Found {len(cuts)} scene cut(s):")
            for c in cuts:
                print(f"    {c.timestamp:.2f}s (score: {c.score:.3f})")
    except Exception as e:
        out.error("detect_scenes", str(e))
        sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--threshold", default="-30dB", help="Noise threshold (e.g., -30dB)")
@click.option("--min-duration", default=0.5, help="Minimum silence duration in seconds")
@click.pass_context
def detect_silence(ctx, input_file, threshold, min_duration):
    """Detect silent segments in audio/video."""
    from declip.analyze import detect_silence as do_detect

    out: OutputManager = ctx.obj["out"]
    try:
        segments = do_detect(input_file, noise_threshold=threshold, min_duration=min_duration)
        if out.json_mode:
            for s in segments:
                out.emit("silence", start=s.start, end=s.end, duration=s.duration)
            out.emit("summary", total_segments=len(segments))
        else:
            print(f"  Found {len(segments)} silent segment(s):")
            for s in segments:
                print(f"    {s.start:.2f}s - {s.end:.2f}s ({s.duration:.1f}s)")
    except Exception as e:
        out.error("detect_silence", str(e))
        sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output-dir", "-o", help="Directory for review output")
@click.option("--frames", "-n", default=16, help="Number of overview frames")
@click.option("--scene-threshold", default=0.3, help="Scene detection threshold")
@click.pass_context
def review(ctx, input_file, output_dir, frames, scene_threshold):
    """Full self-review pipeline: frames + scenes + silence + targeted cuts."""
    from declip.analyze import review as do_review

    out: OutputManager = ctx.obj["out"]
    if not output_dir:
        output_dir = str(Path(input_file).stem + "_review")

    out.emit("review", f"  Reviewing {input_file}...", input=input_file)

    try:
        result = do_review(
            input_file, output_dir,
            frame_count=frames,
            scene_threshold=scene_threshold,
        )
        if out.json_mode:
            out.emit("review_complete", **result.to_dict())
        else:
            print(result.summary())
    except Exception as e:
        out.error("review", str(e))
        sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.pass_context
def loudness(ctx, input_file):
    """Analyze audio loudness (EBU R128 / LUFS)."""
    from declip.analyze import analyze_loudness

    out: OutputManager = ctx.obj["out"]
    try:
        result = analyze_loudness(input_file)
        if out.json_mode:
            out.emit("loudness", **result.to_dict())
        else:
            print(f"  Integrated: {result.integrated_lufs} LUFS")
            print(f"  Loudness range: {result.loudness_range} LU")
            print(f"  True peak: {result.true_peak_dbtp} dBTP")
            if result.target_offset is not None:
                direction = "louder" if result.target_offset > 0 else "quieter"
                print(f"  Streaming target (-14 LUFS): {abs(result.target_offset):.1f} LU {direction}")
    except Exception as e:
        out.error("loudness", str(e))
        sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", help="Output file path")
@click.option("--format", "-f", "fmt", default="wav", type=click.Choice(["wav", "mp3", "flac", "aac"]))
@click.option("--sample-rate", "-r", type=int, help="Sample rate (e.g., 44100, 48000)")
@click.pass_context
def extract_audio(ctx, input_file, output_path, fmt, sample_rate):
    """Extract audio track from a video/audio file."""
    from declip.analyze import extract_audio as do_extract

    out: OutputManager = ctx.obj["out"]
    try:
        result = do_extract(input_file, output_path, format=fmt, sample_rate=sample_rate)
        size = Path(result).stat().st_size
        if out.json_mode:
            out.emit("extract_audio", output=result, size_bytes=size, format=fmt)
        else:
            print(f"  Extracted: {result} ({size / 1024 / 1024:.1f} MB)")
    except Exception as e:
        out.error("extract_audio", str(e))
        sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.pass_context
def detect_beats(ctx, input_file):
    """Detect beats and estimate tempo (BPM)."""
    from declip.analyze import detect_beats as do_detect

    out: OutputManager = ctx.obj["out"]
    try:
        result = do_detect(input_file)
        if out.json_mode:
            out.emit("beats", tempo=result.tempo, beat_count=result.beat_count,
                     beat_times=result.beat_times)
        else:
            print(f"  Tempo: {result.tempo} BPM")
            print(f"  Beats: {result.beat_count}")
            if result.beat_count <= 20:
                for t in result.beat_times:
                    print(f"    {t:.3f}s")
            else:
                for t in result.beat_times[:10]:
                    print(f"    {t:.3f}s")
                print(f"    ... and {result.beat_count - 10} more")
    except Exception as e:
        out.error("detect_beats", str(e))
        sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--at", "timestamp", type=float, help="Single timestamp to OCR")
@click.option("--count", "-n", default=5, help="Number of frames to OCR (if no --at)")
@click.option("--output-dir", "-o", help="Directory for extracted frames")
@click.option("--lang", default="eng", help="Tesseract language code")
@click.pass_context
def ocr(ctx, input_file, timestamp, count, output_dir, lang):
    """Read text from video frames using OCR."""
    from declip.analyze import ocr_frame, ocr_frames

    out: OutputManager = ctx.obj["out"]
    try:
        if timestamp is not None:
            result = ocr_frame(input_file, timestamp, output_dir, lang)
            if out.json_mode:
                out.emit("ocr", timestamp=result.timestamp, text=result.text,
                         frame_path=result.frame_path)
            else:
                print(f"  Frame at {result.timestamp:.2f}s:")
                if result.text:
                    for line in result.text.split("\n"):
                        print(f"    {line}")
                else:
                    print("    (no text detected)")
        else:
            results = ocr_frames(input_file, count=count, output_dir=output_dir, lang=lang)
            for r in results:
                if out.json_mode:
                    out.emit("ocr", timestamp=r.timestamp, text=r.text,
                             frame_path=r.frame_path)
                else:
                    text_preview = r.text[:80].replace("\n", " ") if r.text else "(no text)"
                    print(f"  {r.timestamp:.2f}s: {text_preview}")
    except Exception as e:
        out.error("ocr", str(e))
        sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", help="Output .mid file path")
@click.option("--threshold", default=0.5, help="Pitch confidence threshold (0.0-1.0)")
@click.pass_context
def audio_to_midi(ctx, input_file, output_path, threshold):
    """Transcribe audio to MIDI (pYIN pitch detection + onset detection)."""
    from declip.analyze import audio_to_midi as do_convert

    out: OutputManager = ctx.obj["out"]
    try:
        result = do_convert(input_file, output_path, confidence_threshold=threshold)
        if out.json_mode:
            out.emit("midi", note_count=result.note_count, duration=result.duration,
                     output=result.output_path)
        else:
            print(f"  Notes: {result.note_count}")
            print(f"  Duration: {result.duration:.1f}s")
            if result.output_path:
                print(f"  MIDI file: {result.output_path}")
    except Exception as e:
        out.error("audio_to_midi", str(e))
        sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.pass_context
def streams(ctx, input_file):
    """List all streams in a media file (video, audio, subtitle tracks)."""
    from declip.analyze import list_streams
    from dataclasses import asdict

    out: OutputManager = ctx.obj["out"]
    try:
        result = list_streams(input_file)
        for s in result:
            if out.json_mode:
                out.emit("stream", **{k: v for k, v in asdict(s).items() if v is not None})
            else:
                lang = f" [{s.language}]" if s.language else ""
                if s.type == "video":
                    print(f"  #{s.index} video: {s.codec} {s.width}x{s.height} @ {s.fps:.1f}fps{lang}")
                elif s.type == "audio":
                    layout = f" ({s.channel_layout})" if s.channel_layout else ""
                    print(f"  #{s.index} audio: {s.codec} {s.channels}ch {s.sample_rate}Hz{layout}{lang}")
                else:
                    print(f"  #{s.index} {s.type}: {s.codec}{lang}")
    except Exception as e:
        out.error("streams", str(e))
        sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", help="Output image path (PNG/JPG)")
@click.option("--columns", default=4, help="Grid columns")
@click.option("--rows", default=4, help="Grid rows")
@click.option("--thumb-width", default=480, help="Width of each thumbnail")
@click.pass_context
def contact_sheet(ctx, input_file, output_path, columns, rows, thumb_width):
    """Generate a contact sheet (thumbnail grid) from a video."""
    from declip.analyze import contact_sheet as do_sheet

    out: OutputManager = ctx.obj["out"]
    if not output_path:
        output_path = str(Path(input_file).stem + "_contact.png")

    try:
        result = do_sheet(input_file, output_path, columns=columns, rows=rows,
                          thumb_width=thumb_width)
        if out.json_mode:
            out.emit("contact_sheet", output=result, columns=columns, rows=rows)
        else:
            total = columns * rows
            print(f"  Contact sheet: {result} ({columns}x{rows} = {total} thumbnails)")
    except Exception as e:
        out.error("contact_sheet", str(e))
        sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", "output_srt", help="Output .srt file path")
@click.option("--model", default="base", type=click.Choice(["tiny", "base", "small", "medium", "large-v3"]))
@click.option("--language", "-l", help="Language code (auto-detect if omitted)")
@click.pass_context
def transcribe(ctx, input_file, output_srt, model, language):
    """Transcribe speech to text (Whisper). Optionally saves .srt subtitles."""
    from declip.analyze import transcribe as do_transcribe

    out: OutputManager = ctx.obj["out"]
    if not output_srt:
        output_srt = str(Path(input_file).with_suffix(".srt"))

    try:
        result = do_transcribe(input_file, output_srt, model_size=model, language=language)
        if out.json_mode:
            out.emit("transcribe", language=result.language,
                     segments=len(result.subtitles), srt=result.srt_path,
                     text=result.full_text[:1000])
        else:
            print(f"  Language: {result.language}")
            print(f"  Segments: {len(result.subtitles)}")
            print(f"  SRT: {result.srt_path}")
            print(f"  Text: {result.full_text[:200]}")
    except Exception as e:
        out.error("transcribe", str(e))
        sys.exit(1)


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--threshold", default=0.3, help="Scene detection threshold")
@click.option("--output", "-o", help="Save chapters metadata file")
@click.pass_context
def chapters(ctx, input_file, threshold, output):
    """Generate chapter markers from scene cuts."""
    from declip.analyze import generate_chapters

    out: OutputManager = ctx.obj["out"]
    try:
        result = generate_chapters(input_file, threshold, output)
        if out.json_mode:
            for ch in result:
                out.emit("chapter", index=ch.index, start=ch.start,
                         end=ch.end, title=ch.title)
        else:
            print(f"  {len(result)} chapter(s):")
            for ch in result:
                dur = ch.end - ch.start
                print(f"    {ch.index}. {ch.start:.1f}s - {ch.end:.1f}s ({dur:.1f}s) {ch.title}")
            if output:
                print(f"  Metadata: {output}")
    except Exception as e:
        out.error("chapters", str(e))
        sys.exit(1)


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

    out: OutputManager = ctx.obj["out"]
    if not output:
        output = str(Path(input_file).stem + "_waveform.png")

    try:
        result = do_waveform(input_file, output, width, height, color)
        if out.json_mode:
            out.emit("waveform", output=result)
        else:
            print(f"  Waveform: {result}")
    except Exception as e:
        out.error("waveform", str(e))
        sys.exit(1)


@main.command()
@click.argument("video_file", type=click.Path(exists=True))
@click.option("--music-vol", default=0.3, help="Volume during speech (0.0-1.0)")
@click.option("--normal-vol", default=1.0, help="Volume during silence (0.0-1.0)")
@click.pass_context
def duck_filter(ctx, video_file, music_vol, normal_vol):
    """Generate FFmpeg audio ducking filter from speech detection."""
    from declip.analyze import generate_duck_filter

    out: OutputManager = ctx.obj["out"]
    try:
        filt = generate_duck_filter(video_file, music_vol, normal_vol)
        if out.json_mode:
            out.emit("duck_filter", filter=filt)
        else:
            print(f"  FFmpeg -af filter:\n  {filt}")
    except Exception as e:
        out.error("duck_filter", str(e))
        sys.exit(1)


@main.command()
@click.argument("project_file", type=click.Path(exists=True))
@click.option("--output", "-o", help="Output .fcpxml path")
@click.pass_context
def export_fcpxml(ctx, project_file, output):
    """Export a project to FCPXML for Final Cut Pro."""
    from declip.analyze import export_fcpxml as do_export

    out: OutputManager = ctx.obj["out"]
    if not output:
        output = str(Path(project_file).with_suffix(".fcpxml"))

    try:
        result = do_export(project_file, output)
        if out.json_mode:
            out.emit("fcpxml", output=result)
        else:
            print(f"  Exported: {result}")
    except Exception as e:
        out.error("export_fcpxml", str(e))
        sys.exit(1)


@main.command()
@click.argument("project_files", nargs=-1, required=True, type=click.Path(exists=True))
@click.option("--preset", type=click.Choice(list(PRESETS.keys())), help="Output preset")
@click.pass_context
def batch_render(ctx, project_files, preset):
    """Render multiple project files."""
    from declip.backends import ffmpeg as ffmpeg_backend
    from declip.backends import mlt as mlt_backend

    out: OutputManager = ctx.obj["out"]
    total = len(project_files)

    for i, pf in enumerate(project_files):
        out.emit("batch", f"  [{i+1}/{total}] {pf}...", step=i+1, total=total)
        try:
            project = Project.load(pf)
            project_dir = Path(pf).parent
            project.resolve_auto_starts(project_dir)

            if preset:
                project.output = PRESETS[preset].model_copy()
                if preset in PRESET_RESOLUTIONS:
                    project.settings.resolution = PRESET_RESOLUTIONS[preset]

            render_out = OutputManager(json_mode=False, quiet=True)
            use_ffmpeg = ffmpeg_backend.can_handle(project)
            if use_ffmpeg:
                success = ffmpeg_backend.render(project, project_dir, render_out)
            else:
                success = mlt_backend.render(project, project_dir, render_out)

            status = "OK" if success else "FAILED"
            out.emit("batch_result", f"    {status}: {project.output.path}",
                     file=pf, status=status)
        except Exception as e:
            out.emit("batch_result", f"    ERROR: {e}", file=pf, status="error")

    out.emit("batch_complete", f"  Done: {total} project(s)", total=total)


@main.command()
@click.argument("project_file", type=click.Path(exists=True))
@click.option("--backend", type=click.Choice(["auto", "ffmpeg", "mlt"]), default="auto")
@click.pass_context
def watch(ctx, project_file, backend):
    """Watch a project file and re-render on change."""
    from declip.backends import ffmpeg as ffmpeg_backend
    from declip.backends import mlt as mlt_backend
    import time as _time

    out: OutputManager = ctx.obj["out"]
    project_dir = Path(project_file).parent

    out.emit("watch", f"  Watching {project_file} for changes... (Ctrl+C to stop)")

    last_mtime = 0.0
    try:
        while True:
            mtime = Path(project_file).stat().st_mtime
            if mtime > last_mtime:
                last_mtime = mtime
                out.emit("watch_trigger", f"  Change detected, rendering...")
                try:
                    project = Project.load(project_file)
                    render_out = OutputManager(json_mode=False, quiet=True)

                    if backend == "auto":
                        use_ffmpeg = ffmpeg_backend.can_handle(project)
                    else:
                        use_ffmpeg = (backend == "ffmpeg")

                    if use_ffmpeg:
                        success = ffmpeg_backend.render(project, project_dir, render_out)
                    else:
                        success = mlt_backend.render(project, project_dir, render_out)

                    if success:
                        out.emit("watch_done", f"  Rendered: {project.output.path}")
                    else:
                        out.emit("watch_error", f"  Render failed")
                except Exception as e:
                    out.emit("watch_error", f"  Error: {e}")

            _time.sleep(1)
    except KeyboardInterrupt:
        out.emit("watch_stop", "  Stopped watching.")


# ---------------------------------------------------------------------------
# AI video generation (fal.ai)
# ---------------------------------------------------------------------------

@main.command()
@click.argument("prompt")
@click.option("--model", "-m", default="kling-3", help="Model name (kling-3, wan-2.5, ltx, etc.)")
@click.option("--duration", "-d", default=5, type=int, help="Duration in seconds")
@click.option("--output", "-o", "output_path", help="Output file path")
@click.option("--image", "-i", "image_path", type=click.Path(exists=True), help="Start image for image-to-video")
@click.option("--end-image", type=click.Path(exists=True), help="End image (Kling only)")
@click.option("--aspect", default="16:9", type=click.Choice(["16:9", "9:16", "1:1"]))
@click.option("--audio/--no-audio", default=False, help="Generate audio (Kling 3.0)")
@click.option("--negative", help="Negative prompt")
@click.option("--seed", type=int, help="Seed for reproducibility")
@click.option("--resolution", type=click.Choice(["480p", "720p", "1080p"]), help="Resolution (Wan models)")
@click.pass_context
def generate(ctx, prompt, model, duration, output_path, image_path, end_image,
             aspect, audio, negative, seed, resolution):
    """Generate a video clip using AI (fal.ai). Requires FAL_KEY env var."""
    from declip.generate import generate_video

    out: OutputManager = ctx.obj["out"]
    if not output_path:
        safe = "".join(c if c.isalnum() else "_" for c in prompt[:30])
        output_path = f"gen_{safe}.mp4"

    out.emit("generate", f"  Generating {duration}s video via {model}...",
             model=model, duration=duration)

    try:
        result = generate_video(
            prompt=prompt, model=model, duration=duration,
            aspect_ratio=aspect, output_path=output_path,
            image_path=image_path, end_image_path=end_image,
            negative_prompt=negative, generate_audio=audio,
            seed=seed, resolution=resolution,
        )
        if out.json_mode:
            out.emit("generated", video_url=result.video_url,
                     local_path=result.local_path, model=result.model,
                     estimated_cost=result.estimated_cost, seed=result.seed)
        else:
            print(f"  Saved: {result.local_path}")
            print(f"  Model: {result.model} | ~${result.estimated_cost:.3f}")
            if result.seed is not None:
                print(f"  Seed: {result.seed}")
    except Exception as e:
        out.error("generate", str(e))
        sys.exit(1)


@main.command()
@click.option("--model", "-m", default="kling-3", help="Model name")
@click.option("--duration", "-d", default=5, type=int, help="Duration in seconds")
@click.option("--count", "-n", default=1, type=int, help="Number of clips")
@click.option("--audio/--no-audio", default=False, help="Include audio")
@click.pass_context
def estimate_cost(ctx, model, duration, count, audio):
    """Estimate generation cost without running anything."""
    from declip.generate import estimate_cost as do_estimate

    out: OutputManager = ctx.obj["out"]
    result = do_estimate(model=model, duration=duration, count=count, audio=audio)
    if out.json_mode:
        out.emit("estimate", **result)
    else:
        print(f"  Model: {result['model']}")
        print(f"  Duration: {result['duration_sec']}s x {result['clips']} clip(s)")
        print(f"  Per clip: ${result['cost_per_clip']:.3f}")
        print(f"  Total: ${result['total_cost']:.2f}")
        if result['audio_included']:
            print(f"  (includes audio generation)")


@main.command()
@click.pass_context
def models(ctx):
    """List available AI video generation models with pricing."""
    from declip.generate import list_models

    out: OutputManager = ctx.obj["out"]
    result = list_models()
    for name, info in result.items():
        if out.json_mode:
            out.emit("model", name=name, **info)
        else:
            type_tag = "i2v" if info["type"] == "image-to-video" else "t2v"
            print(f"  {name:<20s} {type_tag}  ${info['cost_per_sec']:.3f}/sec  (${info['cost_5sec']:.2f}/5s)")


# ---------------------------------------------------------------------------
# Edit commands (quick operations, no project file needed)
# ---------------------------------------------------------------------------

@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--target", "-t", default="youtube",
              help="Platform target: youtube (-14 LUFS), tiktok (-11), podcast (-16), broadcast (-23), or custom like '-18'")
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def loudnorm(ctx, input_file, target, output_path):
    """Normalize audio loudness to a platform target (two-pass)."""
    from declip.ops import loudnorm as _loudnorm
    out: OutputManager = ctx.obj["out"]
    out.emit("loudnorm", f"  Normalizing to {target}...")
    ok, msg = _loudnorm(input_file, target, output_path)
    if not ok:
        out.error("loudnorm", msg)
        sys.exit(1)
    out.emit("complete", f"  {msg}")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--strength", "-s", default="medium", type=click.Choice(["light", "medium", "heavy"]))
@click.option("--method", "-m", default="fft", type=click.Choice(["fft", "nlmeans"]))
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def denoise(ctx, input_file, strength, method, output_path):
    """Reduce audio noise (FFT-based or non-local means)."""
    from declip.ops import denoise as _denoise
    out: OutputManager = ctx.obj["out"]
    out.emit("denoise", f"  Denoising ({method}, {strength})...")
    ok, msg = _denoise(input_file, strength, method, output_path)
    if not ok:
        out.error("denoise", msg)
        sys.exit(1)
    out.emit("complete", f"  {msg}")


@main.command()
@click.argument("video_file", type=click.Path(exists=True))
@click.argument("music_file", type=click.Path(exists=True))
@click.option("--threshold", default=0.02, help="Compression threshold (0.0-1.0)")
@click.option("--ratio", default=8.0, help="Compression ratio")
@click.option("--attack", default=200.0, help="Attack time in ms")
@click.option("--release", default=1000.0, help="Release time in ms")
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def sidechain(ctx, video_file, music_file, threshold, ratio, attack, release, output_path):
    """Auto-duck music under speech using sidechain compression."""
    from declip.ops import sidechain as _sidechain
    out: OutputManager = ctx.obj["out"]
    out.emit("sidechain", f"  Ducking music under speech...")
    ok, msg = _sidechain(video_file, music_file, threshold, ratio, attack, release, output_path)
    if not ok:
        out.error("sidechain", msg)
        sys.exit(1)
    out.emit("complete", f"  {msg}")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--speed", "-s", default=2.0, type=float, help="Speed multiplier (0.25-100)")
@click.option("--interpolate", is_flag=True, help="Use optical-flow interpolation for smooth slow-mo")
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def speed(ctx, input_file, speed, interpolate, output_path):
    """Change video playback speed. <1.0 = slow-mo, >1.0 = fast."""
    from declip.ops import speed as _speed
    out: OutputManager = ctx.obj["out"]
    out.emit("speed", f"  Changing speed to {speed}x...")
    ok, msg = _speed(input_file, speed, interpolate, output_path)
    if not ok:
        out.error("speed", msg)
        sys.exit(1)
    out.emit("complete", f"  {msg}")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--shakiness", default=5, type=int, help="Detection sensitivity 1-10")
@click.option("--smoothing", default=10, type=int, help="Smoothing strength in frames")
@click.option("--zoom", default=0.0, type=float, help="Zoom % to hide borders")
@click.option("--tripod", is_flag=True, help="Lock to single reference frame")
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def stabilize(ctx, input_file, shakiness, smoothing, zoom, tripod, output_path):
    """Stabilize shaky video (two-pass vidstab)."""
    from declip.ops import stabilize as _stabilize
    out: OutputManager = ctx.obj["out"]
    out.emit("stabilize", f"  Stabilizing...")
    ok, msg = _stabilize(input_file, shakiness, smoothing, zoom, tripod, output_path)
    if not ok:
        out.error("stabilize", msg)
        sys.exit(1)
    out.emit("complete", f"  {msg}")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def reverse(ctx, input_file, output_path):
    """Reverse a video. Auto-chunks long videos to avoid memory issues."""
    from declip.ops import reverse as _reverse
    out: OutputManager = ctx.obj["out"]
    out.emit("reverse", f"  Reversing...")
    ok, msg = _reverse(input_file, output_path=output_path)
    if not ok:
        out.error("reverse", msg)
        sys.exit(1)
    out.emit("complete", f"  {msg}")


@main.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--temperature", default=0.0, type=float, help="White balance -1.0 (cool) to 1.0 (warm)")
@click.option("--auto-levels", is_flag=True, help="Auto-normalize color levels")
@click.option("--shadows-r", default=0.0, type=float, help="Shadow red (-1 to 1)")
@click.option("--shadows-g", default=0.0, type=float, help="Shadow green (-1 to 1)")
@click.option("--shadows-b", default=0.0, type=float, help="Shadow blue (-1 to 1)")
@click.option("--midtones-r", default=0.0, type=float, help="Midtone red (-1 to 1)")
@click.option("--midtones-g", default=0.0, type=float, help="Midtone green (-1 to 1)")
@click.option("--midtones-b", default=0.0, type=float, help="Midtone blue (-1 to 1)")
@click.option("--highlights-r", default=0.0, type=float, help="Highlight red (-1 to 1)")
@click.option("--highlights-g", default=0.0, type=float, help="Highlight green (-1 to 1)")
@click.option("--highlights-b", default=0.0, type=float, help="Highlight blue (-1 to 1)")
@click.option("--output", "-o", "output_path", help="Output file path")
@click.pass_context
def color_grade(ctx, input_file, temperature, auto_levels,
                shadows_r, shadows_g, shadows_b,
                midtones_r, midtones_g, midtones_b,
                highlights_r, highlights_g, highlights_b,
                output_path):
    """Advanced color grading — color balance, white balance, auto-levels."""
    from declip.ops import color_grade as _color_grade
    out: OutputManager = ctx.obj["out"]
    out.emit("color_grade", f"  Grading...")
    ok, msg = _color_grade(
        input_file, temperature,
        shadows_r, shadows_g, shadows_b,
        midtones_r, midtones_g, midtones_b,
        highlights_r, highlights_g, highlights_b,
        auto_levels, output_path,
    )
    if not ok:
        out.error("color_grade", msg)
        sys.exit(1)
    out.emit("complete", f"  {msg}")


if __name__ == "__main__":
    main()
