"""Tests for the ops module — shared operations logic."""

import pytest
from declip.ops import (
    resolve_loudnorm_target,
    LOUDNORM_TARGETS,
    _output_path,
)


# ---------------------------------------------------------------------------
# Output path helper
# ---------------------------------------------------------------------------

def test_output_path_explicit():
    assert _output_path("video.mp4", "/tmp/out.mp4", "_suffix") == "/tmp/out.mp4"


def test_output_path_suffix():
    assert _output_path("video.mp4", None, "_reversed").endswith("video_reversed.mp4")


def test_output_path_extension_swap():
    result = _output_path("video.mp4", None, ".gif")
    assert result.endswith("video.gif")


# ---------------------------------------------------------------------------
# Loudnorm target resolution
# ---------------------------------------------------------------------------

def test_loudnorm_named_targets():
    for name, expected in LOUDNORM_TARGETS.items():
        lufs, err = resolve_loudnorm_target(name)
        assert err is None, f"Failed for {name}: {err}"
        assert lufs == expected


def test_loudnorm_case_insensitive():
    lufs, err = resolve_loudnorm_target("YouTube")
    assert err is None
    assert lufs == -14.0


def test_loudnorm_custom_number():
    lufs, err = resolve_loudnorm_target("-18")
    assert err is None
    assert lufs == -18.0


def test_loudnorm_custom_positive():
    lufs, err = resolve_loudnorm_target("0")
    assert err is None
    assert lufs == 0.0


def test_loudnorm_invalid_string():
    lufs, err = resolve_loudnorm_target("notaplatform")
    assert lufs is None
    assert "Invalid target" in err


# ---------------------------------------------------------------------------
# File-not-found handling (no FFmpeg needed)
# ---------------------------------------------------------------------------

def test_speed_missing_file():
    from declip.ops import speed
    ok, msg = speed("/nonexistent/file.mp4", 2.0)
    assert not ok
    assert "not found" in msg


def test_stabilize_missing_file():
    from declip.ops import stabilize
    ok, msg = stabilize("/nonexistent/file.mp4")
    assert not ok
    assert "not found" in msg


def test_reverse_missing_file():
    from declip.ops import reverse
    ok, msg = reverse("/nonexistent/file.mp4")
    assert not ok
    assert "not found" in msg


def test_denoise_missing_file():
    from declip.ops import denoise
    ok, msg = denoise("/nonexistent/file.mp4")
    assert not ok
    assert "not found" in msg


def test_loudnorm_missing_file():
    from declip.ops import loudnorm
    ok, msg = loudnorm("/nonexistent/file.mp4")
    assert not ok
    assert "not found" in msg


def test_sidechain_missing_video():
    from declip.ops import sidechain
    ok, msg = sidechain("/nonexistent/video.mp4", "/nonexistent/music.mp3")
    assert not ok
    assert "not found" in msg


def test_color_grade_missing_file():
    from declip.ops import color_grade
    ok, msg = color_grade("/nonexistent/file.mp4", temperature=0.5)
    assert not ok
    assert "not found" in msg


def test_color_grade_no_params(tmp_path):
    # Need an existing file to get past the file-exists check
    dummy = tmp_path / "test.mp4"
    dummy.write_bytes(b"\x00")
    from declip.ops import color_grade
    ok, msg = color_grade(str(dummy))
    assert not ok
    assert "provide at least one" in msg.lower()


def test_speed_zero_rejected():
    from declip.ops import speed
    ok, msg = speed("/nonexistent/file.mp4", 0)
    assert not ok
    assert "positive" in msg.lower()


def test_speed_negative_rejected():
    from declip.ops import speed
    ok, msg = speed("/nonexistent/file.mp4", -1.0)
    assert not ok
    assert "positive" in msg.lower()
