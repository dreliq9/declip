"""MCP tools for project operations — validate, render, export."""

from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:

    @mcp.tool()
    def declip_init(directory: str) -> str:
        """Create a minimal declip project.json template in the specified directory.

        Args:
            directory: Directory to create the project file in
        """
        from declip.schema import Project

        out_path = Path(directory) / "project.json"
        if out_path.exists():
            return f"Error: {out_path} already exists"

        template = {
            "version": "1.0",
            "settings": {"resolution": [1920, 1080], "fps": 30, "background": "#000000"},
            "timeline": {
                "tracks": [{"id": "main", "clips": [{"asset": "input.mp4", "start": 0}]}],
                "audio": [],
            },
            "output": {"path": "output.mp4", "format": "mp4", "codec": "h264", "quality": "high"},
        }
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(template, indent=2))
        return f"Created {out_path}"

    @mcp.tool()
    def declip_validate(project_file: str) -> str:
        """Validate a declip project JSON file — checks schema and asset existence.

        Args:
            project_file: Path to the project.json file
        """
        from declip.schema import Project

        try:
            project = Project.load(project_file)
        except Exception as e:
            return f"Validation error: {e}"

        project_dir = Path(project_file).parent
        missing = []
        for track in project.timeline.tracks:
            for clip in track.clips:
                p = Path(clip.asset)
                if not p.is_absolute():
                    p = project_dir / p
                if not p.exists():
                    missing.append(clip.asset)

        for audio in project.timeline.audio:
            p = Path(audio.asset)
            if not p.is_absolute():
                p = project_dir / p
            if not p.exists():
                missing.append(audio.asset)

        tracks = len(project.timeline.tracks)
        clips = sum(len(t.clips) for t in project.timeline.tracks)
        result = f"Valid project: {tracks} track(s), {clips} clip(s), {project.settings.resolution[0]}x{project.settings.resolution[1]} @ {project.settings.fps}fps"

        if missing:
            result += f"\nMissing assets: {', '.join(missing)}"

        return result

    @mcp.tool()
    def declip_render(
        project_file: str,
        backend: str = "auto",
        output_path: str | None = None,
        preset: str | None = None,
        variables: str | None = None,
    ) -> str:
        """Render a declip project file to video.

        Auto-selects FFmpeg (single-track) or MLT (multi-track) backend.

        Args:
            project_file: Path to the project.json file
            backend: "auto", "ffmpeg", or "mlt"
            output_path: Override the output file path
            preset: Output preset name (youtube-1080p, instagram-reel, prores-master, draft, web-vp9, youtube-4k)
            variables: JSON string of template variables, e.g. '{"title": "Episode 1"}'
        """
        from declip.schema import Project, PRESETS, PRESET_RESOLUTIONS
        from declip.backends import ffmpeg as ffmpeg_backend
        from declip.backends import mlt as mlt_backend
        from declip.output import OutputManager

        var_dict = json.loads(variables) if variables else None
        project_dir = Path(project_file).parent

        try:
            project = Project.load(project_file, variables=var_dict)
        except Exception as e:
            return f"Error loading project: {e}"

        if preset and preset in PRESETS:
            project.output = PRESETS[preset].model_copy()
            if preset in PRESET_RESOLUTIONS:
                project.settings.resolution = PRESET_RESOLUTIONS[preset]

        if output_path:
            project.output.path = str(Path(output_path).resolve())

        # Resolve any "auto" start values to actual timestamps
        project.resolve_auto_starts(project_dir)

        # Estimate duration (all starts are resolved to floats at this point)
        max_end = 0.0
        for track in project.timeline.tracks:
            for clip in track.clips:
                start = float(clip.start)
                if clip.duration is not None:
                    end = start + clip.duration
                elif clip.trim_out is not None:
                    end = start + (clip.trim_out - clip.trim_in)
                else:
                    end = start + 10
                max_end = max(max_end, end)

        out = OutputManager(json_mode=False, quiet=True)

        if backend == "auto":
            use_ffmpeg = ffmpeg_backend.can_handle(project)
        else:
            use_ffmpeg = (backend == "ffmpeg")

        chosen = "ffmpeg" if use_ffmpeg else "mlt"

        if use_ffmpeg:
            success = ffmpeg_backend.render(project, project_dir, out, max_end or None)
        else:
            success = mlt_backend.render(project, project_dir, out, max_end or None)

        if success:
            out_path = project.output.path
            if not Path(out_path).is_absolute():
                out_path = str(project_dir / out_path)
            size = Path(out_path).stat().st_size if Path(out_path).exists() else 0
            return f"Rendered successfully via {chosen}\nOutput: {out_path} ({size / 1024 / 1024:.1f} MB)"
        else:
            return f"Render failed via {chosen}. Check stderr for details."

    @mcp.tool()
    def declip_export_mlt(project_file: str) -> str:
        """Export a declip project as MLT XML (without rendering).

        Args:
            project_file: Path to the project.json file
        """
        from declip.schema import Project
        from declip.backends import mlt as mlt_backend

        try:
            project = Project.load(project_file)
        except Exception as e:
            return f"Error: {e}"

        project_dir = Path(project_file).parent
        project.resolve_auto_starts(project_dir)
        return mlt_backend.compile_to_string(project, project_dir)

    @mcp.tool()
    def declip_list_presets() -> str:
        """List all available output presets with their settings."""
        from declip.schema import PRESETS, PRESET_RESOLUTIONS

        lines = []
        for name, preset in PRESETS.items():
            res = PRESET_RESOLUTIONS.get(name, (1920, 1080))
            lines.append(f"{name}: {res[0]}x{res[1]}, {preset.codec.value}, {preset.quality.value}, audio={preset.audio_codec}")
        return "\n".join(lines)

    @mcp.tool()
    def declip_assets(project_file: str) -> str:
        """List all assets referenced in a project with status, duration, and size.

        Args:
            project_file: Path to the project.json file
        """
        from declip.schema import Project
        from declip.probe import probe as probe_file

        try:
            project = Project.load(project_file)
        except Exception as e:
            return f"Error: {e}"

        project_dir = Path(project_file).parent
        seen = set()
        lines = []
        total_size = 0

        all_assets = []
        for track in project.timeline.tracks:
            for clip in track.clips:
                all_assets.append(clip.asset)
        for audio in project.timeline.audio:
            all_assets.append(audio.asset)

        for asset in all_assets:
            if asset in seen:
                continue
            seen.add(asset)
            p = Path(asset)
            if not p.is_absolute():
                p = project_dir / p

            if not p.exists():
                lines.append(f"MISSING: {asset}")
                continue

            try:
                info = probe_file(p)
                total_size += info.file_size
                size_mb = info.file_size / 1024 / 1024
                lines.append(f"OK: {asset} ({info.duration:.1f}s, {size_mb:.1f}MB, {info.codec})")
            except Exception as e:
                lines.append(f"ERROR: {asset}: {e}")

        lines.append(f"\nTotal: {len(seen)} asset(s), {total_size / 1024 / 1024:.1f} MB")
        return "\n".join(lines)
