import json

import pytest

from declip import project_ops


def _write_project(tmp_path, data):
    project = tmp_path / "project.json"
    project.write_text(json.dumps(data))
    return project


def test_validate_project_checks_filter_assets(tmp_path):
    video = tmp_path / "video.mp4"
    video.touch()
    project = _write_project(tmp_path, {
        "version": "1.0",
        "timeline": {
            "tracks": [{
                "id": "main",
                "clips": [{
                    "asset": "video.mp4",
                    "start": 0,
                    "duration": 1,
                    "filters": [{
                        "type": "watermark",
                        "watermark": {"image": "missing-logo.png"},
                    }],
                }],
            }]
        },
    })

    result = project_ops.validate_project(str(project))

    assert result.startswith("Valid project:")
    assert "Missing assets: missing-logo.png" in result


def test_unknown_preset_fails_explicitly(tmp_path):
    video = tmp_path / "video.mp4"
    video.touch()
    project = _write_project(tmp_path, {
        "version": "1.0",
        "timeline": {"tracks": [{"id": "main", "clips": [{"asset": "video.mp4", "start": 0, "duration": 1}]}]},
    })

    result = project_ops.render_project_file(str(project), preset="does-not-exist")
    assert result.startswith("Error: Unknown preset")


def test_auto_selects_mlt_for_dedicated_audio_when_mlt_can_preserve(tmp_path):
    video = tmp_path / "video.mp4"
    music = tmp_path / "music.mp3"
    video.touch(); music.touch()
    project = _write_project(tmp_path, {
        "version": "1.0",
        "timeline": {
            "tracks": [{"id": "main", "clips": [{"asset": "video.mp4", "start": 0, "duration": 2.0}]}],
            "audio": [{"asset": "music.mp3", "start": 0, "duration": 2.0}],
        },
    })

    prepared = project_ops.prepare_project(str(project), backend="auto")

    assert prepared.backend == "mlt"
    assert prepared.project is prepared.plan.project


def test_auto_fails_when_neither_backend_can_preserve_project(tmp_path):
    video = tmp_path / "video.mp4"
    music = tmp_path / "music.mp3"
    video.touch(); music.touch()
    project = _write_project(tmp_path, {
        "version": "1.0",
        "timeline": {
            "tracks": [{
                "id": "main",
                "clips": [
                    {"asset": "video.mp4", "start": 0, "duration": 2.0},
                    {
                        "asset": "video.mp4",
                        "start": 1.5,
                        "duration": 2.0,
                        "transition_in": {"type": "dissolve", "duration": 0.5},
                    },
                ],
            }],
            "audio": [{"asset": "music.mp3", "start": 0, "duration": 3.5}],
        },
    })

    with pytest.raises(ValueError, match="No backend can preserve"):
        project_ops.prepare_project(str(project), backend="auto")


def test_forced_mlt_rejects_unlowered_transition(tmp_path):
    video = tmp_path / "video.mp4"
    video.touch()
    project = _write_project(tmp_path, {
        "version": "1.0",
        "timeline": {"tracks": [{
            "id": "main",
            "clips": [
                {"asset": "video.mp4", "start": 0, "duration": 2.0},
                {"asset": "video.mp4", "start": 1.5, "duration": 2.0, "transition_in": {"type": "dissolve", "duration": 0.5}},
            ],
        }]},
    })

    with pytest.raises(ValueError, match="MLT backend cannot preserve"):
        project_ops.prepare_project(str(project), backend="mlt")
