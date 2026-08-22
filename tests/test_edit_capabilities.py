from types import SimpleNamespace

from declip import edit
import declip.probe


def test_color_combines_basic_and_advanced_in_one_encode(monkeypatch, tmp_path):
    source = tmp_path / "input.mp4"
    source.touch()
    calls = []

    def fake_run(command, timeout=300):
        calls.append(command)
        return True, ""

    monkeypatch.setattr(edit, "_run_ffmpeg", fake_run)
    result = edit.color(
        str(source),
        brightness=0.1,
        temperature=0.2,
        shadows_r=0.1,
        auto_levels=True,
    )

    assert result.startswith("Color adjusted:")
    assert len(calls) == 1
    graph = calls[0][calls[0].index("-vf") + 1]
    assert "eq=brightness=0.1" in graph
    assert "colorbalance=" in graph
    assert "colortemperature=" in graph
    assert "normalize" in graph


def test_freeze_frame_does_not_limit_output_to_one_frame(monkeypatch, tmp_path):
    source = tmp_path / "input.mp4"
    source.touch()
    calls = []
    monkeypatch.setattr(edit, "_run_ffmpeg", lambda command, timeout=300: (calls.append(command) or True, ""))

    result = edit.freeze_frame(str(source), timestamp=1.25, hold_duration=3.0, fps=30)

    assert result.startswith("Freeze frame")
    assert "-frames:v" not in calls[0]
    graph = calls[0][calls[0].index("-vf") + 1]
    assert "loop=loop=-1:size=1:start=0" in graph
    assert calls[0][calls[0].index("-t") + 1] == "3.0"


def test_image_overlay_scales_from_probed_main_width(monkeypatch, tmp_path):
    source = tmp_path / "input.mp4"
    logo = tmp_path / "logo.png"
    source.touch(); logo.touch()
    monkeypatch.setattr(declip.probe, "probe", lambda _: SimpleNamespace(width=1000))
    calls = []
    monkeypatch.setattr(edit, "_run_ffmpeg", lambda command, timeout=300: (calls.append(command) or True, ""))

    edit.image_overlay(str(source), str(logo), scale=0.2)

    graph = calls[0][calls[0].index("-filter_complex") + 1]
    assert "scale=200:-2" in graph
    assert "main_w" not in graph
