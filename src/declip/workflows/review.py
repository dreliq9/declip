"""Review — Phase 0–3 QA pack for any rendered video.

See docs/workflows/review.md for the recipe.
"""

from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from typing import Optional

from declip.workflows.types import ReviewResult


def run(
    input_path: str,
    output_dir: Optional[str] = None,
    frame_count: int = 16,
    scene_threshold: float = 27.0,
) -> ReviewResult:
    """Generate a QA report pack for a rendered video.

    Args:
        input_path: Video to review.
        output_dir: Report directory. Defaults to <basename>-review/.
        frame_count: Sparse-frame count.
        scene_threshold: Scene-detect ContentDetector threshold.
    """
    from declip import probe as probe_mod
    from declip.analyze import (
        analyze_loudness,
        contact_sheet,
        detect_beats,
        detect_scenes,
        detect_silence,
        extract_frame,
        extract_frames,
    )

    started = time.time()
    in_path = Path(input_path).resolve()
    if not in_path.exists():
        return ReviewResult(success=False, error=f"input not found: {input_path}")

    out_dir = Path(output_dir).resolve() if output_dir else (in_path.parent / f"{in_path.stem}-review").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sparse").mkdir(exist_ok=True)
    (out_dir / "cuts").mkdir(exist_ok=True)

    # Phase 0: probe
    try:
        info = probe_mod.probe(str(in_path))
    except Exception as e:  # noqa: BLE001
        return ReviewResult(success=False, error=f"probe failed: {e}")
    with open(out_dir / "probe.json", "w") as f:
        json.dump(info.to_dict(), f, indent=2)

    # Phase 1: audio analyses (sequential — librosa/ffmpeg subprocesses are CPU-bound;
    # parallelism in Python is bounded by the GIL and FFmpeg saturates one core anyway).
    cuts: list = []
    silence: list = []
    bpm: Optional[float] = None
    try:
        cuts = detect_scenes(str(in_path), threshold=scene_threshold)
        with open(out_dir / "scenes.json", "w") as f:
            json.dump([{"timestamp": c.timestamp, "score": c.score} for c in cuts], f, indent=2)
    except Exception as e:  # noqa: BLE001
        with open(out_dir / "scenes.json", "w") as f:
            json.dump({"error": str(e)}, f, indent=2)

    try:
        silence = detect_silence(str(in_path))
        with open(out_dir / "silence.json", "w") as f:
            json.dump([{"start": s.start, "end": s.end, "duration": s.duration} for s in silence], f, indent=2)
    except Exception as e:  # noqa: BLE001
        with open(out_dir / "silence.json", "w") as f:
            json.dump({"error": str(e)}, f, indent=2)

    try:
        b = detect_beats(str(in_path))
        bpm = float(b.tempo)
        with open(out_dir / "beats.json", "w") as f:
            json.dump({"tempo": b.tempo, "beat_count": b.beat_count, "beat_times": b.beat_times}, f, indent=2)
    except Exception as e:  # noqa: BLE001
        with open(out_dir / "beats.json", "w") as f:
            json.dump({"error": str(e)}, f, indent=2)

    integrated_lufs: Optional[float] = None
    try:
        loud = analyze_loudness(str(in_path))
        integrated_lufs = float(loud.integrated_lufs)
        with open(out_dir / "loudness.txt", "w") as f:
            f.write(
                f"Integrated: {loud.integrated_lufs:.1f} LUFS\n"
                f"Loudness range: {loud.loudness_range:.1f} LU\n"
                f"True peak: {loud.true_peak_dbtp:.1f} dBTP\n"
            )
    except Exception as e:  # noqa: BLE001
        with open(out_dir / "loudness.txt", "w") as f:
            f.write(f"Error: {e}\n")

    # Phase 2: contact sheet + sparse frames
    try:
        contact_sheet(str(in_path), out_dir / "contact_sheet.png", columns=5, rows=4)
    except Exception:  # noqa: BLE001 — analysis aid; non-fatal
        pass

    sparse_frames: list = []
    try:
        sparse_frames = extract_frames(str(in_path), str(out_dir / "sparse"), count=frame_count)
    except Exception:  # noqa: BLE001
        pass

    # Phase 3: targeted frames at cut points
    cut_pairs = 0
    for i, c in enumerate(cuts):
        for offset, label in ((-0.5, "before"), (0.5, "after")):
            ts = max(0.0, float(c.timestamp) + offset)
            try:
                extract_frame(str(in_path), ts, out_dir / "cuts" / f"cut_{i:03d}_{label}.png")
                cut_pairs += 1
            except Exception:  # noqa: BLE001
                continue

    # REVIEW.md
    md_lines = [
        f"# Review: {in_path.name}",
        "",
        "## Probe",
        f"- Duration: {info.duration:.1f}s",
        f"- Resolution: {info.width}x{info.height} @ {info.fps}fps",
        f"- Codec: {info.codec} / {info.audio_codec}",
        f"- Size: {info.file_size / 1024 / 1024:.1f} MB",
        f"- HDR: {info.is_hdr}",
        "",
        "## Audio",
    ]
    if integrated_lufs is not None:
        md_lines.append(f"- Integrated: {integrated_lufs:.1f} LUFS")
    md_lines += [
        "",
        "## Phase 1 results",
        f"- Scene cuts: **{len(cuts)}**",
        f"- Silent segments: **{len(silence)}**",
        f"- Tempo: **{bpm:.1f} BPM**" if bpm else "- Tempo: no tempo detected",
        "",
        "## Phase 2 — visual overview",
        "- `contact_sheet.png` — 5x4 grid",
        f"- `sparse/` — {len(sparse_frames)} evenly-spaced frame extracts",
        "",
        "## Phase 3 — cut-point detail",
        f"- `cuts/` — {cut_pairs} per-cut frames (before/after each scene boundary)",
        "",
        "## Validation tricks",
        "- **Crossfades present?** Lower scene count than clip count = working transitions.",
        "- **Source bumpers?** Compare `cuts/cut_*_before.png` vs `cuts/cut_*_after.png`.",
        "- **Audio fades correct?** Cross-check `silence.json` start/end vs intended fade timing.",
        "",
    ]
    report_path = out_dir / "REVIEW.md"
    report_path.write_text("\n".join(md_lines))

    return ReviewResult(
        success=True,
        output_path=str(out_dir),
        report_path=str(report_path),
        duration_seconds=info.duration,
        scene_cut_count=len(cuts),
        silent_segment_count=len(silence),
        bpm=bpm,
        integrated_lufs=integrated_lufs,
        sparse_frame_count=len(sparse_frames),
        cut_frame_count=cut_pairs,
        elapsed_ms=int((time.time() - started) * 1000),
    )
