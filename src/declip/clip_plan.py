"""Import youtube-mcp materialized clip plans into native Declip projects."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import Clip, Output, Project, Settings, Timeline, Track, Transition, TransitionType

MATERIALIZED_SCHEMA = "youtube-mcp.materialized-clip-plan/v1"
PROVENANCE_SCHEMA = "declip.youtube-mcp-provenance/v1"


class ClipPlanImportError(RuntimeError):
    pass


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_materialized_manifest(path: str | Path) -> tuple[Path, dict[str, Any]]:
    manifest_path = Path(path).expanduser().resolve()
    if not manifest_path.exists() or not manifest_path.is_file():
        raise ClipPlanImportError(f"materialized clip-plan manifest not found: {manifest_path}")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClipPlanImportError(f"materialized clip-plan manifest is unreadable: {manifest_path}") from exc
    if data.get("schema") != MATERIALIZED_SCHEMA:
        raise ClipPlanImportError(
            f"unsupported manifest schema: {data.get('schema')!r}; expected {MATERIALIZED_SCHEMA!r}"
        )
    assets = data.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ClipPlanImportError("materialized clip-plan contains no assets")
    return manifest_path, data


def _validated_assets(manifest: dict[str, Any], *, verify_hashes: bool) -> list[dict[str, Any]]:
    validated: list[dict[str, Any]] = []
    seen_clip_ids: set[str] = set()
    for index, raw in enumerate(manifest.get("assets") or [], start=1):
        if not isinstance(raw, dict):
            raise ClipPlanImportError(f"asset {index} is not an object")
        clip_id = str(raw.get("clip_id") or "")
        if not clip_id:
            raise ClipPlanImportError(f"asset {index} is missing clip_id")
        if clip_id in seen_clip_ids:
            raise ClipPlanImportError(f"duplicate clip_id in manifest: {clip_id}")
        seen_clip_ids.add(clip_id)

        asset_path = Path(str(raw.get("path") or "")).expanduser().resolve()
        if not asset_path.exists() or not asset_path.is_file():
            raise ClipPlanImportError(f"materialized asset is missing: {asset_path}")
        try:
            duration_s = float(raw.get("duration_s"))
        except (TypeError, ValueError) as exc:
            raise ClipPlanImportError(f"asset {clip_id} has invalid duration_s") from exc
        if duration_s <= 0:
            raise ClipPlanImportError(f"asset {clip_id} duration_s must be positive")

        expected_sha = str(raw.get("sha256") or "")
        if verify_hashes:
            if len(expected_sha) != 64:
                raise ClipPlanImportError(f"asset {clip_id} has no valid SHA-256")
            actual_sha = _sha256(asset_path)
            if actual_sha != expected_sha:
                raise ClipPlanImportError(
                    f"asset {clip_id} SHA-256 mismatch: expected {expected_sha}, got {actual_sha}"
                )

        item = dict(raw)
        item["path"] = str(asset_path)
        item["duration_s"] = duration_s
        validated.append(item)
    return validated


def project_from_materialized_clip_plan(
    manifest_path: str | Path,
    project_path: str | Path,
    *,
    output_path: str = "output.mp4",
    resolution: tuple[int, int] = (1920, 1080),
    fps: int = 30,
    transition: str = "none",
    transition_duration: float = 0.5,
    verify_hashes: bool = True,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Create a native Declip project from youtube-mcp materialized assets.

    Materialized youtube-mcp clips are already source-trimmed. Declip therefore
    places them in manifest order with trim_in=0 and trim_out=duration_s.
    """
    source_manifest_path, manifest = load_materialized_manifest(manifest_path)
    assets = _validated_assets(manifest, verify_hashes=verify_hashes)

    destination = Path(project_path).expanduser().resolve()
    if destination.suffix.lower() != ".json":
        raise ClipPlanImportError("project_path must end in .json")
    if destination.exists() and not overwrite:
        raise ClipPlanImportError(f"project already exists: {destination}")
    if resolution[0] <= 0 or resolution[1] <= 0:
        raise ClipPlanImportError("resolution dimensions must be positive")
    if fps <= 0 or fps > 120:
        raise ClipPlanImportError("fps must be between 1 and 120")
    if transition_duration <= 0:
        raise ClipPlanImportError("transition_duration must be positive")

    transition_type: TransitionType | None
    if transition == "none":
        transition_type = None
    else:
        try:
            transition_type = TransitionType(transition)
        except ValueError as exc:
            allowed = ["none", *(item.value for item in TransitionType)]
            raise ClipPlanImportError(
                f"unsupported transition {transition!r}; expected one of {allowed}"
            ) from exc

    clips: list[Clip] = []
    for index, asset in enumerate(assets):
        transition_in = None
        if index > 0 and transition_type is not None:
            transition_in = Transition(type=transition_type, duration=transition_duration)
        clips.append(
            Clip(
                asset=asset["path"],
                start=0.0 if index == 0 else "auto",
                trim_in=0.0,
                trim_out=float(asset["duration_s"]),
                transition_in=transition_in,
            )
        )

    project = Project(
        settings=Settings(resolution=resolution, fps=fps),
        timeline=Timeline(tracks=[Track(id="main", clips=clips)]),
        output=Output(path=output_path),
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    project.save(destination)

    sidecar_path = destination.with_name(destination.stem + ".sources.json")
    if sidecar_path.exists() and not overwrite:
        destination.unlink(missing_ok=True)
        raise ClipPlanImportError(f"provenance sidecar already exists: {sidecar_path}")

    provenance = {
        "schema": PROVENANCE_SCHEMA,
        "created_at": _now_iso(),
        "project_path": str(destination),
        "source_manifest_path": str(source_manifest_path),
        "source_manifest_schema": manifest.get("schema"),
        "plan_revision": manifest.get("plan_revision"),
        "materialization_revision": manifest.get("materialization_revision"),
        "verify_hashes": verify_hashes,
        "timeline_order": [str(asset["clip_id"]) for asset in assets],
        "sources": [
            {
                key: asset.get(key)
                for key in (
                    "clip_id",
                    "video_id",
                    "title",
                    "channel",
                    "source_url",
                    "source_start_s",
                    "source_end_s",
                    "duration_s",
                    "sha256",
                    "path",
                )
            }
            for asset in assets
        ],
    }
    sidecar_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False), encoding="utf-8")

    return {
        "project_path": str(destination),
        "provenance_path": str(sidecar_path),
        "clip_count": len(clips),
        "plan_revision": manifest.get("plan_revision"),
        "materialization_revision": manifest.get("materialization_revision"),
        "hashes_verified": verify_hashes,
        "rendered": False,
    }
