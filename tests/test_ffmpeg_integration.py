import shutil
import subprocess
from pathlib import Path

import pytest

from declip.backends import ffmpeg as ffmpeg_backend
from declip.output import OutputManager
from declip.probe import probe
from declip.schema import Project


pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="FFmpeg/ffprobe not installed",
)


def _run(command: list[str]) -> None:
    subprocess.run(command, check=True, capture_output=True, timeout=60)


def _make_clip(path: Path, color: str, frequency: int, duration: float = 1.0) -> None:
    _run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=30:d={duration}",
        "-f", "lavfi", "-i", f"sine=frequency={frequency}:sample_rate=48000:duration={duration}",
        "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k",
        str(path),
    ])


def _make_still(path: Path, color: str = "yellow") -> None:
    _run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c={color}:s=160x90:r=1:d=1",
        "-frames:v", "1",
        str(path),
    ])


def _render(project: Project, project_dir: Path) -> Path:
    out = OutputManager(json_mode=False, quiet=True)
    success = ffmpeg_backend.render(project, project_dir, out, total_duration=None)
    assert success, out.get_log()
    output = Path(project.output.path)
    if not output.is_absolute():
        output = project_dir / output
    assert output.exists() and output.stat().st_size > 0
    return output


def test_ffmpeg_concat_renders_two_synthetic_clips(tmp_path: Path):
    _make_clip(tmp_path / "a.mp4", "red", 440)
    _make_clip(tmp_path / "b.mp4", "blue", 660)
    project = Project.model_validate({
        "version": "1.0",
        "timeline": {"tracks": [{"id": "main", "clips": [
            {"asset": "a.mp4", "start": 0, "duration": 1.0},
            {"asset": "b.mp4", "start": "auto", "duration": 1.0},
        ]}]},
        "output": {"path": str(tmp_path / "concat.mp4")},
    })

    output = _render(project, tmp_path)
    assert probe(output).duration == pytest.approx(2.0, abs=0.20)


def test_ffmpeg_xfade_renders_expected_overlap_duration(tmp_path: Path):
    _make_clip(tmp_path / "a.mp4", "red", 440)
    _make_clip(tmp_path / "b.mp4", "blue", 660)
    project = Project.model_validate({
        "version": "1.0",
        "timeline": {"tracks": [{"id": "main", "clips": [
            {"asset": "a.mp4", "start": 0, "duration": 1.0},
            {
                "asset": "b.mp4",
                "start": "auto",
                "duration": 1.0,
                "transition_in": {"type": "dissolve", "duration": 0.25},
            },
        ]}]},
        "output": {"path": str(tmp_path / "xfade.mp4")},
    })

    output = _render(project, tmp_path)
    assert probe(output).duration == pytest.approx(1.75, abs=0.20)


def test_ffmpeg_still_image_renders_for_declared_duration(tmp_path: Path):
    _make_still(tmp_path / "still.png")
    project = Project.model_validate({
        "version": "1.0",
        "timeline": {"tracks": [{"id": "main", "clips": [
            {"asset": "still.png", "start": 0, "duration": 1.2},
        ]}]},
        "output": {"path": str(tmp_path / "still.mp4")},
    })

    output = _render(project, tmp_path)
    info = probe(output)
    assert info.duration == pytest.approx(1.2, abs=0.20)
    assert info.width == 1920 and info.height == 1080


def test_ffmpeg_multiclip_watermark_survives_real_render(tmp_path: Path):
    _make_clip(tmp_path / "a.mp4", "red", 440)
    _make_clip(tmp_path / "b.mp4", "blue", 660)
    _make_still(tmp_path / "logo.png", "white")
    watermark = {
        "type": "watermark",
        "watermark": {
            "image": "logo.png",
            "position": [0.95, 0.05],
            "scale": 0.1,
            "opacity": 0.6,
        },
    }
    project = Project.model_validate({
        "version": "1.0",
        "timeline": {"tracks": [{"id": "main", "clips": [
            {"asset": "a.mp4", "start": 0, "duration": 1.0, "filters": [watermark]},
            {"asset": "b.mp4", "start": "auto", "duration": 1.0, "filters": [watermark]},
        ]}]},
        "output": {"path": str(tmp_path / "watermarked.mp4")},
    })

    output = _render(project, tmp_path)
    assert probe(output).duration == pytest.approx(2.0, abs=0.20)
