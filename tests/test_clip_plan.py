from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from declip.clip_plan import (
    ClipPlanImportError,
    MATERIALIZED_SCHEMA,
    PROVENANCE_SCHEMA,
    project_from_materialized_clip_plan,
)
from declip.schema import Project


def _write_asset(path: Path, payload: bytes) -> str:
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _manifest(tmp_path: Path) -> Path:
    a = tmp_path / "clip-a.mp4"
    b = tmp_path / "clip-b.mp4"
    sha_a = _write_asset(a, b"clip-a")
    sha_b = _write_asset(b, b"clip-b")
    manifest = {
        "schema": MATERIALIZED_SCHEMA,
        "plan_revision": "cp-aaaaaaaaaaaaaaaaaaaaaaaa",
        "materialization_revision": "cm-bbbbbbbbbbbbbbbbbbbbbbbb",
        "assets": [
            {
                "clip_id": "clip-001",
                "video_id": "jNQXAC9IVRw",
                "title": "History",
                "channel": "Historian",
                "source_url": "https://www.youtube.com/watch?v=jNQXAC9IVRw",
                "source_start_s": 98.0,
                "source_end_s": 108.0,
                "duration_s": 10.0,
                "path": str(a),
                "sha256": sha_a,
            },
            {
                "clip_id": "clip-002",
                "video_id": "dQw4w9WgXcQ",
                "title": "Artist",
                "channel": "Studio",
                "source_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "source_start_s": 40.0,
                "source_end_s": 46.0,
                "duration_s": 6.0,
                "path": str(b),
                "sha256": sha_b,
            },
        ],
    }
    path = tmp_path / "materialized.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    return path


def test_import_builds_native_project_in_manifest_order(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    destination = tmp_path / "project.json"

    result = project_from_materialized_clip_plan(
        manifest,
        destination,
        output_path="remix.mp4",
    )

    project = Project.load(destination)
    clips = project.timeline.tracks[0].clips
    assert len(clips) == 2
    assert Path(clips[0].asset).name == "clip-a.mp4"
    assert clips[0].start == 0.0
    assert clips[0].trim_in == 0.0
    assert clips[0].trim_out == 10.0
    assert Path(clips[1].asset).name == "clip-b.mp4"
    assert clips[1].start == "auto"
    assert clips[1].trim_out == 6.0
    assert project.output.path == "remix.mp4"
    assert result["rendered"] is False
    assert result["hashes_verified"] is True

    provenance = json.loads(Path(result["provenance_path"]).read_text())
    assert provenance["schema"] == PROVENANCE_SCHEMA
    assert provenance["timeline_order"] == ["clip-001", "clip-002"]
    assert provenance["sources"][0]["source_start_s"] == 98.0
    assert provenance["sources"][1]["video_id"] == "dQw4w9WgXcQ"


def test_import_can_add_transitions_without_changing_source_ranges(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    destination = tmp_path / "project.json"

    project_from_materialized_clip_plan(
        manifest,
        destination,
        transition="dissolve",
        transition_duration=0.75,
    )
    project = Project.load(destination)
    first, second = project.timeline.tracks[0].clips
    assert first.transition_in is None
    assert second.transition_in is not None
    assert second.transition_in.type.value == "dissolve"
    assert second.transition_in.duration == 0.75
    assert first.trim_out == 10.0
    assert second.trim_out == 6.0


def test_import_rejects_modified_materialized_asset(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    data = json.loads(manifest.read_text())
    Path(data["assets"][0]["path"]).write_bytes(b"tampered")

    with pytest.raises(ClipPlanImportError, match="SHA-256 mismatch"):
        project_from_materialized_clip_plan(manifest, tmp_path / "project.json")


def test_import_rejects_unknown_schema(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    data = json.loads(manifest.read_text())
    data["schema"] = "other/v1"
    manifest.write_text(json.dumps(data))

    with pytest.raises(ClipPlanImportError, match="unsupported manifest schema"):
        project_from_materialized_clip_plan(manifest, tmp_path / "project.json")


def test_import_does_not_overwrite_existing_project_by_default(tmp_path: Path) -> None:
    manifest = _manifest(tmp_path)
    destination = tmp_path / "project.json"
    destination.write_text("existing")

    with pytest.raises(ClipPlanImportError, match="project already exists"):
        project_from_materialized_clip_plan(manifest, destination)
    assert destination.read_text() == "existing"
