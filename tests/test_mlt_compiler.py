from pathlib import Path
from declip.compilers import mlt
from declip.schema import Project

def test_mlt_compiler_normalizes_auto_starts(tmp_path: Path):
    project = Project.model_validate({"version":"1.0","timeline":{"tracks":[{"id":"main","clips":[{"asset":"a.mp4","start":0,"trim_out":2.0},{"asset":"b.mp4","start":"auto","trim_out":3.0}]}]}})
    compiled = mlt.compile_project(project, tmp_path)
    clips = compiled.plan.project.timeline.tracks[0].clips
    assert clips[1].start == 2.0 and clips[1].duration == 3.0
    assert str(tmp_path / "a.mp4") in compiled.xml
    assert str(tmp_path / "b.mp4") in compiled.xml
