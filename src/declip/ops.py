"""Shared operations — single implementations called by both MCP tools and CLI.

Each function takes file paths + parameters, runs FFmpeg, and returns
(success: bool, message: str). On success, message describes the output.
On failure, message contains the error.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import tempfile
from pathlib import Path


def _run(cmd: list[str], timeout: int = 300) -> tuple[bool, str]:
    """Run an FFmpeg command, return (success, stderr_tail)."""
    proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
    if proc.returncode != 0:
        return False, proc.stderr.decode(errors="replace")[-500:]
    return True, ""


def _file_info(path: str) -> str:
    p = Path(path)
    if p.exists():
        return f"{path} ({p.stat().st_size / 1024 / 1024:.1f} MB)"
    return path


def _output_path(input_file: str, output: str | None, suffix: str) -> str:
    if output:
        return output
    p = Path(input_file)
    if suffix.startswith("."):
        return str(p.with_suffix(suffix))
    return str(p.with_stem(p.stem + suffix))


# ---------------------------------------------------------------------------
# Speed
# ---------------------------------------------------------------------------

def speed(
    input_file: str,
    speed: float = 2.0,
    interpolate: bool = False,
    output_path: str | None = None,
) -> tuple[bool, str]:
    """Change playback speed with optional optical-flow interpolation."""
    if speed <= 0:
        return False, "Error: speed must be positive"
    if not Path(input_file).exists():
        return False, f"Error: {input_file} not found"

    out = _output_path(input_file, output_path, f"_{speed}x")

    if interpolate and speed < 1.0:
        from declip.probe import probe as probe_file
        try:
            info = probe_file(input_file)
            target_fps = int(round(info.fps)) if info.fps else 30
        except Exception:
            target_fps = 30
        video_filter = (
            f"setpts={1/speed}*PTS,"
            f"minterpolate=fps={target_fps}:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1"
        )
    else:
        video_filter = f"setpts={1/speed}*PTS"

    # Build atempo chain (accepts 0.5-100.0 per filter)
    audio_filters = []
    remaining = speed
    while remaining > 100.0:
        audio_filters.append("atempo=100.0")
        remaining /= 100.0
    while remaining < 0.5:
        audio_filters.append("atempo=0.5")
        remaining *= 2.0
    audio_filters.append(f"atempo={remaining}")
    audio_filter = ",".join(audio_filters)

    cmd = ["ffmpeg", "-y", "-i", input_file,
           "-vf", video_filter, "-af", audio_filter, out]
    ok, err = _run(cmd, timeout=600)
    if not ok:
        # Retry without audio (input may have no audio track)
        cmd = ["ffmpeg", "-y", "-i", input_file,
               "-vf", video_filter, "-an", out]
        ok, err = _run(cmd, timeout=600)
        if not ok:
            return False, err

    return True, f"Speed {speed}x: {_file_info(out)}"


# ---------------------------------------------------------------------------
# Stabilize
# ---------------------------------------------------------------------------

def stabilize(
    input_file: str,
    shakiness: int = 5,
    smoothing: int = 10,
    zoom: float = 0,
    tripod: bool = False,
    output_path: str | None = None,
) -> tuple[bool, str]:
    """Two-pass vidstab stabilization."""
    if not Path(input_file).exists():
        return False, f"Error: {input_file} not found"

    out = _output_path(input_file, output_path, "_stabilized")

    with tempfile.NamedTemporaryFile(suffix=".trf", delete=False) as f:
        transforms = f.name

    try:
        cmd1 = ["ffmpeg", "-y", "-i", input_file,
                "-vf", f"vidstabdetect=shakiness={shakiness}:result={transforms}",
                "-f", "null", "-"]
        ok, err = _run(cmd1, timeout=600)
        if not ok:
            return False, f"Stabilization pass 1 failed: {err}"

        transform_opts = f"input={transforms}:smoothing={smoothing}:zoom={zoom}"
        if tripod:
            transform_opts += ":tripod=1"
        cmd2 = ["ffmpeg", "-y", "-i", input_file,
                "-vf", f"vidstabtransform={transform_opts},unsharp=5:5:0.8:3:3:0.4",
                "-c:a", "copy", out]
        ok, err = _run(cmd2, timeout=600)
        if not ok:
            return False, f"Stabilization pass 2 failed: {err}"
    finally:
        try:
            os.unlink(transforms)
        except OSError:
            pass

    return True, f"Stabilized: {_file_info(out)}"


# ---------------------------------------------------------------------------
# Reverse
# ---------------------------------------------------------------------------

def reverse(
    input_file: str,
    audio: bool = True,
    chunk_seconds: int = 10,
    output_path: str | None = None,
) -> tuple[bool, str]:
    """Reverse video. Auto-chunks >30s to avoid OOM."""
    if not Path(input_file).exists():
        return False, f"Error: {input_file} not found"

    out = _output_path(input_file, output_path, "_reversed")

    from declip.probe import probe as probe_file
    try:
        info = probe_file(input_file)
        duration = info.duration
    except Exception:
        duration = 0

    # Short clips: direct reverse
    if duration <= 30:
        if audio:
            cmd = ["ffmpeg", "-y", "-i", input_file, "-vf", "reverse",
                   "-af", "areverse", out]
        else:
            cmd = ["ffmpeg", "-y", "-i", input_file, "-vf", "reverse",
                   "-an", out]
        ok, err = _run(cmd, timeout=600)
        if not ok:
            return False, err
        return True, f"Reversed: {_file_info(out)}"

    # Long clips: chunked reverse
    num_chunks = math.ceil(duration / chunk_seconds)
    chunk_paths = []
    concat_list = None

    try:
        for i in range(num_chunks):
            start = i * chunk_seconds
            chunk_dur = min(chunk_seconds, duration - start)
            if chunk_dur <= 0:
                break

            with tempfile.NamedTemporaryFile(suffix=f"_chunk{i}.mp4", delete=False) as f:
                chunk_path = f.name
            chunk_paths.append(chunk_path)

            if audio:
                cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(chunk_dur),
                       "-i", input_file, "-vf", "reverse",
                       "-af", "areverse", chunk_path]
            else:
                cmd = ["ffmpeg", "-y", "-ss", str(start), "-t", str(chunk_dur),
                       "-i", input_file, "-vf", "reverse",
                       "-an", chunk_path]
            ok, err = _run(cmd, timeout=600)
            if not ok:
                return False, f"Error reversing chunk {i}: {err}"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            concat_list = f.name
            for chunk_path in reversed(chunk_paths):
                f.write(f"file '{Path(chunk_path).resolve()}'\n")

        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
               "-i", concat_list, "-c", "copy", out]
        ok, err = _run(cmd, timeout=600)
        if not ok:
            return False, f"Error concatenating reversed chunks: {err}"

        return True, f"Reversed ({num_chunks} chunks): {_file_info(out)}"
    finally:
        for p in chunk_paths:
            try:
                os.unlink(p)
            except OSError:
                pass
        if concat_list:
            try:
                os.unlink(concat_list)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Color grade
# ---------------------------------------------------------------------------

def color_grade(
    input_file: str,
    temperature: float = 0,
    shadows_r: float = 0, shadows_g: float = 0, shadows_b: float = 0,
    midtones_r: float = 0, midtones_g: float = 0, midtones_b: float = 0,
    highlights_r: float = 0, highlights_g: float = 0, highlights_b: float = 0,
    auto_levels: bool = False,
    output_path: str | None = None,
) -> tuple[bool, str]:
    """Advanced color grading — colorbalance, colortemperature, auto-levels."""
    if not Path(input_file).exists():
        return False, f"Error: {input_file} not found"

    out = _output_path(input_file, output_path, "_graded")
    filters = []

    has_balance = any([
        shadows_r, shadows_g, shadows_b,
        midtones_r, midtones_g, midtones_b,
        highlights_r, highlights_g, highlights_b,
    ])
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

    if not filters:
        return False, "Error: provide at least one color adjustment (temperature, shadow/midtone/highlight balance, or auto_levels)"

    vf = ",".join(filters)
    cmd = ["ffmpeg", "-y", "-i", input_file, "-vf", vf,
           "-c:a", "copy", out]
    ok, err = _run(cmd, timeout=600)
    if not ok:
        return False, err
    return True, f"Color graded: {_file_info(out)}"


# ---------------------------------------------------------------------------
# Sidechain compression
# ---------------------------------------------------------------------------

def sidechain(
    video_file: str,
    music_file: str,
    threshold: float = 0.02,
    ratio: float = 8.0,
    attack: float = 200,
    release: float = 1000,
    output_path: str | None = None,
) -> tuple[bool, str]:
    """Auto-duck music under speech via sidechaincompress."""
    for f in [video_file, music_file]:
        if not Path(f).exists():
            return False, f"Error: {f} not found"

    out = _output_path(video_file, output_path, "_ducked")

    # sidechaincompress: (main_audio, sidechain_signal)
    # music is main (gets compressed), speech is sidechain (controls compressor)
    fc = (
        f"[1:a][0:a]sidechaincompress="
        f"threshold={threshold}:ratio={ratio}:"
        f"attack={attack}:release={release}:"
        f"level_sc=1[compressed];"
        f"[compressed][0:a]amix=inputs=2:duration=first:normalize=0"
    )

    cmd = ["ffmpeg", "-y", "-i", video_file, "-i", music_file,
           "-filter_complex", fc,
           "-map", "0:v", "-c:v", "copy", out]
    ok, err = _run(cmd, timeout=600)
    if not ok:
        return False, err
    return True, f"Sidechain ducked: {_file_info(out)}"


# ---------------------------------------------------------------------------
# Denoise
# ---------------------------------------------------------------------------

def denoise(
    input_file: str,
    strength: str = "medium",
    method: str = "fft",
    output_path: str | None = None,
) -> tuple[bool, str]:
    """Audio noise reduction via FFT or non-local means."""
    if not Path(input_file).exists():
        return False, f"Error: {input_file} not found"

    out = _output_path(input_file, output_path, "_denoised")

    if method == "nlmeans":
        strength_map = {"light": "3", "medium": "7", "heavy": "12"}
        s = strength_map.get(strength, "7")
        af = f"anlmdn=s={s}"
    else:
        strength_map = {"light": "10", "medium": "20", "heavy": "35"}
        nr = strength_map.get(strength, "20")
        af = f"afftdn=nr={nr}:nt=w"

    cmd = ["ffmpeg", "-y", "-i", input_file, "-af", af,
           "-c:v", "copy", out]
    ok, err = _run(cmd, timeout=600)
    if not ok:
        return False, err
    return True, f"Denoised ({method}, {strength}): {_file_info(out)}"


# ---------------------------------------------------------------------------
# Loudness normalization
# ---------------------------------------------------------------------------

LOUDNORM_TARGETS = {
    "youtube": -14.0, "shorts": -14.0,
    "tiktok": -11.0, "reels": -11.0, "instagram": -11.0,
    "podcast": -16.0, "broadcast": -23.0,
}


def resolve_loudnorm_target(target: str) -> tuple[float | None, str | None]:
    """Resolve a target name or number to LUFS. Returns (lufs, error)."""
    lufs = LOUDNORM_TARGETS.get(target.lower())
    if lufs is not None:
        return lufs, None
    try:
        return float(target), None
    except ValueError:
        return None, f"Invalid target '{target}'. Use youtube, tiktok, podcast, broadcast, or a LUFS number like -14"


def loudnorm(
    input_file: str,
    target: str = "youtube",
    output_path: str | None = None,
) -> tuple[bool, str]:
    """Two-pass loudness normalization to a platform target."""
    if not Path(input_file).exists():
        return False, f"Error: {input_file} not found"

    target_lufs, err = resolve_loudnorm_target(target)
    if err:
        return False, f"Error: {err}"

    out = _output_path(input_file, output_path, "_loudnorm")
    tp = -1.5

    # Pass 1: measure
    cmd1 = [
        "ffmpeg", "-y", "-i", input_file,
        "-af", f"loudnorm=I={target_lufs}:TP={tp}:LRA=11:print_format=json",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd1, capture_output=True, text=True, timeout=600)

    # Parse measured values
    stderr = proc.stderr
    json_start = stderr.rfind("{")
    json_end = stderr.rfind("}") + 1
    measured = {}
    if json_start >= 0 and json_end > json_start:
        try:
            measured = json.loads(stderr[json_start:json_end])
        except json.JSONDecodeError:
            pass

    if not measured:
        return False, "Error: could not measure loudness in pass 1"

    # Pass 2: apply with measured values
    af = (
        f"loudnorm=I={target_lufs}:TP={tp}:LRA=11:"
        f"measured_I={measured.get('input_i', '-24.0')}:"
        f"measured_TP={measured.get('input_tp', '-2.0')}:"
        f"measured_LRA={measured.get('input_lra', '7.0')}:"
        f"measured_thresh={measured.get('input_thresh', '-34.0')}:"
        f"offset={measured.get('target_offset', '0.0')}:linear=true"
    )

    cmd2 = ["ffmpeg", "-y", "-i", input_file, "-af", af,
            "-c:v", "copy", out]
    ok, err = _run(cmd2, timeout=600)
    if not ok:
        return False, err
    return True, f"Normalized to {target_lufs:.0f} LUFS ({target}): {_file_info(out)}"
