"""Tests for the declip schema."""

import json
import pytest
from declip.schema import Project, Clip, Filter, FilterType, Track, Timeline


def test_minimal_project():
    data = {
        "version": "1.0",
        "timeline": {
            "tracks": [
                {
                    "id": "main",
                    "clips": [{"asset": "test.mp4", "start": 0}],
                }
            ]
        },
    }
    p = Project.model_validate(data)
    assert p.settings.resolution == (1920, 1080)
    assert p.settings.fps == 30
    assert p.output.codec.value == "h264"
    assert len(p.timeline.tracks) == 1
    assert p.timeline.tracks[0].clips[0].asset == "test.mp4"


def test_trim_validation():
    with pytest.raises(Exception):
        Clip(asset="test.mp4", start=0, trim_in=5.0, trim_out=3.0)


def test_full_project_roundtrip(tmp_path):
    data = {
        "version": "1.0",
        "settings": {"resolution": [1280, 720], "fps": 24},
        "timeline": {
            "tracks": [
                {
                    "id": "main",
                    "clips": [
                        {
                            "asset": "a.mp4",
                            "start": 0,
                            "trim_in": 1.0,
                            "trim_out": 5.0,
                            "filters": [{"type": "fade_in", "duration": 0.5}],
                        },
                        {
                            "asset": "b.mp4",
                            "start": 4.0,
                            "transition_in": {"type": "dissolve", "duration": 1.0},
                        },
                    ],
                }
            ],
            "audio": [
                {"asset": "music.mp3", "volume": 0.5}
            ],
        },
        "output": {"path": "out.mp4", "quality": "medium"},
    }
    p = Project.model_validate(data)
    assert p.settings.resolution == (1280, 720)
    assert p.timeline.tracks[0].clips[1].transition_in.type.value == "dissolve"
    assert p.timeline.audio[0].volume == 0.5

    # Roundtrip via JSON
    out_file = tmp_path / "test.json"
    p.save(out_file)
    p2 = Project.load(out_file)
    assert p2.settings.fps == 24
    assert len(p2.timeline.tracks[0].clips) == 2


def test_invalid_version():
    with pytest.raises(Exception):
        Project.model_validate({
            "version": "2.0",
            "timeline": {"tracks": [{"id": "t", "clips": [{"asset": "x", "start": 0}]}]},
        })


def test_empty_tracks_rejected():
    with pytest.raises(Exception):
        Project.model_validate({
            "version": "1.0",
            "timeline": {"tracks": []},
        })


# ---------------------------------------------------------------------------
# Auto-sequencing tests (Phase 4)
# ---------------------------------------------------------------------------

def test_auto_start_first_clip_defaults_to_zero():
    """First clip with start='auto' should resolve to 0.0."""
    data = {
        "version": "1.0",
        "timeline": {
            "tracks": [{
                "id": "main",
                "clips": [{"asset": "a.mp4", "start": "auto", "duration": 5.0}],
            }]
        },
    }
    p = Project.model_validate(data)
    p.resolve_auto_starts()
    assert p.timeline.tracks[0].clips[0].start == 0.0


def test_auto_start_sequential():
    """Clips with start='auto' placed after previous clip ends."""
    data = {
        "version": "1.0",
        "timeline": {
            "tracks": [{
                "id": "main",
                "clips": [
                    {"asset": "a.mp4", "start": 0, "duration": 5.0},
                    {"asset": "b.mp4", "start": "auto", "duration": 3.0},
                    {"asset": "c.mp4", "start": "auto", "duration": 4.0},
                ],
            }]
        },
    }
    p = Project.model_validate(data)
    p.resolve_auto_starts()
    clips = p.timeline.tracks[0].clips
    assert clips[0].start == 0
    assert clips[1].start == 5.0
    assert clips[2].start == 8.0


def test_auto_start_with_transition_overlap():
    """Auto-placed clips with transitions overlap by transition duration."""
    data = {
        "version": "1.0",
        "timeline": {
            "tracks": [{
                "id": "main",
                "clips": [
                    {"asset": "a.mp4", "start": 0, "duration": 5.0},
                    {
                        "asset": "b.mp4",
                        "start": "auto",
                        "duration": 3.0,
                        "transition_in": {"type": "dissolve", "duration": 1.0},
                    },
                ],
            }]
        },
    }
    p = Project.model_validate(data)
    p.resolve_auto_starts()
    clips = p.timeline.tracks[0].clips
    # Should be placed at 5.0 - 1.0 (transition overlap) = 4.0
    assert clips[1].start == 4.0


def test_auto_start_with_trim():
    """Auto-placed clips use trim_out - trim_in for duration when no explicit duration."""
    data = {
        "version": "1.0",
        "timeline": {
            "tracks": [{
                "id": "main",
                "clips": [
                    {"asset": "a.mp4", "start": 0, "trim_in": 2.0, "trim_out": 7.0},
                    {"asset": "b.mp4", "start": "auto", "duration": 3.0},
                ],
            }]
        },
    }
    p = Project.model_validate(data)
    p.resolve_auto_starts()
    clips = p.timeline.tracks[0].clips
    # First clip duration = 7.0 - 2.0 = 5.0, so second clip starts at 5.0
    assert clips[1].start == 5.0


def test_auto_start_mixed_with_manual():
    """Mix of auto and manual start values works correctly."""
    data = {
        "version": "1.0",
        "timeline": {
            "tracks": [{
                "id": "main",
                "clips": [
                    {"asset": "a.mp4", "start": 0, "duration": 5.0},
                    {"asset": "b.mp4", "start": "auto", "duration": 3.0},
                    {"asset": "c.mp4", "start": 20.0, "duration": 4.0},  # manual gap
                    {"asset": "d.mp4", "start": "auto", "duration": 2.0},
                ],
            }]
        },
    }
    p = Project.model_validate(data)
    p.resolve_auto_starts()
    clips = p.timeline.tracks[0].clips
    assert clips[1].start == 5.0
    assert clips[2].start == 20.0  # manual, unchanged
    assert clips[3].start == 24.0  # auto after manual clip


def test_auto_start_invalid_string_rejected():
    """Non-'auto' strings in start are rejected by validation."""
    with pytest.raises(Exception):
        Clip(asset="test.mp4", start="beginning", duration=5.0)
