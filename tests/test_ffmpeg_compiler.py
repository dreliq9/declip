from pathlib import Path
import pytest
from declip.compilers import ffmpeg
from declip.schema import Project


def _project(clips, *, audio=None):
    return Project.model_validate({"version":"1.0","timeline":{"tracks":[{"id":"main","clips":clips}],"audio":audio or []},"output":{"path":"out.mp4"}})

def _filter_graph(command: list[str]) -> str:
    return command[command.index("-filter_complex") + 1]

def test_input_duration_is_scoped_before_each_input(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ffmpeg, "_has_audio", lambda _: False)
    project = _project([{"asset":"a.mp4","start":0,"trim_out":2.0},{"asset":"b.mp4","start":2.0,"trim_in":1.0,"trim_out":4.0}])
    command = ffmpeg.compile_commands(project, tmp_path)[0]
    assert ["-t","2.0","-i",str(tmp_path / "a.mp4")] == command[2:6]
    second_i = command.index(str(tmp_path / "b.mp4"))
    assert command[second_i - 5:second_i + 1] == ["-ss","1.0","-t","3.0","-i",str(tmp_path / "b.mp4")]

def test_multi_clip_watermark_is_compiled(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ffmpeg, "_has_audio", lambda _: False)
    project = _project([
        {"asset":"a.mp4","start":0,"trim_out":2.0,"filters":[{"type":"watermark","watermark":{"image":"logo.png","position":[0.95,0.05],"scale":0.1,"opacity":0.7}}]},
        {"asset":"b.mp4","start":2.0,"trim_out":2.0},
    ])
    command = ffmpeg.compile_commands(project, tmp_path)[0]
    inputs = [command[i+1] for i, token in enumerate(command[:-1]) if token == "-i"]
    assert inputs == [str(tmp_path / "a.mp4"), str(tmp_path / "b.mp4"), str(tmp_path / "logo.png")]
    graph = _filter_graph(command)
    assert "[2:v]scale=192:-1" in graph
    assert "overlay=x='(W-w)*0.95':y='(H-h)*0.05'" in graph
    assert "concat=n=2:v=1:a=0[outv]" in graph

def test_reverse_applies_to_audio_in_multiclip(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ffmpeg, "_has_audio", lambda _: True)
    graph = _filter_graph(ffmpeg.compile_commands(_project([{"asset":"a.mp4","start":0,"trim_out":2.0,"reverse":True},{"asset":"b.mp4","start":2.0,"trim_out":2.0}]), tmp_path)[0])
    assert "reverse" in graph and "areverse" in graph

def test_freeze_frame_uses_shared_multiclip_lowering(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ffmpeg, "_has_audio", lambda _: True)
    command = ffmpeg.compile_commands(_project([{"asset":"a.mp4","start":0,"duration":2.0,"freeze_frame":1.5},{"asset":"b.mp4","start":2.0,"trim_out":2.0}]), tmp_path)[0]
    first_i = command.index(str(tmp_path / "a.mp4"))
    assert command[first_i - 5:first_i + 1] == ["-ss","1.5","-t","2.0","-i",str(tmp_path / "a.mp4")]
    graph = _filter_graph(command)
    assert "loop=loop=-1:size=1:start=0" in graph and "atrim=duration=2.0" in graph

def test_mixed_transition_graph_uses_real_concat_for_hard_cut(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(ffmpeg, "_has_audio", lambda _: False)
    project = _project([
        {"asset":"a.mp4","start":0,"trim_out":3.0},
        {"asset":"b.mp4","start":2.5,"trim_out":3.0,"transition_in":{"type":"dissolve","duration":0.5}},
        {"asset":"c.mp4","start":5.5,"trim_out":2.0},
    ])
    graph = _filter_graph(ffmpeg.compile_commands(project, tmp_path)[0])
    assert "xfade=transition=fade:duration=0.5" in graph
    assert "concat=n=2:v=1:a=0[outv]" in graph
    assert "duration=0.001" not in graph

def test_dedicated_audio_routes_away_from_ffmpeg(tmp_path: Path):
    project = _project([{"asset":"a.mp4","start":0,"trim_out":2.0}], audio=[{"asset":"music.mp3","start":0}])
    assert ffmpeg.can_handle(project) is False
    with pytest.raises(ffmpeg.CompilationError):
        ffmpeg.compile_commands(project, tmp_path)
