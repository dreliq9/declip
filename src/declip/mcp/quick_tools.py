"""MCP tools for quick operations — trim, concat, thumbnail, probe.

Returns Pydantic models defined in `declip.mcp.types`. FastMCP serializes
each into both `content` (human-readable text via __str__) and
`structuredContent` (typed JSON). Agents can read fields like
`result.duration_seconds` directly without parsing the formatted string.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Annotated, Optional

from mcp.server.fastmcp import FastMCP
from pydantic import Field

from declip.mcp.types import (
    ConcatResult,
    ProbeResult,
    ThumbnailResult,
    TrimResult,
)


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def declip_probe(
        file_path: Annotated[str, Field(description="Path to a video or audio file")],
    ) -> ProbeResult:
        """Probe a media file and return its properties (duration, resolution, codecs, size)."""
        from declip.probe import probe

        try:
            info = probe(file_path)
        except Exception as e:
            return ProbeResult(
                path=file_path, duration_seconds=0.0, file_size_bytes=0, error=str(e),
            )

        return ProbeResult(
            path=info.path,
            duration_seconds=info.duration,
            file_size_bytes=info.file_size,
            width=info.width,
            height=info.height,
            fps=info.fps,
            video_codec=info.codec,
            pixel_format=info.pixel_format,
            bit_depth=info.bit_depth,
            is_hdr=info.is_hdr,
            video_bitrate_bps=info.video_bitrate,
            color_space=info.color_space,
            color_primaries=info.color_primaries,
            color_transfer=info.color_transfer,
            audio_codec=info.audio_codec,
            audio_channels=info.audio_channels,
            audio_sample_rate=info.audio_sample_rate,
            audio_bitrate_bps=info.audio_bitrate,
        )

    @mcp.tool()
    def declip_trim(
        input_file: Annotated[str, Field(description="Path to the input video file")],
        trim_in: Annotated[float, Field(ge=0, description="Start time in seconds")],
        trim_out: Annotated[float, Field(gt=0, description="End time in seconds")],
        smart: Annotated[bool, Field(
            description="Use keyframe-aware hybrid cut (clean cuts, slightly slower)",
        )] = False,
        output_path: Annotated[
            Optional[str], Field(default=None, description="Output file path (defaults to input_trimmed.ext)"),
        ] = None,
    ) -> TrimResult:
        """Trim a video to a time range.

        Default mode uses stream copy (fast, may have brief glitch at cut point
        if it doesn't land on a keyframe). Smart mode re-encodes only the few
        frames between the cut point and the next keyframe, then stream-copies
        the rest — clean cuts with minimal re-encoding.
        """
        if trim_out <= trim_in:
            return TrimResult(
                success=False, trim_in_seconds=trim_in, trim_out_seconds=trim_out,
                duration_seconds=0.0, smart=smart, error="trim_out must be greater than trim_in",
            )

        if not output_path:
            p = Path(input_file)
            output_path = str(p.with_stem(p.stem + "_trimmed"))

        duration = trim_out - trim_in

        if not smart:
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(trim_in), "-i", str(input_file),
                "-t", str(duration), "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                output_path,
            ]
            proc = subprocess.run(cmd, capture_output=True)
            if proc.returncode != 0:
                return TrimResult(
                    success=False, trim_in_seconds=trim_in, trim_out_seconds=trim_out,
                    duration_seconds=duration, smart=False,
                    error=proc.stderr.decode(errors="replace")[-300:],
                )
            size = Path(output_path).stat().st_size
            return TrimResult(
                success=True, output_path=output_path, file_size_bytes=size,
                trim_in_seconds=trim_in, trim_out_seconds=trim_out,
                duration_seconds=duration, smart=False,
            )

        # Smart trim: find nearest keyframe at or after trim_in
        probe_cmd = [
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "packet=pts_time,flags",
            "-of", "csv=p=0",
            "-read_intervals", f"{trim_in}%{min(trim_in + 15, trim_out)}",
            str(input_file),
        ]
        probe_proc = subprocess.run(probe_cmd, capture_output=True, text=True)

        next_keyframe = None
        if probe_proc.returncode == 0:
            for line in probe_proc.stdout.strip().split("\n"):
                parts = line.strip().split(",")
                if len(parts) >= 2:
                    try:
                        pts = float(parts[0])
                        flags = parts[1]
                        if "K" in flags and pts > trim_in + 0.01:
                            next_keyframe = pts
                            break
                    except (ValueError, IndexError):
                        continue

        # No nearby keyframe: full re-encode of the requested segment
        if next_keyframe is None or next_keyframe >= trim_out:
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(trim_in), "-i", str(input_file),
                "-t", str(duration),
                "-avoid_negative_ts", "make_zero",
                output_path,
            ]
            proc = subprocess.run(cmd, capture_output=True)
            if proc.returncode != 0:
                return TrimResult(
                    success=False, trim_in_seconds=trim_in, trim_out_seconds=trim_out,
                    duration_seconds=duration, smart=True,
                    error=proc.stderr.decode(errors="replace")[-300:],
                )
            size = Path(output_path).stat().st_size
            return TrimResult(
                success=True, output_path=output_path, file_size_bytes=size,
                trim_in_seconds=trim_in, trim_out_seconds=trim_out,
                duration_seconds=duration, smart=True, fallback_full_re_encode=True,
            )

        # Re-encode head, stream-copy tail, concat
        head_duration = next_keyframe - trim_in
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            head_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tail_path = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            concat_list = f.name

        try:
            cmd_head = [
                "ffmpeg", "-y",
                "-ss", str(trim_in), "-i", str(input_file),
                "-t", str(head_duration),
                "-avoid_negative_ts", "make_zero",
                head_path,
            ]
            proc = subprocess.run(cmd_head, capture_output=True)
            if proc.returncode != 0:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(trim_in), "-i", str(input_file),
                    "-t", str(duration),
                    "-avoid_negative_ts", "make_zero",
                    output_path,
                ]
                subprocess.run(cmd, capture_output=True)
                size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
                return TrimResult(
                    success=True, output_path=output_path, file_size_bytes=size,
                    trim_in_seconds=trim_in, trim_out_seconds=trim_out,
                    duration_seconds=duration, smart=True, fallback_full_re_encode=True,
                )

            tail_duration = trim_out - next_keyframe
            cmd_tail = [
                "ffmpeg", "-y",
                "-ss", str(next_keyframe), "-i", str(input_file),
                "-t", str(tail_duration), "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                tail_path,
            ]
            proc = subprocess.run(cmd_tail, capture_output=True)
            if proc.returncode != 0:
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(trim_in), "-i", str(input_file),
                    "-t", str(duration),
                    "-avoid_negative_ts", "make_zero",
                    output_path,
                ]
                subprocess.run(cmd, capture_output=True)
                size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
                return TrimResult(
                    success=True, output_path=output_path, file_size_bytes=size,
                    trim_in_seconds=trim_in, trim_out_seconds=trim_out,
                    duration_seconds=duration, smart=True, fallback_full_re_encode=True,
                )

            with open(concat_list, "w") as cl:
                cl.write(f"file '{Path(head_path).resolve()}'\n")
                cl.write(f"file '{Path(tail_path).resolve()}'\n")

            cmd_concat = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", concat_list, "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                output_path,
            ]
            proc = subprocess.run(cmd_concat, capture_output=True)
            if proc.returncode != 0:
                return TrimResult(
                    success=False, trim_in_seconds=trim_in, trim_out_seconds=trim_out,
                    duration_seconds=duration, smart=True,
                    error=f"concat failed: {proc.stderr.decode(errors='replace')[-300:]}",
                )

            size = Path(output_path).stat().st_size
            return TrimResult(
                success=True, output_path=output_path, file_size_bytes=size,
                trim_in_seconds=trim_in, trim_out_seconds=trim_out,
                duration_seconds=duration, smart=True,
                re_encoded_head_seconds=head_duration,
                stream_copied_tail_seconds=tail_duration,
            )
        finally:
            for tmp in [head_path, tail_path, concat_list]:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    @mcp.tool()
    def declip_concat(
        files: Annotated[list[str], Field(min_length=2, description="Video file paths to concatenate (in order)")],
        output_path: Annotated[str, Field(description="Output file path")] = "concat_output.mp4",
        preset: Annotated[
            Optional[str],
            Field(default=None, description="Optional output preset (youtube-1080p, draft, ...)"),
        ] = None,
    ) -> ConcatResult:
        """Concatenate multiple video files into one.

        Smart concat: if all inputs share the same codec/resolution/fps, uses
        stream copy (instant, no re-encode). Otherwise re-encodes to normalize.
        """
        from declip.schema import Project, PRESETS, PRESET_RESOLUTIONS
        from declip.probe import probe as probe_file
        from declip.backends import ffmpeg as ffmpeg_backend
        from declip.output import OutputManager

        infos = []
        for f in files:
            try:
                infos.append(probe_file(f))
            except Exception:
                infos.append(None)

        valid_infos = [i for i in infos if i is not None]
        can_stream_copy = (
            len(valid_infos) == len(files)
            and preset is None
            and len(set(i.codec for i in valid_infos)) == 1
            and len(set((i.width, i.height) for i in valid_infos)) == 1
            and len(set(round(i.fps, 1) for i in valid_infos if i.fps)) <= 1
        )

        if can_stream_copy:
            with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
                for path in files:
                    f.write(f"file '{Path(path).resolve()}'\n")
                listfile = f.name
            try:
                cmd = [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", listfile, "-c", "copy",
                    "-avoid_negative_ts", "make_zero",
                    output_path,
                ]
                proc = subprocess.run(cmd, capture_output=True)
                if proc.returncode == 0:
                    size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
                    return ConcatResult(
                        success=True, output_path=output_path, file_size_bytes=size,
                        file_count=len(files), method="stream-copy",
                    )
            finally:
                os.unlink(listfile)

        clips = []
        cursor = 0.0
        for i, f in enumerate(files):
            dur = infos[i].duration if infos[i] else 10.0
            clips.append({"asset": str(Path(f).resolve()), "start": cursor})
            cursor += dur

        project_data = {
            "version": "1.0",
            "timeline": {"tracks": [{"id": "main", "clips": clips}]},
            "output": {"path": str(Path(output_path).resolve())},
        }

        if preset and preset in PRESETS:
            p = PRESETS[preset]
            project_data["output"] = json.loads(p.model_dump_json(exclude_none=True))
            project_data["output"]["path"] = str(Path(output_path).resolve())
            if preset in PRESET_RESOLUTIONS:
                project_data["settings"] = {"resolution": list(PRESET_RESOLUTIONS[preset])}

        project = Project.model_validate(project_data)
        out = OutputManager(json_mode=False, quiet=True)
        success = ffmpeg_backend.render(project, Path("."), out, total_duration=cursor)

        if success:
            size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
            return ConcatResult(
                success=True, output_path=output_path, file_size_bytes=size,
                file_count=len(files), method="re-encoded",
            )
        return ConcatResult(success=False, file_count=len(files), method="re-encoded", error="concatenation failed")

    @mcp.tool()
    def declip_thumbnail(
        input_file: Annotated[str, Field(description="Path to the video file")],
        timestamp: Annotated[float, Field(ge=0, description="Time in seconds to extract the frame")] = 1.0,
        output_path: Annotated[
            Optional[str], Field(default=None, description="Output PNG path (defaults to input.png)"),
        ] = None,
    ) -> ThumbnailResult:
        """Extract a single frame from a video as a PNG image."""
        from declip.analyze import extract_frame

        if not output_path:
            output_path = str(Path(input_file).with_suffix(".png"))

        try:
            frame = extract_frame(input_file, timestamp, output_path)
            return ThumbnailResult(
                success=True, output_path=frame.path,
                timestamp_seconds=frame.timestamp,
                width=frame.width, height=frame.height,
            )
        except Exception as e:
            return ThumbnailResult(success=False, error=str(e))
