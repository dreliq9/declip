from pathlib import Path

from declip.compilers.render_plan import build_render_plan
from declip.schema import Project


def test_render_plan_resolves_auto_start_without_mutating_source(tmp_path: Path):
    project = Project.model_validate({"version":"1.0","timeline":{"tracks":[{"id":"main","clips":[
        {"asset":"a.mp4","start":0,"trim_out":4.0},
        {"asset":"b.mp4","start":"auto","trim_out":3.0,"transition_in":{"type":"dissolve","duration":1.0}},
    ]}]}})
    plan = build_render_plan(project, tmp_path)
    clips = plan.project.timeline.tracks[0].clips
    assert project.timeline.tracks[0].clips[1].start == "auto"
    assert clips[0].start == 0.0 and clips[0].duration == 4.0
    assert clips[1].start == 3.0 and clips[1].duration == 3.0
    assert not plan.warnings


def test_render_plan_uses_injected_duration_resolver(tmp_path: Path):
    project = Project.model_validate({"version":"1.0","timeline":{"tracks":[{"id":"main","clips":[{"asset":"a.mp4","start":0,"trim_in":2.0}]}]}})
    plan = build_render_plan(project, tmp_path, duration_resolver=lambda _: 12.0)
    assert plan.project.timeline.tracks[0].clips[0].duration == 10.0
    assert not plan.warnings


def test_render_plan_surfaces_duration_fallback(tmp_path: Path):
    project = Project.model_validate({"version":"1.0","timeline":{"tracks":[{"id":"main","clips":[{"asset":"missing.mp4","start":0}]}]}})
    def fail(_: str) -> float:
        raise RuntimeError("probe failed")
    plan = build_render_plan(project, tmp_path, duration_resolver=fail)
    assert plan.project.timeline.tracks[0].clips[0].duration == 10.0
    assert len(plan.warnings) == 1
    assert plan.warnings[0].code == "duration-fallback"
    assert "probe failed" in plan.warnings[0].message


def test_freeze_frame_without_duration_gets_explicit_default(tmp_path: Path):
    project = Project.model_validate({"version":"1.0","timeline":{"tracks":[{"id":"main","clips":[{"asset":"a.mp4","start":0,"freeze_frame":1.0}]}]}})
    plan = build_render_plan(project, tmp_path)
    assert plan.project.timeline.tracks[0].clips[0].duration == 5.0
    assert "freeze-frame" in plan.warnings[0].message
