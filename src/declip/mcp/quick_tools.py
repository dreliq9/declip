"""MCP tools for quick operations — trim, concat, thumbnail, probe."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def declip_probe(file_path: str) -> str:
        """Probe a media file and return its properties (duration, resolution, codecs, size).

        Args:
            file_path: Path to a video or audio file
        """
        from declip.probe import probe

        try:
            info = probe(file_path)
        except Exception as e:
            return f"Error: {e}"

        lines = [f"File: {info.path}"]
        lines.append(f"Duration: {info.duration:.1f}s")
        if info.width:
            vid_line = f"Video: {info.width}x{info.height} @ {info.fps:.1f}fps ({info.codec})"
            if info.pixel_format:
                vid_line += f", {info.pixel_format}"
            if info.bit_depth and info.bit_depth != 8:
                vid_line += f", {info.bit_depth}-bit"
            if info.is_hdr:
                vid_line += " [HDR]"
            if info.video_bitrate:
                vid_line += f", {info.video_bitrate / 1_000_000:.1f} Mbps"
            lines.append(vid_line)
            if info.color_space and info.color_space != "unknown":
                lines.append(f"Color: {info.color_space}, primaries={info.color_primaries}, transfer={info.color_transfer}")
        if info.audio_codec:
            aud_line = f"Audio: {info.audio_codec}, {info.audio_channels}ch, {info.audio_sample_rate}Hz"
            if info.audio_bitrate:
                aud_line += f", {info.audio_bitrate / 1000:.0f} kbps"
            lines.append(aud_line)
        lines.append(f"Size: {info.file_size / 1024 / 1024:.1f} MB")
        return "\n".join(lines)

    @mcp.tool()
    def declip_trim(
        input_file: str,
        trim_in: float,
        trim_out: float,
        smart: bool = False,
        output_path: str | None = None,
    ) -> str:
        """Trim a video to a time range.

        Default mode uses stream copy (fast, may have brief glitch at cut point
        if it doesn't land on a keyframe). Smart mode re-encodes only the few
        frames between the cut point and the next keyframe, then stream-copies
        the rest — clean cuts with minimal re-encoding.

        Args:
            input_file: Path to the input video file
            trim_in: Start time in seconds
            trim_out: End time in seconds
            smart: Use keyframe-aware hybrid cut (clean cut points, slightly slower)
            output_path: Output file path (defaults to input_trimmed.ext)
        """
        if trim_out <= trim_in:
            return "Error: trim_out must be greater than trim_in"

        if not output_path:
            p = Path(input_file)
            output_path = str(p.with_stem(p.stem + "_trimmed"))

        duration = trim_out - trim_in

        if not smart:
            # Fast path: pure stream copy
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(trim_in), "-i", str(input_file),
                "-t", str(duration), "-c", "copy",
                "-avoid_negative_ts", "make_zero",
                output_path,
            ]
            proc = subprocess.run(cmd, capture_output=True)
            if proc.returncode != 0:
                return f"Error: {proc.stderr.decode(errors='replace')[-300:]}"

            size = Path(output_path).stat().st_size
            return f"Trimmed {trim_in}s-{trim_out}s ({duration:.1f}s)\nOutput: {output_path} ({size / 1024 / 1024:.1f} MB)"

        # Smart trim: find nearest keyframe before trim_in, re-encode
        # the gap from trim_in to the next keyframe, stream-copy the rest.
        # This gives frame-accurate cuts without re-encoding the entire file.
        import tempfile, os

        # Step 1: Find the nearest keyframe at or after trim_in
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

        # If no keyframe found nearby or keyframe is past trim_out, just re-encode the whole segment
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
                return f"Error: {proc.stderr.decode(errors='replace')[-300:]}"
            size = Path(output_path).stat().st_size
            return f"Smart trimmed {trim_in}s-{trim_out}s ({duration:.1f}s, full re-encode — no nearby keyframe)\nOutput: {output_path} ({size / 1024 / 1024:.1f} MB)"

        # Step 2: Re-encode the head (trim_in to next_keyframe)
        head_duration = next_keyframe - trim_in
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            head_path = f.name
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            tail_path = f.name
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            concat_list = f.name

        try:
            # Re-encode head segment (few frames only)
            cmd_head = [
                "ffmpeg", "-y",
                "-ss", str(trim_in), "-i", str(input_file),
                "-t", str(head_duration),
                "-avoid_negative_ts", "make_zero",
                head_path,
            ]
            proc = subprocess.run(cmd_head, capture_output=True)
            if proc.returncode != 0:
                # Fall back to full re-encode
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(trim_in), "-i", str(input_file),
                    "-t", str(duration),
                    "-avoid_negative_ts", "make_zero",
                    output_path,
                ]
                subprocess.run(cmd, capture_output=True)
                size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
                return f"Smart trimmed {trim_in}s-{trim_out}s ({duration:.1f}s, fallback re-encode)\nOutput: {output_path} ({size / 1024 / 1024:.1f} MB)"

            # Stream-copy tail segment (keyframe to trim_out)
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
                # Fall back: just use the re-encoded head for the full duration
                cmd = [
                    "ffmpeg", "-y",
                    "-ss", str(trim_in), "-i", str(input_file),
                    "-t", str(duration),
                    "-avoid_negative_ts", "make_zero",
                    output_path,
                ]
                subprocess.run(cmd, capture_output=True)
                size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
                return f"Smart trimmed {trim_in}s-{trim_out}s ({duration:.1f}s, fallback re-encode)\nOutput: {output_path} ({size / 1024 / 1024:.1f} MB)"

            # Concat head + tail
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
                return f"Error during concat: {proc.stderr.decode(errors='replace')[-300:]}"

            size = Path(output_path).stat().st_size
            return (
                f"Smart trimmed {trim_in}s-{trim_out}s ({duration:.1f}s)\n"
                f"Re-encoded {head_duration:.2f}s head, stream-copied {tail_duration:.1f}s tail\n"
                f"Output: {output_path} ({size / 1024 / 1024:.1f} MB)"
            )
        finally:
            for tmp in [head_path, tail_path, concat_list]:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass

    @mcp.tool()
    def declip_concat(
        files: list[str],
        output_path: str = "concat_output.mp4",
        preset: str | None = None,
    ) -> str:
        """Concatenate multiple video files into one.

        Smart concat: if all inputs share the same codec/resolution/fps, uses
        stream copy (instant, no re-encode). Otherwise re-encodes to normalize.

        Args:
            files: List of video file paths to concatenate (in order)
            output_path: Output file path
            preset: Optional output preset (youtube-1080p, draft, etc.)
        """
        from declip.schema import Project, PRESETS, PRESET_RESOLUTIONS
        from declip.probe import probe as probe_file
        from declip.backends import ffmpeg as ffmpeg_backend
        from declip.output import OutputManager
        import tempfile

        if len(files) < 2:
            return "Error: need at least 2 files to concatenate"

        # Probe all inputs to check if they match
        infos = []
        for f in files:
            try:
                infos.append(probe_file(f))
            except Exception:
                infos.append(None)

        # Check if all inputs are compatible for stream copy
        valid_infos = [i for i in infos if i is not None]
        can_stream_copy = (
            len(valid_infos) == len(files)
            and preset is None
            and len(set(i.codec for i in valid_infos)) == 1
            and len(set((i.width, i.height) for i in valid_infos)) == 1
            and len(set(round(i.fps, 1) for i in valid_infos if i.fps)) <= 1
        )

        if can_stream_copy:
            # Fast path: concat demuxer with stream copy
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
                    return f"Concatenated {len(files)} files (stream copy — no re-encode)\nOutput: {output_path} ({size / 1024 / 1024:.1f} MB)"
                # Fall through to re-encode path on failure
            finally:
                import os
                os.unlink(listfile)

        # Slow path: re-encode via project renderer (handles mixed formats)
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
            return f"Concatenated {len(files)} files (re-encoded)\nOutput: {output_path} ({size / 1024 / 1024:.1f} MB)"
        return "Error: concatenation failed"

    @mcp.tool()
    def declip_thumbnail(
        input_file: str,
        timestamp: float = 1.0,
        output_path: str | None = None,
    ) -> str:
        """Extract a single frame from a video as a PNG image.

        Args:
            input_file: Path to the video file
            timestamp: Time in seconds to extract the frame
            output_path: Output PNG path (defaults to input.png)
        """
        from declip.analyze import extract_frame

        if not output_path:
            output_path = str(Path(input_file).with_suffix(".png"))

        try:
            frame = extract_frame(input_file, timestamp, output_path)
            return f"Saved: {frame.path} ({frame.width}x{frame.height}, t={frame.timestamp:.2f}s)"
        except Exception as e:
            return f"Error: {e}"
