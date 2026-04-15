"""Video analysis — frame extraction, scene detection, silence detection,
loudness analysis, beat detection, OCR, audio extraction, contact sheets,
stream enumeration, and audio-to-MIDI.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

import av
import numpy as np


# ---------------------------------------------------------------------------
# Frame extraction
# ---------------------------------------------------------------------------

@dataclass
class ExtractedFrame:
    timestamp: float
    path: str
    width: int
    height: int


def extract_frame(video_path: str | Path, timestamp: float, output_path: str | Path) -> ExtractedFrame:
    """Extract a single frame at a given timestamp."""
    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    container = av.open(str(video_path))
    stream = container.streams.video[0]
    stream.codec_context.skip_frame = "NONKEY"

    # Seek to nearest keyframe before target
    target_pts = int(timestamp / float(stream.time_base))
    container.seek(int(timestamp * av.time_base))

    frame = None
    for f in container.decode(video=0):
        frame = f
        if f.time >= timestamp:
            break

    container.close()

    if frame is None:
        raise ValueError(f"Could not extract frame at {timestamp}s from {video_path}")

    image = frame.to_image()
    image.save(str(output_path))

    return ExtractedFrame(
        timestamp=frame.time or timestamp,
        path=str(output_path),
        width=image.width,
        height=image.height,
    )


def extract_frames(
    video_path: str | Path,
    output_dir: str | Path,
    count: int = 16,
    timestamps: list[float] | None = None,
) -> list[ExtractedFrame]:
    """Extract multiple frames — either evenly spaced or at specific timestamps.

    Args:
        video_path: Path to video file
        output_dir: Directory to save PNG frames
        count: Number of evenly-spaced frames (ignored if timestamps provided)
        timestamps: Specific timestamps in seconds to extract
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    container = av.open(str(video_path))
    duration = float(container.duration / av.time_base) if container.duration else 0.0
    container.close()

    if timestamps is None:
        if duration <= 0:
            raise ValueError(f"Cannot determine duration of {video_path}")
        step = duration / (count + 1)
        timestamps = [step * (i + 1) for i in range(count)]

    results = []
    for i, ts in enumerate(timestamps):
        out_path = output_dir / f"frame_{i:04d}_{ts:.2f}s.png"
        try:
            frame = extract_frame(video_path, ts, out_path)
            results.append(frame)
        except Exception:
            pass  # Skip frames we can't extract (past end, etc.)

    return results


# ---------------------------------------------------------------------------
# Scene detection (frame difference)
# ---------------------------------------------------------------------------

@dataclass
class SceneCut:
    timestamp: float
    score: float  # 0.0-1.0, higher = more different


def detect_scenes(
    video_path: str | Path,
    threshold: float = 27.0,
    sample_interval: float = 0.25,
) -> list[SceneCut]:
    """Detect scene changes using PySceneDetect's ContentDetector.

    Falls back to manual frame-difference analysis if PySceneDetect
    is not installed.

    Args:
        video_path: Path to video file
        threshold: ContentDetector threshold (default 27.0 catches hard cuts;
                   lower values like 20.0 catch dissolves too).
                   For fallback mode, values < 1.0 are interpreted as the
                   legacy 0.0-1.0 scale.
        sample_interval: Seconds between sampled frames (fallback only)
    """
    video_path = Path(video_path)

    try:
        from scenedetect import open_video, SceneManager
        from scenedetect.detectors import ContentDetector, AdaptiveDetector

        video = open_video(str(video_path))
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        scene_manager.detect_scenes(video)
        scene_list = scene_manager.get_scene_list()

        cuts = []
        for i, (start, end) in enumerate(scene_list):
            if i == 0:
                continue  # First scene start is always 0
            ts = start.get_seconds()
            cuts.append(SceneCut(timestamp=round(ts, 3), score=1.0))

        return cuts

    except ImportError:
        # Fallback: manual frame-difference analysis
        # Convert legacy threshold if needed
        if threshold >= 1.0:
            threshold = 0.3  # default for legacy mode

        container = av.open(str(video_path))
        stream = container.streams.video[0]
        stream.codec_context.skip_frame = "DEFAULT"

        prev_array = None
        cuts = []
        last_sampled_time = 0.0

        for frame in container.decode(video=0):
            if frame.time is None:
                continue
            if prev_array is not None:
                if frame.time - last_sampled_time < sample_interval:
                    continue

            img = frame.to_ndarray(format="rgb24")
            h, w = img.shape[:2]
            small = img[::max(1, h//90), ::max(1, w//160)]
            arr = small.astype(float) / 255.0

            if prev_array is not None:
                diff = float(abs(arr - prev_array).mean())
                if diff > threshold:
                    cuts.append(SceneCut(timestamp=round(frame.time, 3), score=round(diff, 4)))

            prev_array = arr
            last_sampled_time = frame.time

        container.close()
        return cuts


# ---------------------------------------------------------------------------
# Silence detection (via FFmpeg)
# ---------------------------------------------------------------------------

@dataclass
class SilentSegment:
    start: float
    end: float
    duration: float


def detect_silence(
    audio_path: str | Path,
    noise_threshold: str = "-30dB",
    min_duration: float = 0.5,
) -> list[SilentSegment]:
    """Detect silent segments in audio/video using FFmpeg's silencedetect filter.

    Args:
        audio_path: Path to audio or video file
        noise_threshold: Noise floor (e.g., "-30dB", "-40dB")
        min_duration: Minimum silence duration in seconds to report
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")

    cmd = [
        "ffmpeg", "-i", str(audio_path),
        "-af", f"silencedetect=noise={noise_threshold}:d={min_duration}",
        "-f", "null", "-",
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True)
    stderr = proc.stderr

    segments = []
    starts = []

    for line in stderr.split("\n"):
        if "silence_start:" in line:
            try:
                val = float(line.split("silence_start:")[1].strip().split()[0])
                starts.append(val)
            except (ValueError, IndexError):
                pass
        elif "silence_end:" in line and starts:
            try:
                parts = line.split("silence_end:")[1].strip().split()
                end = float(parts[0])
                start = starts.pop(0)
                segments.append(SilentSegment(
                    start=round(start, 3),
                    end=round(end, 3),
                    duration=round(end - start, 3),
                ))
            except (ValueError, IndexError):
                pass

    return segments


# ---------------------------------------------------------------------------
# Speech detection (Silero VAD)
# ---------------------------------------------------------------------------

@dataclass
class SpeechSegment:
    start: float
    end: float
    duration: float


def detect_speech(
    audio_path: str | Path,
    min_speech_duration: float = 0.25,
    min_silence_duration: float = 0.3,
    threshold: float = 0.5,
) -> list[SpeechSegment]:
    """Detect speech segments using Silero VAD.

    Much more accurate than inverting silencedetect — detects actual speech
    rather than just absence of silence. Falls back to inverted silencedetect
    if Silero is not installed.

    Args:
        audio_path: Path to audio or video file
        min_speech_duration: Minimum speech segment duration in seconds
        min_silence_duration: Minimum silence between speech segments
        threshold: VAD sensitivity (0.0-1.0, higher = stricter)
    """
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"File not found: {audio_path}")

    try:
        import torch
        from silero_vad import load_silero_vad, get_speech_timestamps

        SAMPLE_RATE = 16000

        # Load audio via PyAV (already a dependency) to avoid torchaudio/torchcodec issues
        container = av.open(str(audio_path))
        audio_stream = container.streams.audio[0]
        resampler = av.audio.resampler.AudioResampler(
            format="s16", layout="mono", rate=SAMPLE_RATE
        )
        frames = []
        for frame in container.decode(audio=0):
            resampled = resampler.resample(frame)
            for r in resampled:
                frames.append(r.to_ndarray().flatten())
        container.close()

        audio_np = np.concatenate(frames).astype(np.float32) / 32768.0
        wav = torch.from_numpy(audio_np)

        model = load_silero_vad()
        timestamps = get_speech_timestamps(
            wav, model,
            sampling_rate=SAMPLE_RATE,
            threshold=threshold,
            min_speech_duration_ms=int(min_speech_duration * 1000),
            min_silence_duration_ms=int(min_silence_duration * 1000),
            return_seconds=True,
        )

        return [
            SpeechSegment(
                start=round(ts["start"], 3),
                end=round(ts["end"], 3),
                duration=round(ts["end"] - ts["start"], 3),
            )
            for ts in timestamps
        ]

    except ImportError:
        # Fallback: invert silence detection to approximate speech
        silent = detect_silence(audio_path, noise_threshold="-30dB", min_duration=0.3)

        container = av.open(str(audio_path))
        duration = float(container.duration / av.time_base) if container.duration else 0.0
        container.close()

        speech = []
        cursor = 0.0
        for seg in sorted(silent, key=lambda s: s.start):
            if seg.start > cursor + min_speech_duration:
                speech.append(SpeechSegment(
                    start=round(cursor, 3),
                    end=round(seg.start, 3),
                    duration=round(seg.start - cursor, 3),
                ))
            cursor = seg.end

        if cursor < duration - min_speech_duration:
            speech.append(SpeechSegment(
                start=round(cursor, 3),
                end=round(duration, 3),
                duration=round(duration - cursor, 3),
            ))

        return speech


# ---------------------------------------------------------------------------
# Review helper — the full self-review pipeline
# ---------------------------------------------------------------------------

@dataclass
class BlackSegment:
    start: float
    end: float
    duration: float


@dataclass
class FrozenSegment:
    start: float
    end: float
    duration: float


def detect_black_frames(video_path: str | Path, min_duration: float = 0.1) -> list[BlackSegment]:
    """Detect black frame segments using FFmpeg's blackdetect filter."""
    if not shutil.which("ffmpeg"):
        return []
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", f"blackdetect=d={min_duration}:pix_th=0.10",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    segments = []
    for line in proc.stderr.split("\n"):
        if "black_start:" in line:
            try:
                parts = line.split("black_start:")[1]
                start = float(parts.split()[0])
                dur = float(parts.split("black_duration:")[1].split()[0])
                segments.append(BlackSegment(start=round(start, 3), end=round(start + dur, 3), duration=round(dur, 3)))
            except (ValueError, IndexError):
                pass
    return segments


def detect_frozen_frames(video_path: str | Path, min_duration: float = 2.0) -> list[FrozenSegment]:
    """Detect frozen/stuck frame segments using FFmpeg's freezedetect filter."""
    if not shutil.which("ffmpeg"):
        return []
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", f"freezedetect=n=0.003:d={min_duration}",
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    segments = []
    starts = []
    for line in proc.stderr.split("\n"):
        if "freeze_start:" in line:
            try:
                val = float(line.split("freeze_start:")[1].strip().split()[0])
                starts.append(val)
            except (ValueError, IndexError):
                pass
        elif "freeze_end:" in line and starts:
            try:
                parts = line.split("freeze_end:")[1].strip().split()
                end = float(parts[0])
                start = starts.pop(0)
                segments.append(FrozenSegment(start=round(start, 3), end=round(end, 3), duration=round(end - start, 3)))
            except (ValueError, IndexError):
                pass
    return segments


@dataclass
class ReviewResult:
    frames: list[ExtractedFrame]
    scene_cuts: list[SceneCut]
    silent_segments: list[SilentSegment]
    black_segments: list[BlackSegment]
    frozen_segments: list[FrozenSegment]
    duration: float
    frame_dir: str
    issues: list[str]

    def to_dict(self) -> dict:
        return {
            "duration": self.duration,
            "frame_dir": self.frame_dir,
            "frame_count": len(self.frames),
            "frames": [asdict(f) for f in self.frames],
            "scene_cuts": [asdict(s) for s in self.scene_cuts],
            "silent_segments": [asdict(s) for s in self.silent_segments],
            "black_segments": [asdict(s) for s in self.black_segments],
            "frozen_segments": [asdict(s) for s in self.frozen_segments],
            "issues": self.issues,
        }

    def summary(self) -> str:
        lines = [
            f"  Duration: {self.duration:.1f}s",
            f"  Frames extracted: {len(self.frames)} → {self.frame_dir}",
            f"  Scene cuts: {len(self.scene_cuts)}",
        ]
        for cut in self.scene_cuts:
            lines.append(f"    {cut.timestamp:.2f}s (score: {cut.score:.3f})")
        lines.append(f"  Silent segments: {len(self.silent_segments)}")
        for seg in self.silent_segments:
            lines.append(f"    {seg.start:.2f}s - {seg.end:.2f}s ({seg.duration:.1f}s)")
        if self.black_segments:
            lines.append(f"  ⚠ Black frames: {len(self.black_segments)}")
            for seg in self.black_segments:
                lines.append(f"    {seg.start:.2f}s - {seg.end:.2f}s ({seg.duration:.1f}s)")
        if self.frozen_segments:
            lines.append(f"  ⚠ Frozen frames: {len(self.frozen_segments)}")
            for seg in self.frozen_segments:
                lines.append(f"    {seg.start:.2f}s - {seg.end:.2f}s ({seg.duration:.1f}s)")
        if self.issues:
            lines.append(f"  Issues: {len(self.issues)}")
            for issue in self.issues:
                lines.append(f"    • {issue}")
        else:
            lines.append("  ✓ No issues detected")
        return "\n".join(lines)


def review(
    video_path: str | Path,
    output_dir: str | Path,
    frame_count: int = 16,
    scene_threshold: float = 27.0,
    extra_frames_at_cuts: bool = True,
) -> ReviewResult:
    """Full self-review pipeline for QA without watching.

    4-phase workflow:
    1. Sparse frames (visual overview)
    2. Scene detection + silence detection + black/freeze detection
    3. Targeted frames at detected cut points
    4. Issue summary (pass/fail heuristics)
    """
    video_path = Path(video_path)
    output_dir = Path(output_dir)

    # Get duration
    container = av.open(str(video_path))
    duration = float(container.duration / av.time_base) if container.duration else 0.0
    container.close()

    # Phase 1: Sparse frames
    frames = extract_frames(video_path, output_dir / "overview", count=frame_count)

    # Phase 2: Detection passes
    scene_cuts = detect_scenes(video_path, threshold=scene_threshold)
    silent_segments = detect_silence(video_path)
    black_segments = detect_black_frames(video_path)
    frozen_segments = detect_frozen_frames(video_path)

    # Phase 3: Targeted frames at cut points (0.5s before and after each cut)
    if extra_frames_at_cuts and scene_cuts:
        cut_timestamps = []
        for cut in scene_cuts:
            before = max(0, cut.timestamp - 0.5)
            after = min(duration, cut.timestamp + 0.5)
            cut_timestamps.extend([before, after])

        cut_frames = extract_frames(
            video_path, output_dir / "cuts",
            timestamps=sorted(set(cut_timestamps)),
        )
        frames.extend(cut_frames)

    # Phase 4: Issue detection
    issues = []
    if black_segments:
        for seg in black_segments:
            if seg.duration > 1.0:
                issues.append(f"Black frame at {seg.start:.1f}s ({seg.duration:.1f}s)")
    if frozen_segments:
        for seg in frozen_segments:
            issues.append(f"Frozen frame at {seg.start:.1f}s ({seg.duration:.1f}s)")
    long_silence = [s for s in silent_segments if s.duration > 5.0]
    if long_silence:
        for seg in long_silence:
            issues.append(f"Long silence at {seg.start:.1f}s ({seg.duration:.1f}s)")

    return ReviewResult(
        frames=frames,
        scene_cuts=scene_cuts,
        silent_segments=silent_segments,
        black_segments=black_segments,
        frozen_segments=frozen_segments,
        duration=duration,
        frame_dir=str(output_dir),
        issues=issues,
    )


# ---------------------------------------------------------------------------
# Loudness analysis (EBU R128 / LUFS)
# ---------------------------------------------------------------------------

@dataclass
class LoudnessResult:
    integrated_lufs: float
    loudness_range: float
    true_peak_dbtp: float
    target_offset: float | None = None  # how far from target (-14 LUFS streaming standard)
    # Platform compliance
    youtube_ok: bool = False   # within 1 dB of -14 LUFS
    podcast_ok: bool = False   # within 1 dB of -16 LUFS
    broadcast_ok: bool = False # within 1 dB of -23 LUFS
    # Time-series (Phase 3) — momentary LUFS at 10Hz, short-term at ~3s windows
    momentary_lufs: list[tuple[float, float]] | None = None  # [(time_s, lufs), ...]
    short_term_lufs: list[tuple[float, float]] | None = None  # [(time_s, lufs), ...]

    def to_dict(self) -> dict:
        return asdict(self)


def analyze_loudness(audio_path: str | Path, time_series: bool = False) -> LoudnessResult:
    """Analyze audio loudness per EBU R128 standard using ebur128 filter.

    Returns integrated LUFS, loudness range, true peak, and platform compliance.
    With time_series=True, also returns momentary (400ms) and short-term (3s)
    LUFS measurements at 10Hz for identifying spikes and dips.

    Args:
        audio_path: Path to audio or video file
        time_series: If True, capture momentary and short-term LUFS over time
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")

    # metadata=1 outputs per-frame momentary and short-term LUFS to stderr
    af = "ebur128=peak=true"
    if time_series:
        af += ":metadata=1"

    cmd = [
        "ffmpeg", "-i", str(audio_path),
        "-af", af,
        "-f", "null", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    stderr = proc.stderr

    # Parse summary block from ebur128 output
    integrated = -70.0
    lra = 0.0
    true_peak = -70.0

    # Time-series collection
    momentary_list: list[tuple[float, float]] = []
    short_term_list: list[tuple[float, float]] = []

    # Track current frame time for metadata parsing
    current_time = 0.0
    in_summary = False

    for line in stderr.split("\n"):
        stripped = line.strip()

        # Detect summary section (comes at the end)
        if "Summary:" in stripped:
            in_summary = True

        if in_summary:
            if "I:" in stripped and "LUFS" in stripped:
                try:
                    integrated = float(stripped.split("I:")[1].split("LUFS")[0].strip())
                except (ValueError, IndexError):
                    pass
            elif "LRA:" in stripped and "LU" in stripped:
                try:
                    lra = float(stripped.split("LRA:")[1].split("LU")[0].strip())
                except (ValueError, IndexError):
                    pass
            elif "Peak:" in stripped and "dB" in stripped:
                try:
                    # ebur128 outputs "True Peak: X.X dBTP" — split on "dB" to handle both dBTP and dBFS
                    true_peak = float(stripped.split("Peak:")[1].split("dB")[0].strip())
                except (ValueError, IndexError):
                    pass
        elif time_series:
            # Parse per-frame metadata lines:
            #   t: 0.4     TARGET:-14  M: -22.5  S: -70.0  I: -22.5  LUFS  LRA: 0.0 LU
            if stripped.startswith("t:") and "M:" in stripped:
                try:
                    t_val = float(stripped.split("t:")[1].split("TARGET")[0].strip())
                    m_val = float(stripped.split("M:")[1].split("S:")[0].strip())
                    s_part = stripped.split("S:")[1].split("I:")[0].strip()
                    s_val = float(s_part)
                    current_time = t_val
                    if m_val > -120:
                        momentary_list.append((round(t_val, 2), round(m_val, 1)))
                    if s_val > -120:
                        short_term_list.append((round(t_val, 2), round(s_val, 1)))
                except (ValueError, IndexError):
                    pass

    integrated = round(integrated, 1)
    lra = round(lra, 1)
    true_peak = round(true_peak, 1)

    return LoudnessResult(
        integrated_lufs=integrated,
        loudness_range=lra,
        true_peak_dbtp=true_peak,
        target_offset=round(-14.0 - integrated, 1) if integrated > -70 else None,
        youtube_ok=abs(integrated - (-14.0)) <= 1.0,
        podcast_ok=abs(integrated - (-16.0)) <= 1.0,
        broadcast_ok=abs(integrated - (-23.0)) <= 1.0,
        momentary_lufs=momentary_list if time_series and momentary_list else None,
        short_term_lufs=short_term_list if time_series and short_term_list else None,
    )


# ---------------------------------------------------------------------------
# Audio extraction
# ---------------------------------------------------------------------------

def extract_audio(
    input_path: str | Path,
    output_path: str | Path | None = None,
    format: str = "wav",
    sample_rate: int | None = None,
) -> str:
    """Extract audio track from a video/audio file.

    Args:
        input_path: Source file
        output_path: Destination (auto-generated if None)
        format: Output format (wav, mp3, flac, aac)
        sample_rate: Optional sample rate override (e.g., 44100, 48000)

    Returns the output file path.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")

    input_path = Path(input_path)
    if output_path is None:
        output_path = input_path.with_suffix(f".{format}")
    output_path = Path(output_path)

    cmd = ["ffmpeg", "-y", "-i", str(input_path), "-vn"]
    if sample_rate:
        cmd += ["-ar", str(sample_rate)]

    codec_map = {"wav": "pcm_s16le", "mp3": "libmp3lame", "flac": "flac", "aac": "aac"}
    if format in codec_map:
        cmd += ["-c:a", codec_map[format]]

    cmd.append(str(output_path))
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Audio extraction failed: {proc.stderr.decode(errors='replace')[-300:]}")

    return str(output_path)


# ---------------------------------------------------------------------------
# Beat detection
# ---------------------------------------------------------------------------

@dataclass
class BeatResult:
    tempo: float          # BPM
    beat_times: list[float]  # timestamps in seconds
    beat_count: int


def detect_beats(audio_path: str | Path) -> BeatResult:
    """Detect beats and estimate tempo using librosa.

    Returns BPM and beat timestamps.
    """
    import librosa
    import numpy as np

    y, sr = librosa.load(str(audio_path), sr=22050, mono=True)
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)

    # tempo may be an array in some librosa versions
    if hasattr(tempo, '__len__'):
        tempo = float(tempo[0])
    else:
        tempo = float(tempo)

    return BeatResult(
        tempo=round(tempo, 1),
        beat_times=[round(float(t), 3) for t in beat_times],
        beat_count=len(beat_times),
    )


# ---------------------------------------------------------------------------
# OCR from frames
# ---------------------------------------------------------------------------

@dataclass
class OCRResult:
    timestamp: float
    text: str
    frame_path: str


def _ocr_image(image_path: str, lang: str = "eng") -> str:
    """Run OCR on an image, using macOS Vision framework if available, else Tesseract."""
    import sys

    # Try macOS Vision framework first (much better accuracy on video frames)
    if sys.platform == "darwin":
        try:
            from ocrmac import ocrmac
            results = ocrmac.OCR(image_path).recognize()
            return "\n".join(r[0] for r in results).strip()
        except ImportError:
            pass
        # Try subprocess to our own Swift OCR or direct Vision API
        try:
            result = subprocess.run(
                ["swift", "-e", f'''
import Foundation; import Vision; import AppKit
let img = NSImage(contentsOfFile: "{image_path}")!
let cgImg = img.cgImage(forProposedRect: nil, context: nil, hints: nil)!
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
try VNImageRequestHandler(cgImage: cgImg, options: [:]).perform([req])
let text = req.results?.compactMap {{ $0.topCandidates(1).first?.string }}.joined(separator: "\\n") ?? ""
print(text)
'''],
                capture_output=True, text=True, timeout=15,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout.strip()
        except Exception:
            pass

    # Fallback: Tesseract
    import pytesseract
    from PIL import Image
    img = Image.open(image_path)
    return pytesseract.image_to_string(img, lang=lang).strip()


def ocr_frame(
    video_path: str | Path,
    timestamp: float,
    output_dir: str | Path | None = None,
    lang: str = "eng",
) -> OCRResult:
    """Extract a frame and run OCR on it.

    Uses macOS Vision framework (0.92 accuracy on video frames) when available,
    falls back to Tesseract.

    Args:
        video_path: Path to video
        timestamp: Time in seconds to extract
        output_dir: Where to save the frame (temp if None)
        lang: Tesseract language code (fallback only)
    """
    video_path = Path(video_path)
    if output_dir is None:
        import tempfile
        output_dir = Path(tempfile.mkdtemp(prefix="declip_ocr_"))
    else:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    frame_path = output_dir / f"ocr_{timestamp:.2f}s.png"
    frame_info = extract_frame(video_path, timestamp, frame_path)

    text = _ocr_image(str(frame_path), lang=lang)

    return OCRResult(
        timestamp=frame_info.timestamp,
        text=text,
        frame_path=str(frame_path),
    )


def ocr_frames(
    video_path: str | Path,
    timestamps: list[float] | None = None,
    count: int = 5,
    output_dir: str | Path | None = None,
    lang: str = "eng",
) -> list[OCRResult]:
    """Run OCR on multiple frames from a video.

    If timestamps not provided, extracts evenly-spaced frames.
    """
    video_path = Path(video_path)

    if timestamps is None:
        container = av.open(str(video_path))
        duration = float(container.duration / av.time_base) if container.duration else 0.0
        container.close()
        if duration <= 0:
            raise ValueError(f"Cannot determine duration of {video_path}")
        step = duration / (count + 1)
        timestamps = [step * (i + 1) for i in range(count)]

    results = []
    for ts in timestamps:
        try:
            result = ocr_frame(video_path, ts, output_dir, lang)
            results.append(result)
        except Exception:
            pass

    return results


# ---------------------------------------------------------------------------
# Audio-to-MIDI
# ---------------------------------------------------------------------------

@dataclass
class MIDINote:
    start: float
    end: float
    pitch: int      # MIDI note number (60 = middle C)
    velocity: int   # 0-127


@dataclass
class MIDIResult:
    notes: list[MIDINote]
    note_count: int
    output_path: str | None
    duration: float


def audio_to_midi(
    audio_path: str | Path,
    output_path: str | Path | None = None,
    min_note_length: float = 0.05,
    confidence_threshold: float = 0.5,
) -> MIDIResult:
    """Transcribe audio to MIDI using librosa pitch detection + midiutil.

    Uses pYIN algorithm for fundamental frequency estimation and onset
    detection for note boundaries. Pure Python — no TensorFlow/CoreML needed.

    Args:
        audio_path: Path to audio/video file
        output_path: Path to save .mid file (optional)
        min_note_length: Minimum note duration in seconds
        confidence_threshold: Pitch confidence threshold (0.0-1.0)
    """
    import librosa
    import numpy as np

    audio_path = Path(audio_path)
    y, sr = librosa.load(str(audio_path), sr=22050, mono=True)

    # Pitch detection via pYIN
    f0, voiced_flag, voiced_probs = librosa.pyin(
        y, sr=sr,
        fmin=librosa.note_to_hz("C2"),
        fmax=librosa.note_to_hz("C7"),
    )

    # Onset detection for note boundaries
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units="frames")
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)

    # Frame times for pitch array
    times = librosa.times_like(f0, sr=sr)

    # Build notes from pitch + onset data
    notes = []

    if len(onset_times) == 0:
        # No onsets detected — treat the whole audio as one note if pitched
        valid = np.where(voiced_flag & (voiced_probs >= confidence_threshold))[0]
        if len(valid) > 0:
            avg_hz = np.nanmean(f0[valid])
            midi_note = int(round(librosa.hz_to_midi(avg_hz)))
            notes.append(MIDINote(
                start=round(float(times[valid[0]]), 3),
                end=round(float(times[valid[-1]]), 3),
                pitch=midi_note,
                velocity=80,
            ))
    else:
        # For each onset, find the dominant pitch until the next onset
        for i, onset_t in enumerate(onset_times):
            # End time is next onset or end of audio
            end_t = onset_times[i + 1] if i + 1 < len(onset_times) else times[-1]

            if end_t - onset_t < min_note_length:
                continue

            # Find frames in this note's time window
            mask = (times >= onset_t) & (times < end_t) & voiced_flag & (voiced_probs >= confidence_threshold)
            pitched_frames = np.where(mask)[0]

            if len(pitched_frames) == 0:
                continue

            # Dominant pitch (median to reject outliers)
            avg_hz = float(np.nanmedian(f0[pitched_frames]))
            if np.isnan(avg_hz) or avg_hz <= 0:
                continue

            midi_note = int(round(librosa.hz_to_midi(avg_hz)))
            midi_note = max(0, min(127, midi_note))

            # Velocity from RMS energy in this window
            start_sample = int(onset_t * sr)
            end_sample = int(end_t * sr)
            segment = y[start_sample:end_sample]
            rms = float(np.sqrt(np.mean(segment ** 2))) if len(segment) > 0 else 0
            velocity = max(20, min(127, int(rms * 1000)))

            notes.append(MIDINote(
                start=round(float(onset_t), 3),
                end=round(float(end_t), 3),
                pitch=midi_note,
                velocity=velocity,
            ))

    duration = max((n.end for n in notes), default=0.0)

    out_path = None
    if output_path is not None:
        from midiutil import MIDIFile

        output_path = Path(output_path)
        midi = MIDIFile(1)
        midi.addTempo(0, 0, 120)

        for note in notes:
            beat_start = note.start * 2  # 120 BPM = 2 beats/sec
            beat_dur = (note.end - note.start) * 2
            midi.addNote(0, 0, note.pitch, beat_start, beat_dur, note.velocity)

        with open(str(output_path), "wb") as f:
            midi.writeFile(f)
        out_path = str(output_path)

    return MIDIResult(
        notes=notes,
        note_count=len(notes),
        output_path=out_path,
        duration=duration,
    )


# ---------------------------------------------------------------------------
# Stream enumeration
# ---------------------------------------------------------------------------

@dataclass
class StreamInfo:
    index: int
    type: str          # "video", "audio", "subtitle", "data"
    codec: str
    language: str | None
    # Video-specific
    width: int | None = None
    height: int | None = None
    fps: float | None = None
    # Audio-specific
    channels: int | None = None
    sample_rate: int | None = None
    channel_layout: str | None = None


def list_streams(file_path: str | Path) -> list[StreamInfo]:
    """Enumerate all streams in a media file with detailed info."""
    container = av.open(str(file_path))
    streams = []

    for s in container.streams:
        info = StreamInfo(
            index=s.index,
            type=s.type,
            codec=s.codec_context.name if s.codec_context else "unknown",
            language=s.metadata.get("language") if s.metadata else None,
        )

        if s.type == "video":
            info.width = s.codec_context.width
            info.height = s.codec_context.height
            info.fps = float(s.average_rate) if s.average_rate else None
        elif s.type == "audio":
            info.channels = s.codec_context.channels
            info.sample_rate = s.codec_context.sample_rate
            layout = s.codec_context.layout
            info.channel_layout = layout.name if layout else None

        streams.append(info)

    container.close()
    return streams


# ---------------------------------------------------------------------------
# Contact sheet
# ---------------------------------------------------------------------------

def contact_sheet(
    video_path: str | Path,
    output_path: str | Path,
    columns: int = 4,
    rows: int = 4,
    thumb_width: int = 480,
    timestamps: list[float] | None = None,
    use_scene_detection: bool = True,
) -> str:
    """Generate a contact sheet (thumbnail grid) from a video.

    By default, uses scene detection to pick representative frames at
    scene boundaries (much more useful than even spacing). Falls back
    to even spacing if scene detection finds too few cuts.

    Args:
        video_path: Source video
        output_path: Where to save the contact sheet image
        columns: Grid columns
        rows: Grid rows
        thumb_width: Width of each thumbnail
        timestamps: Specific timestamps (overrides auto selection)
        use_scene_detection: Use scene cuts for thumbnail placement

    Returns the output path.
    """
    from PIL import Image, ImageDraw, ImageFont

    video_path = Path(video_path)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    count = columns * rows

    container = av.open(str(video_path))
    duration = float(container.duration / av.time_base) if container.duration else 0.0
    vs = container.streams.video[0]
    aspect = vs.codec_context.width / vs.codec_context.height if vs.codec_context.height else 16/9
    container.close()

    thumb_height = int(thumb_width / aspect)

    if timestamps is None:
        if use_scene_detection:
            # Use scene cuts as thumbnail timestamps
            cuts = detect_scenes(video_path)
            if len(cuts) >= count // 2:
                # Enough cuts — sample from them plus midpoints
                cut_times = [0.0] + [c.timestamp for c in cuts]
                # Pick representative frame 0.5s after each cut
                scene_timestamps = [min(t + 0.5, duration) for t in cut_times]
                # If more scenes than slots, evenly sample from scene list
                if len(scene_timestamps) > count:
                    step = len(scene_timestamps) / count
                    scene_timestamps = [scene_timestamps[int(i * step)] for i in range(count)]
                timestamps = scene_timestamps[:count]
            else:
                # Not enough scene cuts — fall back to even spacing
                use_scene_detection = False

        if timestamps is None:
            step = duration / (count + 1)
            timestamps = [step * (i + 1) for i in range(count)]

    # Extract frames
    import tempfile
    with tempfile.TemporaryDirectory(prefix="declip_cs_") as tmpdir:
        frames = extract_frames(video_path, tmpdir, timestamps=timestamps)

        # Build grid with timestamp labels
        label_height = 20
        cell_height = thumb_height + label_height
        sheet = Image.new("RGB", (columns * thumb_width, rows * cell_height), (0, 0, 0))
        draw = ImageDraw.Draw(sheet)

        for i, frame in enumerate(frames[:count]):
            if i >= columns * rows:
                break
            col = i % columns
            row = i // columns
            x = col * thumb_width
            y = row * cell_height

            img = Image.open(frame.path).resize((thumb_width, thumb_height), Image.LANCZOS)
            sheet.paste(img, (x, y))

            # Timestamp label
            ts = frame.timestamp
            m, s = divmod(ts, 60)
            label = f"{int(m):02d}:{s:05.2f}"
            draw.text((x + 4, y + thumb_height + 2), label, fill=(200, 200, 200))

        sheet.save(str(output_path))

    return str(output_path)


# ---------------------------------------------------------------------------
# Speech-to-text (Whisper)
# ---------------------------------------------------------------------------

@dataclass
class Word:
    word: str
    start: float
    end: float
    confidence: float


@dataclass
class Subtitle:
    index: int
    start: float
    end: float
    text: str
    words: list[Word] | None = None


@dataclass
class TranscriptResult:
    language: str
    subtitles: list[Subtitle]
    full_text: str
    srt_path: str | None
    words: list[Word] | None = None  # all words with timing (for caption tools)


def transcribe(
    audio_path: str | Path,
    output_srt: str | Path | None = None,
    model_size: str = "base",
    language: str | None = None,
    word_timestamps: bool = False,
) -> TranscriptResult:
    """Transcribe speech to text using faster-whisper.

    Args:
        audio_path: Path to audio or video file
        output_srt: Path to save .srt subtitle file (optional)
        model_size: Whisper model size (tiny, base, small, medium, large-v3)
        language: Language code (e.g., "en") or None for auto-detect
        word_timestamps: Enable per-word timing (needed for auto-captions/karaoke)
    """
    from faster_whisper import WhisperModel

    model = WhisperModel(model_size, compute_type="int8")
    segments, info = model.transcribe(
        str(audio_path),
        language=language,
        word_timestamps=word_timestamps,
        vad_filter=True,
    )

    subtitles = []
    all_words = []
    for i, seg in enumerate(segments):
        seg_words = None
        if word_timestamps and seg.words:
            seg_words = [
                Word(
                    word=w.word.strip(),
                    start=round(w.start, 3),
                    end=round(w.end, 3),
                    confidence=round(w.probability, 3),
                )
                for w in seg.words
            ]
            all_words.extend(seg_words)

        subtitles.append(Subtitle(
            index=i + 1,
            start=round(seg.start, 3),
            end=round(seg.end, 3),
            text=seg.text.strip(),
            words=seg_words,
        ))

    full_text = " ".join(s.text for s in subtitles)

    srt_path = None
    if output_srt is not None:
        srt_path = str(output_srt)
        _write_srt(subtitles, srt_path)

    return TranscriptResult(
        language=info.language,
        subtitles=subtitles,
        full_text=full_text,
        srt_path=srt_path,
        words=all_words if word_timestamps else None,
    )


def _write_srt(subtitles: list[Subtitle], path: str):
    """Write subtitles to SRT format."""
    def _fmt_time(seconds: float) -> str:
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    lines = []
    for sub in subtitles:
        lines.append(str(sub.index))
        lines.append(f"{_fmt_time(sub.start)} --> {_fmt_time(sub.end)}")
        lines.append(sub.text)
        lines.append("")

    Path(path).write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Chapter markers
# ---------------------------------------------------------------------------

@dataclass
class Chapter:
    index: int
    start: float
    end: float
    title: str


def generate_chapters(
    video_path: str | Path,
    scene_threshold: float = 0.3,
    output_path: str | Path | None = None,
) -> list[Chapter]:
    """Generate chapter markers from scene cuts.

    Optionally writes FFmpeg-compatible chapters metadata file.
    """
    video_path = Path(video_path)
    container = av.open(str(video_path))
    duration = float(container.duration / av.time_base) if container.duration else 0.0
    container.close()

    cuts = detect_scenes(video_path, threshold=scene_threshold)

    chapters = []
    timestamps = [0.0] + [c.timestamp for c in cuts] + [duration]

    for i in range(len(timestamps) - 1):
        chapters.append(Chapter(
            index=i + 1,
            start=round(timestamps[i], 3),
            end=round(timestamps[i + 1], 3),
            title=f"Chapter {i + 1}",
        ))

    if output_path is not None:
        _write_chapters_metadata(chapters, str(output_path))

    return chapters


def _write_chapters_metadata(chapters: list[Chapter], path: str):
    """Write FFmpeg-compatible chapters metadata file."""
    lines = [";FFMETADATA1"]
    for ch in chapters:
        start_ms = int(ch.start * 1000)
        end_ms = int(ch.end * 1000)
        lines.append(f"\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={start_ms}\nEND={end_ms}\ntitle={ch.title}")
    Path(path).write_text("\n".join(lines))


# ---------------------------------------------------------------------------
# Waveform visualization
# ---------------------------------------------------------------------------

def waveform(
    audio_path: str | Path,
    output_path: str | Path,
    width: int = 1920,
    height: int = 200,
    color: str = "#00FF88",
) -> str:
    """Generate a waveform visualization as PNG."""
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg not found in PATH")

    output_path = str(output_path)
    cmd = [
        "ffmpeg", "-y", "-i", str(audio_path),
        "-filter_complex",
        f"showwavespic=s={width}x{height}:colors={color}",
        "-frames:v", "1",
        output_path,
    ]

    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Waveform failed: {proc.stderr.decode(errors='replace')[-300:]}")

    return output_path


# ---------------------------------------------------------------------------
# Audio ducking
# ---------------------------------------------------------------------------

def generate_duck_filter(
    video_path: str | Path,
    music_volume: float = 0.3,
    normal_volume: float = 1.0,
    attack: float = 0.5,
    release: float = 1.0,
) -> str:
    """Generate an FFmpeg volume filter string for audio ducking.

    Uses Silero VAD to detect speech segments (falls back to inverted
    silencedetect if Silero is unavailable). Returns an FFmpeg -af filter
    that lowers music volume during speech.

    Returns an FFmpeg -af filter string for the music track.
    """
    speech = detect_speech(video_path)

    from declip.probe import probe
    info = probe(video_path)
    duration = info.duration

    if not speech:
        return f"volume={normal_volume}"

    # Build volume keyframes from speech segments
    keyframes = []
    for seg in speech:
        # Ramp down before speech starts
        ramp_start = max(0, seg.start - attack)
        keyframes.append((ramp_start, normal_volume))
        keyframes.append((seg.start, music_volume))
        # Hold ducked during speech
        keyframes.append((seg.end, music_volume))
        # Ramp up after speech ends
        ramp_end = min(duration, seg.end + release)
        keyframes.append((ramp_end, normal_volume))

    if not keyframes:
        return f"volume={normal_volume}"

    # Build volume filter with enable expressions for each speech segment
    parts = []
    for seg in speech:
        duck_start = max(0, seg.start - attack)
        duck_end = min(duration, seg.end + release)
        parts.append(
            f"volume=enable='between(t,{duck_start:.3f},{duck_end:.3f})':volume={music_volume}"
        )

    return ",".join(parts) if parts else f"volume={normal_volume}"


# ---------------------------------------------------------------------------
# FCPXML export
# ---------------------------------------------------------------------------

def export_fcpxml(
    project_path: str | Path,
    output_path: str | Path,
) -> str:
    """Export a declip project to FCPXML format for Final Cut Pro."""
    from declip.schema import Project

    project = Project.load(project_path)
    fps = project.settings.fps
    w, h = project.settings.resolution
    project_dir = Path(project_path).parent

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE fcpxml>',
        '<fcpxml version="1.10">',
        '  <resources>',
    ]

    asset_map = {}
    asset_idx = 0
    for track in project.timeline.tracks:
        for clip in track.clips:
            if clip.asset not in asset_map:
                asset_id = f"r{asset_idx + 1}"
                asset_path = clip.asset
                if not Path(asset_path).is_absolute():
                    asset_path = str(project_dir / asset_path)
                lines.append(f'    <asset id="{asset_id}" src="file://{asset_path}" '
                             f'hasVideo="1" hasAudio="1"/>')
                asset_map[clip.asset] = asset_id
                asset_idx += 1

    fmt_id = "r0"
    lines.append(f'    <format id="{fmt_id}" frameDuration="1/{fps}s" '
                 f'width="{w}" height="{h}"/>')
    lines.append('  </resources>')
    lines.append('  <library>')
    lines.append('    <event name="Declip Export">')
    lines.append('      <project name="declip_project">')

    max_end = 0.0
    for track in project.timeline.tracks:
        for clip in track.clips:
            dur = clip.duration or (clip.trim_out - clip.trim_in if clip.trim_out else 10.0)
            max_end = max(max_end, clip.start + dur)

    total_frames = int(max_end * fps)
    lines.append(f'        <sequence format="{fmt_id}" '
                 f'duration="{total_frames}/{fps}s">')
    lines.append('          <spine>')

    for track in project.timeline.tracks:
        for clip in sorted(track.clips, key=lambda c: c.start):
            asset_id = asset_map[clip.asset]
            dur = clip.duration or (clip.trim_out - clip.trim_in if clip.trim_out else 10.0)
            dur_frames = int(dur * fps)
            start_frames = int(clip.start * fps)
            trim_in_frames = int(clip.trim_in * fps)
            lines.append(f'            <asset-clip ref="{asset_id}" '
                         f'offset="{start_frames}/{fps}s" '
                         f'duration="{dur_frames}/{fps}s" '
                         f'start="{trim_in_frames}/{fps}s"/>')

    lines.append('          </spine>')
    lines.append('        </sequence>')
    lines.append('      </project>')
    lines.append('    </event>')
    lines.append('  </library>')
    lines.append('</fcpxml>')

    output_path = Path(output_path)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    return str(output_path)
