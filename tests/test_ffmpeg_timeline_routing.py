from pathlib import Path

import pytest

from declip.compilers import ffmpeg
from declip.schema import Project


def _project(clips):
    return Project.model_validate({
        "version": "1.0",
        "timeline": {"tracks": [{"id": "main", "clips": clips}]},
        "output": {"path": "out.mp4"},
    })


def test_manual_timeline_gap_routes_away_from_ffmpeg(tmp_path: Path):
    project = _project([
        {"asset": "a.mp4", "start": 0, "duration": 2.0},
        {"asset": "b.mp4", "start": 5.0, "duration": 2.0},
    ])

    assert ffmpeg.can_handle(project) is False
    with pytest.raises(ffmpeg.CompilationError):
        ffmpeg.compile_commands(project, tmp_path)


def test_manual_unmodeled_overlap_routes_away_from_ffmpeg(tmp_path: Path):
    project = _project([
        {"asset": "a.mp4", "start": 0, "duration": 4.0},
        {"asset": "b.mp4", "start": 3.0, "duration": 2.0},
    ])

    assert ffmpeg.can_handle(project) is False


def test_still_image_input_is_looped_for_declared_duration(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ffmpeg, "_has_audio", lambda _: False)
    project = _project([
        {"asset": "still.png", "start": 0, "duration": 3.0},
    ])

    command = ffmpeg.compile_commands(project, tmp_path)[0]
    image_index = command.index(str(tmp_path / "still.png"))

    assert command[image_index - 7:image_index + 1] == [
        "-loop", "1", "-framerate", "30", "-t", "3.0", "-i", str(tmp_path / "still.png")
    ]
