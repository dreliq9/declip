import shutil
import subprocess
from pathlib import Path

import pytest

from declip.backends import mlt as mlt_backend
from declip.output import OutputManager
from declip.probe import probe
from declip.schema import Project


pytestmark = pytest.mark.skipif(
    not shutil.which("melt") or not shutil.which("ffmpeg") or not shutil.which("ffprobe"),
    reason="melt/FFmpeg/ffprobe not installed",
)


def _make_clip(path: Path, duration: float = 1.5) -> None:
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=purple:s=160x90:r=30:d={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate=48000:duration={duration}",
        "-shortest",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "96k",
        str(path),
    ], check=True, capture_output=True, timeout=60)


def test_mlt_backend_renders_bounded_trimmed_fixture(tmp_path: Path):
    _make_clip(tmp_path / "source.mp4")
    project = Project.model_validate({
        "version": "1.0",
        "settings": {"resolution": [320, 180], "fps": 30},
        "timeline": {"tracks": [{"id": "main", "clips": [{
            "asset": "source.mp4",
            "start": 0,
            "trim_in": 0.25,
            "duration": 1.0,
        }]}]},
        "output": {"path": str(tmp_path / "mlt-output.mp4")},
    })
    out = OutputManager(json_mode=False, quiet=True)

    success = mlt_backend.render(project, tmp_path, out, total_duration=1.0)

    assert success, out.get_log()
    output = tmp_path / "mlt-output.mp4"
    assert output.exists() and output.stat().st_size > 0
    info = probe(output)
    assert info.duration == pytest.approx(1.0, abs=0.20)
    assert info.width == 320 and info.height == 180
