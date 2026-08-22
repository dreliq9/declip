"""Backend-neutral render-plan normalization.

The public project schema is intentionally convenient for authors: clip starts may
be ``"auto"`` and clip durations may be omitted. Backends should not each
re-interpret those conveniences. This module resolves them once into a deep-copied
Project whose clip starts and durations are explicit.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from declip.schema import Clip, Project

DurationResolver = Callable[[str], float]


@dataclass(frozen=True)
class PlanWarning:
    """A non-fatal normalization fallback that callers may surface to users."""

    code: str
    message: str
    track_id: str | None = None
    clip_index: int | None = None


@dataclass(frozen=True)
class RenderPlan:
    """Normalized project plus compiler diagnostics."""

    project: Project
    project_dir: Path
    warnings: tuple[PlanWarning, ...] = ()


class RenderPlanError(ValueError):
    """Raised when a project cannot be normalized safely."""


def resolve_asset(asset: str, project_dir: Path) -> str:
    path = Path(asset)
    if path.is_absolute():
        return str(path)
    return str(project_dir / path)


def _default_duration_resolver(asset_path: str) -> float:
    from declip.probe import probe

    return float(probe(asset_path).duration)


def _clip_duration(
    clip: Clip,
    asset_path: str,
    duration_resolver: DurationResolver,
    fallback_duration: float,
) -> tuple[float, str | None]:
    if clip.duration is not None:
        return float(clip.duration), None
    if clip.trim_out is not None:
        return float(clip.trim_out - clip.trim_in), None
    if clip.freeze_frame is not None:
        return 5.0, "freeze-frame clip has no duration; using 5.0s"

    try:
        source_duration = float(duration_resolver(asset_path))
        duration = source_duration - float(clip.trim_in)
        if duration <= 0:
            raise ValueError("resolved duration is not positive")
        return duration, None
    except Exception as exc:
        if fallback_duration <= 0:
            raise RenderPlanError(
                f"Could not resolve duration for {asset_path}: {exc}"
            ) from exc
        return float(fallback_duration), (
            f"could not resolve duration for {asset_path}; "
            f"using {fallback_duration:.1f}s fallback ({exc})"
        )


def build_render_plan(
    project: Project,
    project_dir: Path,
    *,
    duration_resolver: DurationResolver | None = None,
    fallback_duration: float = 10.0,
) -> RenderPlan:
    """Return a normalized deep copy of ``project``.

    Normalization guarantees for every video clip:
    - ``start`` is a float, never ``"auto"``.
    - ``duration`` is explicit and positive.
    - automatic starts preserve transition overlap semantics.

    Duration probing is injectable so compilers can be unit-tested without media
    files. Probe failures are preserved as warnings instead of disappearing into
    backend-specific magic constants.
    """

    project_dir = Path(project_dir)
    normalized = project.model_copy(deep=True)
    resolver = duration_resolver or _default_duration_resolver
    warnings: list[PlanWarning] = []

    for track in normalized.timeline.tracks:
        cursor = 0.0
        for index, clip in enumerate(track.clips):
            asset_path = resolve_asset(clip.asset, project_dir)
            duration, warning = _clip_duration(
                clip, asset_path, resolver, fallback_duration
            )
            if duration <= 0:
                raise RenderPlanError(
                    f"Clip {track.id}[{index}] has non-positive duration {duration}"
                )

            if clip.start == "auto":
                start = 0.0 if index == 0 else cursor
                if index > 0 and clip.transition_in is not None:
                    start = max(0.0, start - clip.transition_in.duration)
                clip.start = start
            else:
                clip.start = float(clip.start)

            clip.duration = duration
            cursor = float(clip.start) + duration

            if warning:
                warnings.append(
                    PlanWarning(
                        code="duration-fallback",
                        message=warning,
                        track_id=track.id,
                        clip_index=index,
                    )
                )

    return RenderPlan(
        project=normalized,
        project_dir=project_dir,
        warnings=tuple(warnings),
    )
