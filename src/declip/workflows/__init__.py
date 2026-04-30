"""Declarative high-level workflows that orchestrate declip's primitives.

Each module exposes a `run(...)` function that takes typed inputs and returns
a typed Pydantic `WorkflowResult`. Workflows call `declip.analyze.*`,
`declip.ops.*`, and the FFmpeg backend directly — no MCP/CLI subprocess hops.

Public modules:
- ingest        — probe + loudnorm + optional auto-grade
- cutdown       — long source → short highlight via scene/silence detect
- speech_cleanup — talking-head jump-cut edit (Whisper + silence detect)
- beat_sync     — cut video on the beats of a music track
- vertical      — 16:9 → 9:16 reformat (crop / pad / blur-pad)
- review        — Phase 0–3 QA pack
"""

from __future__ import annotations

from declip.workflows.types import (
    BeatSyncResult,
    CutdownResult,
    IngestResult,
    ReviewResult,
    SpeechCleanupResult,
    VerticalResult,
    WorkflowResult,
)

__all__ = [
    "WorkflowResult",
    "IngestResult",
    "CutdownResult",
    "SpeechCleanupResult",
    "BeatSyncResult",
    "VerticalResult",
    "ReviewResult",
]
