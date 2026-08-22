import json

from declip import project_ops


def test_validate_project_checks_filter_assets(tmp_path):
    video = tmp_path / "video.mp4"
    video.touch()
    project = tmp_path / "project.json"
    project.write_text(json.dumps({
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
    }))

    result = project_ops.validate_project(str(project))

    assert result.startswith("Valid project:")
    assert "Missing assets: missing-logo.png" in result


def test_unknown_preset_fails_explicitly(tmp_path):
    video = tmp_path / "video.mp4"
    video.touch()
    project = tmp_path / "project.json"
    project.write_text(json.dumps({
        "version": "1.0",
        "timeline": {"tracks": [{"id": "main", "clips": [{"asset": "video.mp4", "start": 0, "duration": 1}]}]},
    }))

    result = project_ops.render_project_file(str(project), preset="does-not-exist")
    assert result.startswith("Error: Unknown preset")
