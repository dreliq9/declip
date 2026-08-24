from declip.schema import Project


def test_legacy_resolve_auto_starts_uses_canonical_render_plan():
    project = Project.model_validate({
        "version": "1.0",
        "timeline": {
            "tracks": [{
                "id": "main",
                "clips": [
                    {"asset": "a.mp4", "start": 0, "trim_in": 2.0, "trim_out": 7.0},
                    {
                        "asset": "b.mp4",
                        "start": "auto",
                        "duration": 3.0,
                        "transition_in": {"type": "dissolve", "duration": 1.0},
                    },
                ],
            }]
        },
    })

    project.resolve_auto_starts()
    clips = project.timeline.tracks[0].clips

    assert clips[0].duration == 5.0
    assert clips[1].start == 4.0
    assert clips[1].duration == 3.0
