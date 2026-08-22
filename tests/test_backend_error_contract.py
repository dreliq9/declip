from pathlib import Path

from declip.backends import ffmpeg as ffmpeg_backend
from declip.backends import mlt as mlt_backend
from declip.output import OutputManager
from declip.schema import Project


def _project_with_include() -> Project:
    return Project.model_validate({
        "version": "1.0",
        "includes": ["nested.json"],
        "timeline": {
            "tracks": [{
                "id": "main",
                "clips": [{"asset": "clip.mp4", "start": 0, "duration": 1.0}],
            }]
        },
    })


def test_ffmpeg_backend_returns_false_for_render_plan_error(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ffmpeg_backend.shutil, "which", lambda _: "/usr/bin/ffmpeg")
    out = OutputManager(json_mode=False, quiet=True)

    assert not ffmpeg_backend.render(_project_with_include(), tmp_path, out)
    assert "includes" in out.get_log().lower()


def test_mlt_backend_returns_false_for_render_plan_error(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(mlt_backend.shutil, "which", lambda _: "/usr/bin/melt")
    out = OutputManager(json_mode=False, quiet=True)

    assert not mlt_backend.render(_project_with_include(), tmp_path, out)
    assert "includes" in out.get_log().lower()
