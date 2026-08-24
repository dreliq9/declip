from pathlib import Path

import pytest

from declip.compilers import mlt
from declip.compilers.render_plan import build_render_plan
from declip.schema import Project


def test_mlt_compiler_normalizes_auto_starts(tmp_path: Path):
    project = Project.model_validate({"version":"1.0","timeline":{"tracks":[{"id":"main","clips":[{"asset":"a.mp4","start":0,"trim_out":2.0},{"asset":"b.mp4","start":"auto","trim_out":3.0}]}]}})
    compiled = mlt.compile_project(project, tmp_path)
    clips = compiled.plan.project.timeline.tracks[0].clips
    assert clips[1].start == 2.0 and clips[1].duration == 3.0
    assert str(tmp_path / "a.mp4") in compiled.xml
    assert str(tmp_path / "b.mp4") in compiled.xml


def test_mlt_profile_uses_xml_attributes(tmp_path: Path):
    project = Project.model_validate({
        "version": "1.0",
        "settings": {"resolution": [1280, 720], "fps": 24},
        "timeline": {"tracks": [{"id": "main", "clips": [{"asset": "a.mp4", "start": 0, "duration": 1.0}]}]},
    })
    root = mlt.compile_project(project, tmp_path).tree.getroot()
    profile = root.find("profile")
    assert profile is not None
    assert profile.get("width") == "1280"
    assert profile.get("height") == "720"
    assert profile.get("frame_rate_num") == "24"
    assert profile.get("frame_rate_den") == "1"
    assert profile.find("property") is None


def test_mlt_graph_is_bounded_to_normalized_timeline(tmp_path: Path):
    project = Project.model_validate({
        "version": "1.0",
        "settings": {"fps": 30},
        "timeline": {"tracks": [{"id": "main", "clips": [{"asset": "a.mp4", "start": 0, "duration": 2.0}]}]},
    })
    root = mlt.compile_project(project, tmp_path).tree.getroot()
    background = root.find("./playlist[@id='playlist_bg']/entry")
    tractor = root.find("./tractor[@id='main']")
    assert background is not None and tractor is not None
    assert background.get("out") == "59"
    assert tractor.get("out") == "59"


def test_mlt_rejects_same_track_transition_until_playlist_mix_is_lowered(tmp_path: Path):
    project = Project.model_validate({
        "version": "1.0",
        "timeline": {"tracks": [{"id": "main", "clips": [
            {"asset": "a.mp4", "start": 0, "duration": 2.0},
            {"asset": "b.mp4", "start": 1.5, "duration": 2.0, "transition_in": {"type": "dissolve", "duration": 0.5}},
        ]}]},
    })

    plan = build_render_plan(project, tmp_path)
    assert mlt.can_handle(plan.project) is False
    assert any("transition_in" in reason for reason in mlt.unsupported_reasons(plan.project))
    with pytest.raises(mlt.CompilationError):
        mlt.compile_project(project, tmp_path)


def test_mlt_rejects_unlowered_clip_semantics(tmp_path: Path):
    project = Project.model_validate({
        "version": "1.0",
        "timeline": {"tracks": [{"id": "main", "clips": [{
            "asset": "a.mp4", "start": 0, "duration": 2.0, "reverse": True,
        }]}]},
    })
    plan = build_render_plan(project, tmp_path)
    assert mlt.can_handle(plan.project) is False
    assert any("reverse" in reason for reason in mlt.unsupported_reasons(plan.project))


def test_mlt_rejects_alpha_without_explicit_compositor(tmp_path: Path):
    project = Project.model_validate({
        "version": "1.0",
        "timeline": {"tracks": [{"id": "main", "clips": [{
            "asset": "a.mp4", "start": 0, "duration": 2.0, "opacity": 0.5,
        }]}]},
    })
    plan = build_render_plan(project, tmp_path)
    assert any("opacity" in reason for reason in mlt.unsupported_reasons(plan.project))


def test_mlt_accepts_dedicated_audio_without_unlowered_features(tmp_path: Path):
    project = Project.model_validate({
        "version": "1.0",
        "timeline": {
            "tracks": [{"id": "main", "clips": [{"asset": "a.mp4", "start": 0, "duration": 3.0}]}],
            "audio": [{"asset": "music.mp3", "start": 0.5, "duration": 2.0}],
        },
    })
    plan = build_render_plan(project, tmp_path)
    assert mlt.can_handle(plan.project) is True
    compiled = mlt.compile_project(project, tmp_path)
    assert "playlist_audio0" in compiled.xml


def test_mlt_entry_uses_trim_in_plus_explicit_duration(tmp_path: Path):
    project = Project.model_validate({
        "version": "1.0",
        "settings": {"fps": 30},
        "timeline": {"tracks": [{"id": "main", "clips": [{
            "asset": "a.mp4", "start": 0, "trim_in": 2.0, "duration": 3.0,
        }]}]},
    })
    root = mlt.compile_project(project, tmp_path).tree.getroot()
    entry = root.find("./playlist[@id='playlist_main']/entry")
    assert entry is not None
    assert entry.get("in") == "60"
    assert entry.get("out") == "149"


def test_mlt_manual_gap_is_preserved_as_playlist_blank(tmp_path: Path):
    project = Project.model_validate({
        "version": "1.0",
        "settings": {"fps": 30},
        "timeline": {"tracks": [{"id": "main", "clips": [
            {"asset": "a.mp4", "start": 0, "duration": 1.0},
            {"asset": "b.mp4", "start": 3.0, "duration": 1.0},
        ]}]},
    })
    root = mlt.compile_project(project, tmp_path).tree.getroot()
    playlist = root.find("./playlist[@id='playlist_main']")
    assert playlist is not None
    blank = playlist.find("blank")
    assert blank is not None
    assert blank.get("length") == "60"


def test_mlt_uses_native_track_precedence_for_opaque_video(tmp_path: Path):
    project = Project.model_validate({
        "version": "1.0",
        "timeline": {"tracks": [
            {"id": "base", "clips": [{"asset": "a.mp4", "start": 0, "duration": 2.0}]},
            {"id": "upper", "clips": [{"asset": "b.mp4", "start": 0, "duration": 1.0}]},
        ]},
    })
    root = mlt.compile_project(project, tmp_path).tree.getroot()
    services = [
        prop.text
        for transition in root.findall("./tractor/transition")
        for prop in transition.findall("property")
        if prop.get("name") == "mlt_service"
    ]
    assert "frei0r.cairoblend" not in services
    assert set(services) <= {"mix"}


def test_mlt_audio_mix_uses_distinct_tracks(tmp_path: Path):
    project = Project.model_validate({
        "version": "1.0",
        "timeline": {
            "tracks": [{"id": "main", "clips": [{"asset": "a.mp4", "start": 0, "duration": 2.0}]}],
            "audio": [{"asset": "music.mp3", "start": 0, "duration": 2.0}],
        },
    })
    root = mlt.compile_project(project, tmp_path).tree.getroot()
    mix_transitions = []
    for transition in root.findall("./tractor/transition"):
        props = {prop.get("name"): prop.text for prop in transition.findall("property")}
        if props.get("mlt_service") == "mix":
            mix_transitions.append(props)
    assert mix_transitions
    assert all(props["a_track"] == "0" for props in mix_transitions)
    assert all(props["b_track"] != props["a_track"] for props in mix_transitions)
