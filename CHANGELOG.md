# Declip Changelog

---

## v0.8.0 — 2026-04-16 — "Structured Quick Tools"

Adds Pydantic structured outputs to the four `quick_tools` MCP tools — `declip_probe`, `declip_trim`, `declip_concat`, `declip_thumbnail`. FastMCP now serializes each result into both `content` (the same human-readable text via `__str__`) AND `structuredContent` (typed JSON). Agents can read `result.duration_seconds`, `result.file_size_bytes`, etc. directly without parsing the formatted string.

### What changed

- **New `src/declip/mcp/types.py`** — `ProbeResult`, `TrimResult`, `ConcatResult`, `ThumbnailResult`, plus a shared `FileResult` base.
- **`quick_tools.py`** — all 4 tools return Pydantic models. `__str__` preserves the existing text output verbatim so agents that grep the text don't break.
- **Validated inputs:** `declip_trim.trim_in` `ge=0`, `trim_out` `gt=0`. `declip_concat.files` `min_length=2`. `declip_thumbnail.timestamp` `ge=0`.
- **Failure semantics:** the old `"Error: …"` prefix in the text is preserved, but failures now also carry `success=False` + `error=…` in `structuredContent`.

### Migration

Existing agents that read the text output keep working — `__str__` reproduces the previous strings byte-for-byte. New agents can read structured fields:

- `result.duration_seconds`, `result.fps`, `result.video_codec` from `declip_probe`
- `result.output_path`, `result.file_size_bytes`, `result.smart`, `result.re_encoded_head_seconds` from `declip_trim`
- `result.file_count`, `result.method` (`"stream-copy"` or `"re-encoded"`) from `declip_concat`
- `result.timestamp_seconds`, `result.width`, `result.height` from `declip_thumbnail`

### Out of scope (follow-up)

`analysis_tools`, `media_tools`, `advanced_tools`, `generate_tools`, `edit_tools`, `pipeline_tools`, `project_tools` still return strings. Same envelope pattern applies — convert per-module in follow-up PRs.

### Dependency updates

- `mcp>=1.10` (was `>=1.2.0` — way old)
- `pydantic>=2.7` (was `>=2.0`)

---

## v0.7.0 — 2026-03-29 — "Less Is More"

Phase 7: Silero VAD speech detection + tool consolidation. Better AI decision-making with fewer tools.

### New: Silero VAD Speech Detection

`detect_speech()` in analyze.py uses Silero VAD neural network to find actual human speech (87.7% TPR vs FFmpeg silencedetect which only finds absence of energy). Falls back to inverted silencedetect if Silero unavailable. Audio loaded via PyAV to avoid torchaudio/torchcodec dependency issues.

Integrated into:
- `declip_detect_audio` (mode="speech") — MCP tool
- `generate_duck_filter()` — now uses speech segments directly for more accurate ducking

### Tool Consolidation: 56 → 51

| Before | After | Change |
|--------|-------|--------|
| `declip_color_adjust` + `declip_color_grade` | `declip_color` | Merged — one tool handles brightness/contrast/saturation AND colorbalance/temperature/auto-levels |
| `declip_detect_silence` + `declip_detect_speech` | `declip_detect_audio` | Merged — `mode="speech"` (Silero VAD) or `mode="silence"` (FFmpeg) |
| `declip_loudness` + `declip_loudnorm` | `declip_loudness` | Merged — optional `normalize_to` param triggers two-pass normalization |
| `declip_estimate_cost` + `declip_models` | `declip_models` | Merged — optional `estimate_model` param for cost estimates |
| `declip_duck_filter` | removed | Replaced by `declip_sidechain` which does actual ducking, not just filter generation |

### Dependencies Added

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| `silero-vad` | 6.2.1 | MIT | Speech detection (Silero VAD) |
| `torch` | 2.11.0 | BSD | Required by silero-vad |

---

## v0.6.0 — 2026-03-29 — "DRY"

Phase 6: eliminate CLI/MCP code duplication. Single source of truth for all shared operations.

### New Module: `ops.py`

Shared implementations for 7 operations, called by both MCP tools and CLI commands:

| Operation | What it does |
|-----------|-------------|
| `ops.speed` | Playback speed with atempo chain + optional minterpolate |
| `ops.stabilize` | Two-pass vidstab with smoothing/zoom/tripod |
| `ops.reverse` | Direct or chunked reverse with temp file cleanup |
| `ops.color_grade` | colorbalance + colortemperature + normalize |
| `ops.sidechain` | sidechaincompress ducking |
| `ops.denoise` | afftdn / anlmdn noise reduction |
| `ops.loudnorm` | Two-pass loudnorm with platform target resolution |

All ops return `(success: bool, message: str)`. MCP tools and CLI commands are now thin wrappers.

### TransitionType Enum Expanded

Schema `TransitionType` expanded from 7 → 50 values to match all FFmpeg xfade types. Backend `xfade_map` updated. `can_handle()` now returns True for all transition types (no more MLT fallback for transitions).

### Tests

18 new tests in `test_ops.py`: output path helper, loudnorm target resolution (named, case-insensitive, custom number, invalid), file-not-found for all 7 ops, input validation (speed zero/negative, color_grade no params).

**Total: 29 tests** (11 schema + 18 ops).

### Impact

Before: sidechain bug existed in both `edit_tools.py` and `cli.py` independently. After: single implementation in `ops.py`, impossible to diverge.

---

## v0.5.0 — 2026-03-29 — "Full Stack"

Phase 5: CLI parity, test coverage, and consistency fixes. Every tool now reachable from both CLI and MCP.

### New CLI Commands

8 new commands bridging the MCP-only gap:

| Command | What it does |
|---------|-------------|
| `declip loudnorm` | Two-pass loudness normalization — `declip loudnorm video.mp4 --target youtube` |
| `declip denoise` | Audio noise reduction — `declip denoise video.mp4 --strength heavy --method fft` |
| `declip sidechain` | Auto-duck music under speech — `declip sidechain video.mp4 music.mp3` |
| `declip speed` | Speed change with optional interpolation — `declip speed video.mp4 --speed 0.5 --interpolate` |
| `declip stabilize` | Two-pass stabilization — `declip stabilize video.mp4 --smoothing 15 --tripod` |
| `declip reverse` | Reverse with auto-chunking — `declip reverse video.mp4` |
| `declip color-grade` | Advanced grading — `declip color-grade video.mp4 --temperature 0.3 --auto-levels` |

### Tests Added

6 new tests for auto-sequencing (Phase 4 feature):
- `test_auto_start_first_clip_defaults_to_zero`
- `test_auto_start_sequential`
- `test_auto_start_with_transition_overlap`
- `test_auto_start_with_trim`
- `test_auto_start_mixed_with_manual`
- `test_auto_start_invalid_string_rejected`

All 11 tests pass.

### Bug Fixes

| Fix | Details |
|-----|---------|
| Pydantic `start: "auto"` field type | `from __future__ import annotations` broke `Union[float, str]` — fixed with `field_validator` + `Any` annotation |
| Pipeline loudnorm JSON parsing | Replaced fragile regex extraction with `rfind` approach matching `declip_loudnorm` |

### Example Projects

| File | Description |
|------|-------------|
| `examples/auto_sequence.json` | Three clips using `"start": "auto"` with a dissolve transition — demonstrates timestamp-free editing |

---

## v0.4.0 — 2026-03-29 — "Power Tools"

Phase 4: advanced capabilities. 4 new tools (55 total), 2 major upgrades, 1 schema-level feature.

### New Tools

| Tool | File | What it does |
|------|------|-------------|
| `declip_sidechain` | `mcp/edit_tools.py` | Auto-duck music under speech using FFmpeg `sidechaincompress`. Takes video (speech source) + music file, applies sidechain compression so music drops when speech is detected. Configurable threshold, ratio, attack, release. Far more natural than volume-keyframe approach. |
| `declip_denoise` | `mcp/edit_tools.py` | Audio noise reduction via FFmpeg `afftdn` (FFT-based, stationary noise) or `anlmdn` (non-local means, varying noise). Three strength presets (light/medium/heavy). Good pre-processing before voiceover or transcription. |
| `declip_loudnorm` | `mcp/edit_tools.py` | Two-pass loudness normalization to platform targets. Pass 1 measures, pass 2 applies exact correction with `linear=true`. Targets: youtube (-14 LUFS), tiktok/reels (-11), podcast (-16), broadcast (-23), or custom. Extracted from platform_export as a standalone tool. |
| `declip_color_grade` | `mcp/edit_tools.py` | Advanced color grading: per-range color balance (shadows/midtones/highlights RGB), white balance via `colortemperature` (warm↔cool), and auto-levels via `normalize`. Complements existing `declip_color_adjust` (brightness/contrast/saturation). |

### Tool Upgrades

| Upgrade | File | Details |
|---------|------|---------|
| **Speed: optical-flow slow-mo** | `mcp/edit_tools.py` `declip_speed` | New `interpolate` param. When enabled with speed < 1.0, uses FFmpeg `minterpolate=mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1` for optical-flow frame interpolation. Dramatically smoother slow-mo vs. frame duplication. Very slow to encode — offered as a quality option. |
| **Auto-sequencing: `start: "auto"`** | `schema.py`, `cli.py`, `mcp/project_tools.py` | Clips can now use `"start": "auto"` instead of manual timestamp math. Auto-placed after the previous clip's end, minus transition overlap. First clip on a track defaults to 0. Probes assets for duration when needed. Eliminates the #1 pain point of JSON-based video editing. |

### Schema Changes

| Change | Details |
|--------|---------|
| `Clip.start` now accepts `float` or `"auto"` | Validated by model_validator. Resolved to float by `Project.resolve_auto_starts()` before rendering. |
| `Project.resolve_auto_starts(project_dir)` | New method. Called automatically by CLI `render` and MCP `declip_render` before backend dispatch. |

### Tool Count

51 → **55** total tools (4 new: sidechain, denoise, loudnorm, color_grade)

### Phase 4 Remaining (deferred)

| Item | Status | Notes |
|------|--------|-------|
| Shot-list format → project compiler | Deferred | Already works at MCP level via `declip_storyboard`. Schema-level support is nice-to-have. |
| Spotify basic-pitch for polyphonic MIDI | Deferred | Requires new dependency, separate install step |
| Silero VAD for speech detection | Deferred | Requires torch dependency |
| Smart reframe with face detection | Deferred | High effort, needs YOLOv8 |
| WhisperX for precision word alignment | Deferred | wav2vec2 dependency |
| Waveform with markers | Deferred | Low priority |
| gifski backend | Deferred | Requires Rust binary |

---

## v0.3.0 — 2026-03-29 — "Polish Pass"

Phase 3: polish existing tools. 9 upgrades across 5 files — no new tools, but every upgraded tool is meaningfully more capable.

### Tool Upgrades

| Upgrade | File | Details |
|---------|------|---------|
| **Transitions: 7 → 50 xfade types** | `mcp/edit_tools.py` `declip_transition` | Added all FFmpeg xfade types: circleopen/close, circlecrop, rectcrop, slideleft/right/up/down, smoothleft/right/up/down, diagtl/tr/bl/br, hlslice/hrslice/vuslice/vdslice, radial, zoomin, distance, pixelize, squeezeh/v, hlwind/hrwind/vuwind/vdwind, coverleft/right/up/down, revealleft/right/up/down, fadegrays, horzopen/close, vertopen/close. Added validation — unknown types now return a helpful error. |
| **Text overlay: shadow + outline** | `mcp/edit_tools.py` `declip_text_overlay` | New params: `shadow_color`, `shadow_x`, `shadow_y` for drop shadow; `outline_width`, `outline_color` for text border. Uses FFmpeg drawtext `shadowcolor`/`shadowx`/`shadowy` and `borderw`/`bordercolor`. |
| **Stabilization: full param exposure** | `mcp/edit_tools.py` `declip_stabilize` | New params: `smoothing` (frame window, was hardcoded 10), `zoom` (% to hide black borders), `tripod` (lock to single reference frame). |
| **Subtitle burn: auto-detect ASS vs SRT** | `mcp/edit_tools.py` `declip_subtitle_burn` | Renamed param `srt_path` → `subtitle_path`. Auto-detects .ass/.ssa → uses `ass=` filter (preserves native styling); .srt → uses `subtitles=` with `force_style`. New params: `outline_width`, `shadow_offset`, `margin_v`, `alignment`. |
| **Probe: extended media info** | `probe.py` `AssetInfo`, `mcp/quick_tools.py` `declip_probe` | 8 new fields: `pixel_format`, `bit_depth`, `color_space`, `color_primaries`, `color_transfer`, `video_bitrate`, `audio_bitrate`, `is_hdr`. HDR auto-detected from PQ (smpte2084) or HLG (arib-std-b67) transfer characteristics. Probe output now shows bitrate, pixel format, bit depth, HDR flag, and color properties. |
| **Loudness: time-series LUFS** | `analyze.py` `analyze_loudness`, `mcp/media_tools.py` `declip_loudness` | New `time_series` param. When enabled, uses `ebur128=metadata=1` to capture momentary (400ms, 10Hz) and short-term (3s) LUFS over time. Returns loudest/quietest moments, flags samples above -8 LUFS, shows sampled short-term curve. Also added platform compliance display (YouTube/Podcast/Broadcast). |
| **Smart trim: keyframe-aware hybrid cut** | `mcp/quick_tools.py` `declip_trim` | New `smart` param. Finds nearest keyframe after cut point via ffprobe, re-encodes only the head frames (cut point → keyframe), stream-copies the rest. Frame-accurate cuts with minimal re-encoding. Graceful fallback to full re-encode if no nearby keyframe found. |
| **Chunked reverse for long videos** | `mcp/edit_tools.py` `declip_reverse` | Videos >30s now automatically split into chunks (default 10s), reverse each chunk, concat in reverse order. Prevents OOM on long videos (~100GB RAM for 10min 1080p60 with old approach). Configurable `chunk_seconds` param. |
| **Split screen: PIP + borders + audio** | `mcp/edit_tools.py` `declip_split_screen` | New `pip` layout: picture-in-picture with configurable `pip_scale` and `pip_position`. New `border` and `border_color` params for panel dividers. New `audio_from` param: pick which input's audio to use (0-based index), or -1 to mix all tracks. |

### Files Changed

| File | Lines | What changed |
|------|-------|-------------|
| `probe.py` | 73 → 120 | Extended AssetInfo dataclass with 8 new fields, HDR detection logic |
| `analyze.py` | 1340 → ~1420 | Loudness time-series parsing, new `time_series` parameter |
| `mcp/edit_tools.py` | 825 → ~1050 | 5 tool upgrades (transitions, text, stabilize, subtitle, reverse, split screen) |
| `mcp/quick_tools.py` | 193 → ~310 | Smart trim, expanded probe display |
| `mcp/media_tools.py` | 209 → ~250 | Loudness tool: time-series output, compliance display |

---

## v0.2.0 — 2026-03-29 — "Master Builder"

32 → 51 tools. Major audit, bug fixes, analysis upgrades, and full production pipeline.

### Bug Fixes

| Fix | File | Details |
|-----|------|---------|
| Watermark filter was `pass` — never implemented | `backends/ffmpeg.py:114-118` | Implemented overlay via filter_complex in `_single_clip_cmd`. Scales watermark relative to video width, positions from normalized coords, applies opacity via colorchannelmixer. |
| Project renderer didn't crossfade audio on transitions | `backends/ffmpeg.py:343-357` | Replaced audio `concat` chain in `_xfade_cmd` with `acrossfade` matching each video transition duration. MCP tool already did this; backend now matches. |
| `amix` volume pumping | `mcp/edit_tools.py` `declip_audio_mix` | Added `normalize=0` to amix filter. Default amix normalizes output causing volume to pump when tracks overlap. |
| Trim audio sync drift on non-keyframe cuts | `mcp/quick_tools.py` `declip_trim` | Added `-avoid_negative_ts make_zero` to FFmpeg trim command. Fixes A/V sync issues when cut point isn't on a keyframe. |

### Analysis Upgrades (Phase 1)

| Upgrade | File | Before → After | Attribution |
|---------|------|----------------|-------------|
| Scene detection → PySceneDetect | `analyze.py` `detect_scenes()` | Manual frame-diff (MAD on 160x90 downsampled frames) → PySceneDetect ContentDetector with AdaptiveDetector support. Graceful fallback to frame-diff if PySceneDetect not installed. | [PySceneDetect](https://github.com/Breakthrough/PySceneDetect) — BSD 3-Clause. pip install `scenedetect[opencv]`. |
| OCR → macOS Vision framework | `analyze.py` `_ocr_image()`, `ocr_frame()` | Tesseract via pytesseract (0.38 accuracy on video frames) → macOS Vision `VNRecognizeTextRequest` via inline Swift subprocess (0.92 accuracy). Falls back to Tesseract cross-platform. | Apple Vision framework — ships with macOS. No external dependency on Mac. Swift subprocess approach is original. |
| Contact sheet: scene-based sampling | `analyze.py` `contact_sheet()` | Even spacing only → Uses `detect_scenes()` output to place thumbnails at scene boundaries. Timestamp labels on each frame via PIL ImageDraw. Falls back to even spacing if too few scene cuts. | Original implementation. |
| Loudness → ebur128 | `analyze.py` `LoudnessResult`, `analyze_loudness()` | `loudnorm` filter (designed for normalization, not measurement) → `ebur128` filter (proper EBU R128 measurement). Added multi-platform compliance flags: `youtube_ok` (-14 LUFS), `podcast_ok` (-16 LUFS), `broadcast_ok` (-23 LUFS). | FFmpeg ebur128 filter — part of FFmpeg. |
| Review pipeline: blackdetect + freezedetect | `analyze.py` `ReviewResult`, `review()`, `detect_black_frames()`, `detect_frozen_frames()` | 3-phase (sparse frames + scene detect + silence detect) → 4-phase adding black frame detection and frozen frame detection. Added issue summary with pass/fail heuristics. | FFmpeg `blackdetect` and `freezedetect` filters — part of FFmpeg. |
| Transcription: word-level timestamps | `analyze.py` `Word`, `Subtitle.words`, `TranscriptResult.words`, `transcribe()` | Segment-level timing only → Added `word_timestamps=True` parameter. Returns per-word timing with confidence scores via faster-whisper's CTC/attention alignment. Added `vad_filter=True` to reduce hallucinations. | [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — MIT License. Already a dependency. Word timestamps use Whisper's cross-attention weights. |
| Smart concat | `mcp/quick_tools.py` `declip_concat()` | Always re-encodes via filter_complex → Probes all inputs; if codec/resolution/fps match, uses concat demuxer with `-c copy` (instant, no re-encode). Falls back to filter concat for mixed formats. | Original implementation using FFmpeg concat demuxer. |

### New Edit Tools (added earlier this session)

15 tools in `mcp/edit_tools.py` — all FFmpeg-based, zero API cost:

| Tool | What it does |
|------|-------------|
| `declip_text_overlay` | Burn text onto video. Position presets, font lookup, background box, timed appearance. |
| `declip_image_overlay` | Watermark/logo/PIP. Scales relative to main video width, alpha transparency. |
| `declip_transition` | xfade between two clips. dissolve, wipe, fade variants. Audio crossfade with fallback. |
| `declip_speed` | Playback speed 0.25x-100x. Chained atempo for extreme values. Audio fallback. |
| `declip_color_adjust` | Brightness, contrast, saturation, greyscale via FFmpeg eq/hue filters. |
| `declip_crop_resize` | Crop, resize, aspect ratio conversion with letterbox padding. Even-dimension enforcement. |
| `declip_subtitle_burn` | Burn SRT/ASS subtitles. ASS color format mapping. Auto-detect subtitle format. |
| `declip_reverse` | Play backwards. Memory warning for >30s clips. |
| `declip_gif` | Two-pass palette GIF export. Lanczos scaling. Tempfile cleanup. |
| `declip_split_screen` | Tile 2-4 videos. Horizontal, vertical, 2x2 grid. Forces common cell size. |
| `declip_freeze_frame` | Hold a single frame. Probes source FPS instead of hardcoding 30. |
| `declip_stabilize` | vidstab two-pass with unsharp. Tempfile for transform data (no collision). |
| `declip_audio_mix` | Mix audio tracks. Delay, volume, replace mode. normalize=0 on amix. |
| `declip_loop` | Loop N times via concat demuxer. Tempfile cleanup in finally block. |
| `declip_fade` | Fade in/out to black or white. Synced audio fade. Probes duration. |

All original implementations using FFmpeg CLI. No external code copied.

### New Pipeline Tools (Phase 2)

5 tools in `mcp/pipeline_tools.py`:

| Tool | What it does | Attribution |
|------|-------------|-------------|
| `declip_auto_caption` | Transcribe → word-level ASS with `\kf` karaoke tags → burn in. 4 style presets (bold, karaoke, minimal, news). | Original ASS generator. Transcription via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (MIT). ASS karaoke tag format per [Aegisub spec](https://aegisub.org/docs/latest/ass_tags/). |
| `declip_tts` | Generate neural voiceover with word-level timing via edge-tts. Saves word timing JSON sidecar. | [edge-tts](https://github.com/rany2/edge-tts) — GPL-3.0. Uses Microsoft Edge's free TTS WebSocket API. No API key required. |
| `declip_tts_voices` | List available TTS voices filtered by language. | edge-tts (same as above). |
| `declip_platform_export` | One-shot multi-platform export. 9 platform presets with per-platform loudness normalization (two-pass loudnorm) and 3 reframe strategies (center_crop, blur_bg, letterbox). BT.709 colorspace tagging. | Original implementation. Platform specs from [Sprout Social](https://sproutsocial.com/insights/social-media-video-specs-guide/), [Kapwing](https://www.kapwing.com/resources/social-media-video-aspect-ratios-and-sizes-the-2025-guide/), YouTube/TikTok official docs. Blur background technique from [FFmpeg community gist](https://gist.github.com/ArneAnka/a1348b13fc291f72f862d92f35380428). |
| `declip_storyboard` | Shot list JSON → complete video. Auto-sequences clips, generates TTS narration (determines shot duration from audio length), adds background music with ducking, applies transitions, optional auto-captions post-render. | Original orchestration. Uses edge-tts, faster-whisper, and FFmpeg under the hood. |

### Dependencies Added

| Package | Version | License | Purpose |
|---------|---------|---------|---------|
| `scenedetect[opencv]` | 0.6.7.1 | BSD 3-Clause | Scene detection (ContentDetector) |
| `edge-tts` | 7.2.8 | GPL-3.0 | Text-to-speech voiceover |
| `opencv-python` | 4.13.0.92 | Apache 2.0 | Required by PySceneDetect |

### Tool Count

| Category | Before | After |
|----------|--------|-------|
| Project tools | 5 | 5 |
| Quick tools | 4 | 4 |
| Analysis tools | 4 | 4 |
| Media tools | 7 | 7 |
| Advanced tools | 6 | 6 |
| Generate tools | 6 | 6 |
| Edit tools | 0 | **15** |
| Pipeline tools | 0 | **5** |
| **Total** | **32** | **51** |

---

## Future Improvements

### Phase 3 — Polish Existing Tools (COMPLETED in v0.3.0)

| # | Improvement | Status |
|---|------------|--------|
| 1 | Smart trim (keyframe-aware hybrid cut) | ✓ v0.3.0 |
| 2 | Expand transitions to all 50 xfade types | ✓ v0.3.0 |
| 3 | Loudness time-series (momentary/short-term LUFS) | ✓ v0.3.0 |
| 4 | Chunked reverse for long videos | ✓ v0.3.0 |
| 5 | Stabilization parameter exposure | ✓ v0.3.0 |
| 6 | gifski backend for better GIF quality | Deferred to Phase 4 |
| 7 | Split screen: PIP layout + borders + audio selection | ✓ v0.3.0 |
| 8 | Subtitle burn: auto-detect ASS vs SRT, expose styling | ✓ v0.3.0 |
| 9 | Text overlay: shadow + outline params | ✓ v0.3.0 |
| 10 | Probe: HDR/bit-depth/pixel-format/bitrate | ✓ v0.3.0 |

### Phase 4 — Advanced Capabilities (partially completed in v0.4.0)

| # | Improvement | Status |
|---|------------|--------|
| 1 | Auto-sequencing (`start: "auto"` in schema) | ✓ v0.4.0 |
| 2 | Shot-list format → project compiler | Deferred — works at MCP level via storyboard |
| 3 | minterpolate smooth slow-mo | ✓ v0.4.0 |
| 4 | colorbalance / curves / colortemperature | ✓ v0.4.0 |
| 5 | Spotify basic-pitch for polyphonic MIDI | Deferred — new dependency |
| 6 | Silero VAD for speech detection | Deferred — torch dependency |
| 7 | Smart reframe with face detection | Deferred — high effort |
| 8 | WhisperX for precision word alignment | Deferred — wav2vec2 dependency |
| 9 | Sidechain compression for ducking | ✓ v0.4.0 |
| 10 | Audio noise reduction | ✓ v0.4.0 |
| 11 | Loudness normalization tool | ✓ v0.4.0 |
| 12 | Waveform with markers | Deferred — low priority |
| 13 | gifski backend | Deferred from Phase 3 — Rust binary |

### Research Sources

Full audit findings are in `AUDIT.md`. Key research sources that informed these decisions:

- Scene detection: [PySceneDetect benchmarks](https://github.com/Breakthrough/PySceneDetect/blob/main/benchmark/README.md), [TransNetV2](https://github.com/soCzech/TransNetV2)
- OCR accuracy: [Tesseract vs EasyOCR vs PaddleOCR comparison](https://toon-beerten.medium.com/ocr-comparison-tesseract-versus-easyocr-vs-paddleocr-vs-mmocr-a362d9c79e66), [ocrmac](https://github.com/straussmaximilian/ocrmac)
- Auto-captions: [WhisperX paper](https://www.robots.ox.ac.uk/~vgg/publications/2023/Bain23/bain23.pdf), [ASS karaoke tags](https://aegisub.org/docs/latest/ass_tags/), [stable-ts](https://github.com/jianfch/stable-ts)
- TTS: [edge-tts](https://github.com/rany2/edge-tts), [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M), [Chatterbox](https://github.com/resemble-ai/chatterbox)
- Storyboard: [Editly](https://github.com/mifi/editly), [Shotstack API](https://shotstack.io/docs/api/), [Remotion](https://www.remotion.dev/docs/the-fundamentals)
- Platform specs: [Sprout Social](https://sproutsocial.com/insights/social-media-video-specs-guide/), [Kapwing](https://www.kapwing.com/resources/social-media-video-aspect-ratios-and-sizes-the-2025-guide/)
- Loudness: [EBU R128](https://tech.ebu.ch/docs/r/r128.pdf), [LUFS targets by platform](https://clickyapps.com/creator/video/guides/lufs-targets-2025)
- Smart trim: [LosslessCut smart cut](https://github.com/mifi/lossless-cut/issues/126)
- Beat detection: [librosa timing bias](https://github.com/librosa/librosa/issues/1052), [BeatNet](https://github.com/mjhydri/BeatNet)
- MIDI: [basic-pitch](https://github.com/spotify/basic-pitch), [Demucs](https://github.com/facebookresearch/demucs)
- GIF: [gifski](https://gif.ski/), [FFmpeg palette guide](https://blog.pkh.me/p/21-high-quality-gif-with-ffmpeg.html)
- Smart reframe: [Autocrop-Vertical](https://github.com/kamilstanuch/Autocrop-vertical), [Google AutoFlip](https://opensource.googleblog.com/2020/02/autoflip-open-source-framework-for.html)
- Stabilization: [vidstab guide](https://www.paulirish.com/2021/video-stabilization-with-ffmpeg-and-vidstab/)
- Blur background: [FFmpeg blur bg gist](https://gist.github.com/ArneAnka/a1348b13fc291f72f862d92f35380428)

---

## v0.1.0 — Initial Release

32 tools. FFmpeg + MLT backends. Project JSON schema with tracks, clips, filters, transitions, audio tracks. Output presets. CLI + MCP server.
