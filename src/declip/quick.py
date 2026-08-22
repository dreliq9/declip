"""Reusable quick media operations with structured results."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from declip.results import ConcatResult, ProbeResult, ThumbnailResult, TrimResult


def probe(file_path: str) -> ProbeResult:
    from declip.probe import probe as inspect_media
    try:
        info = inspect_media(file_path)
    except Exception as exc:
        return ProbeResult(path=file_path, duration_seconds=0.0, file_size_bytes=0, error=str(exc))
    return ProbeResult(
        path=info.path, duration_seconds=info.duration, file_size_bytes=info.file_size,
        width=info.width, height=info.height, fps=info.fps, video_codec=info.codec,
        pixel_format=info.pixel_format, bit_depth=info.bit_depth, is_hdr=info.is_hdr,
        video_bitrate_bps=info.video_bitrate, color_space=info.color_space,
        color_primaries=info.color_primaries, color_transfer=info.color_transfer,
        audio_codec=info.audio_codec, audio_channels=info.audio_channels,
        audio_sample_rate=info.audio_sample_rate, audio_bitrate_bps=info.audio_bitrate,
    )


def _run(command: list[str], timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run(command, capture_output=True, timeout=timeout)


def _full_reencode(input_file: str, trim_in: float, duration: float, output_path: str) -> tuple[bool, str]:
    command = ["ffmpeg", "-y", "-ss", str(trim_in), "-i", str(input_file), "-t", str(duration), "-avoid_negative_ts", "make_zero", output_path]
    try:
        proc = _run(command)
    except subprocess.TimeoutExpired:
        return False, "full re-encode timed out"
    if proc.returncode != 0:
        return False, proc.stderr.decode(errors="replace")[-300:]
    return True, ""


def trim(input_file: str, trim_in: float, trim_out: float, smart: bool = False, output_path: str | None = None) -> TrimResult:
    if trim_in < 0 or trim_out <= trim_in:
        return TrimResult(success=False, trim_in_seconds=trim_in, trim_out_seconds=trim_out, duration_seconds=max(0.0, trim_out - trim_in), smart=smart, error="trim_out must be greater than trim_in and trim_in non-negative")
    if not Path(input_file).exists():
        return TrimResult(success=False, trim_in_seconds=trim_in, trim_out_seconds=trim_out, duration_seconds=trim_out - trim_in, smart=smart, error=f"{input_file} not found")
    if not output_path:
        source = Path(input_file); output_path = str(source.with_stem(source.stem + "_trimmed"))
    duration = trim_out - trim_in
    if not smart:
        command = ["ffmpeg", "-y", "-ss", str(trim_in), "-i", str(input_file), "-t", str(duration), "-c", "copy", "-avoid_negative_ts", "make_zero", output_path]
        try: proc = _run(command)
        except subprocess.TimeoutExpired:
            return TrimResult(success=False, trim_in_seconds=trim_in, trim_out_seconds=trim_out, duration_seconds=duration, smart=False, error="trim timed out")
        if proc.returncode != 0:
            return TrimResult(success=False, trim_in_seconds=trim_in, trim_out_seconds=trim_out, duration_seconds=duration, smart=False, error=proc.stderr.decode(errors="replace")[-300:])
        return TrimResult(success=True, output_path=output_path, file_size_bytes=Path(output_path).stat().st_size, trim_in_seconds=trim_in, trim_out_seconds=trim_out, duration_seconds=duration, smart=False)

    probe_command = ["ffprobe", "-v", "quiet", "-select_streams", "v:0", "-show_entries", "packet=pts_time,flags", "-of", "csv=p=0", "-read_intervals", f"{trim_in}%{min(trim_in + 15, trim_out)}", str(input_file)]
    try:
        keyframes = subprocess.run(probe_command, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        keyframes = None
    next_keyframe = None
    if keyframes is not None and keyframes.returncode == 0:
        for line in keyframes.stdout.splitlines():
            parts = line.strip().split(",")
            if len(parts) < 2: continue
            try: pts = float(parts[0])
            except ValueError: continue
            if "K" in parts[1] and pts > trim_in + 0.01:
                next_keyframe = pts; break
    if next_keyframe is None or next_keyframe >= trim_out:
        ok, error = _full_reencode(input_file, trim_in, duration, output_path)
        return TrimResult(success=ok, output_path=output_path if ok else None, file_size_bytes=Path(output_path).stat().st_size if ok else None, trim_in_seconds=trim_in, trim_out_seconds=trim_out, duration_seconds=duration, smart=True, fallback_full_re_encode=True, error=None if ok else error)

    head_duration = next_keyframe - trim_in
    tail_duration = trim_out - next_keyframe
    temporary_paths: list[str] = []
    try:
        with tempfile.NamedTemporaryFile(suffix=Path(output_path).suffix or ".mp4", delete=False) as handle: head_path = handle.name
        with tempfile.NamedTemporaryFile(suffix=Path(output_path).suffix or ".mp4", delete=False) as handle: tail_path = handle.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as handle: list_path = handle.name
        temporary_paths = [head_path, tail_path, list_path]
        head = _run(["ffmpeg", "-y", "-ss", str(trim_in), "-i", str(input_file), "-t", str(head_duration), "-avoid_negative_ts", "make_zero", head_path])
        tail = _run(["ffmpeg", "-y", "-ss", str(next_keyframe), "-i", str(input_file), "-t", str(tail_duration), "-c", "copy", "-avoid_negative_ts", "make_zero", tail_path])
        if head.returncode == 0 and tail.returncode == 0:
            Path(list_path).write_text(f"file '{Path(head_path).resolve()}'\nfile '{Path(tail_path).resolve()}'\n", encoding="utf-8")
            joined = _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", "-avoid_negative_ts", "make_zero", output_path])
            if joined.returncode == 0:
                return TrimResult(success=True, output_path=output_path, file_size_bytes=Path(output_path).stat().st_size, trim_in_seconds=trim_in, trim_out_seconds=trim_out, duration_seconds=duration, smart=True, re_encoded_head_seconds=head_duration, stream_copied_tail_seconds=tail_duration)
        ok, error = _full_reencode(input_file, trim_in, duration, output_path)
        return TrimResult(success=ok, output_path=output_path if ok else None, file_size_bytes=Path(output_path).stat().st_size if ok else None, trim_in_seconds=trim_in, trim_out_seconds=trim_out, duration_seconds=duration, smart=True, fallback_full_re_encode=True, error=None if ok else error)
    except subprocess.TimeoutExpired:
        ok, error = _full_reencode(input_file, trim_in, duration, output_path)
        return TrimResult(success=ok, output_path=output_path if ok else None, file_size_bytes=Path(output_path).stat().st_size if ok else None, trim_in_seconds=trim_in, trim_out_seconds=trim_out, duration_seconds=duration, smart=True, fallback_full_re_encode=True, error=None if ok else error)
    finally:
        for path in temporary_paths:
            try: os.unlink(path)
            except OSError: pass


def concat(files: list[str], output_path: str = "concat_output.mp4", preset: str | None = None) -> ConcatResult:
    from declip.probe import probe as inspect_media
    from declip.schema import PRESETS, PRESET_RESOLUTIONS, Project
    from declip.backends import ffmpeg as ffmpeg_backend
    from declip.output import OutputManager
    if len(files) < 2:
        return ConcatResult(success=False, file_count=len(files), error="Need at least 2 files to concatenate")
    missing = [path for path in files if not Path(path).exists()]
    if missing:
        return ConcatResult(success=False, file_count=len(files), error=f"Missing files: {', '.join(missing)}")
    if preset and preset not in PRESETS:
        return ConcatResult(success=False, file_count=len(files), error=f"Unknown preset '{preset}'")
    infos = []
    for path in files:
        try: infos.append(inspect_media(path))
        except Exception: infos.append(None)
    valid = [info for info in infos if info is not None]
    stream_copy = (
        len(valid) == len(files) and preset is None
        and len({info.codec for info in valid}) == 1
        and len({(info.width, info.height) for info in valid}) == 1
        and len({round(info.fps, 2) for info in valid if info.fps}) <= 1
        and len({info.audio_codec for info in valid}) <= 1
    )
    if stream_copy:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as handle:
            list_path = handle.name
            for path in files: handle.write(f"file '{Path(path).resolve()}'\n")
        try:
            proc = _run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_path, "-c", "copy", "-avoid_negative_ts", "make_zero", output_path])
            if proc.returncode == 0:
                return ConcatResult(success=True, output_path=output_path, file_size_bytes=Path(output_path).stat().st_size, file_count=len(files), method="stream-copy")
        finally:
            try: os.unlink(list_path)
            except OSError: pass
    clips, cursor = [], 0.0
    for index, path in enumerate(files):
        duration = infos[index].duration if infos[index] else 10.0
        clips.append({"asset":str(Path(path).resolve()),"start":cursor,"duration":duration})
        cursor += duration
    project_data: dict = {"version":"1.0","timeline":{"tracks":[{"id":"main","clips":clips}]},"output":{"path":str(Path(output_path).resolve())}}
    if preset:
        project_data["output"] = json.loads(PRESETS[preset].model_dump_json(exclude_none=True)); project_data["output"]["path"] = str(Path(output_path).resolve())
        if preset in PRESET_RESOLUTIONS: project_data["settings"] = {"resolution":list(PRESET_RESOLUTIONS[preset])}
    project = Project.model_validate(project_data)
    out = OutputManager(json_mode=False, quiet=True)
    success = ffmpeg_backend.render(project, Path("."), out, total_duration=cursor)
    if success:
        return ConcatResult(success=True, output_path=output_path, file_size_bytes=Path(output_path).stat().st_size if Path(output_path).exists() else 0, file_count=len(files), method="re-encoded")
    return ConcatResult(success=False, file_count=len(files), method="re-encoded", error=out.get_log().strip() or "concatenation failed")


def thumbnail(input_file: str, timestamp: float = 1.0, output_path: str | None = None) -> ThumbnailResult:
    from declip.analyze import extract_frame
    if timestamp < 0:
        return ThumbnailResult(success=False, error="timestamp must be non-negative")
    if not output_path:
        output_path = str(Path(input_file).with_suffix(".png"))
    try:
        frame = extract_frame(input_file, timestamp, output_path)
        return ThumbnailResult(success=True, output_path=frame.path, timestamp_seconds=frame.timestamp, width=frame.width, height=frame.height)
    except Exception as exc:
        return ThumbnailResult(success=False, error=str(exc))
