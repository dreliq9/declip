# Declip Audit — Research Findings & Upgrade Plan

Compiled 2026-03-29 from 6 parallel research agents.

---

## PART 1: Existing Tools — What Needs Fixing

### Critical Bugs (fix immediately)
| Issue | Location | Fix |
|-------|----------|-----|
| Watermark filter is `pass` — never implemented | `ffmpeg.py:114-118` | Implement overlay input handling |
| Project renderer doesn't crossfade audio on transitions | `ffmpeg.py:343-357` | Add `acrossfade` (MCP tool does it, backend doesn't) |
| `amix` normalizes by default causing volume pumping | `edit_tools.py` audio_mix | Add `normalize=0` to amix filter |
| Trim has no keyframe awareness — glitchy cuts | `quick_tools.py:37-72` | Add `-avoid_negative_ts make_zero`, offer smart-cut mode |

### High-Impact Upgrades (existing tools, better implementations)

| Tool | Current | Best-in-class | Upgrade |
|------|---------|--------------|---------|
| **OCR** | Tesseract (0.38 accuracy) | macOS Vision (0.92) | Switch to `ocrmac` on Mac, PaddleOCR cross-platform |
| **Scene detection** | Manual frame diff | PySceneDetect ContentDetector | pip install pyscenedetect, ~30 lines |
| **Transcription** | faster-whisper (segment-level) | WhisperX (word-level + diarization) | Add word_timestamps=True, optional WhisperX |
| **Contact sheet** | Even spacing only | Scene-based sampling | Feed detect_scenes timestamps into contact_sheet |
| **Loudness** | loudnorm (single number) | ebur128 (time-series) | Switch to ebur128, add momentary/short-term LUFS |
| **Review pipeline** | 3-phase (frames + scenes + silence) | Add blackdetect + freezedetect | Same FFmpeg filter pattern, catches render bugs |
| **Audio-to-MIDI** | pYIN (monophonic only) | Spotify basic-pitch (polyphonic) | pip install basic-pitch |
| **Concat** | Always re-encodes | Smart: demuxer when codecs match | Probe inputs first, use -c copy when possible |

### Medium-Priority Improvements

| Tool | What's Missing | How to Add |
|------|---------------|-----------|
| **Transitions** | Only 7 of 44 xfade types | Expand TransitionType enum |
| **Text overlay** | No outline, shadow, animation | Expose drawtext shadow params; add ASS mode for advanced |
| **Speed** | No frame interpolation for slow-mo | Add minterpolate option |
| **Color** | Only eq filter | Add colorbalance, colortemperature, curves, auto-levels |
| **Stabilize** | Hardcoded smoothing=10 | Expose smoothing, zoom, tripod params |
| **Reverse** | Loads entire video into RAM | Chunked approach for >30s videos |
| **Split screen** | No PIP, no borders, drops audio | Add PIP layout, border param, audio_from param |
| **Subtitle burn** | Uses subtitles= for everything | Auto-detect .ass vs .srt, use ass= filter for ASS |
| **GIF** | FFmpeg palette only | Optional gifski backend for better quality |
| **Probe** | Missing HDR, bit depth, bitrate | Expand AssetInfo dataclass |

---

## PART 2: New Capabilities to Build

### 1. Auto-Captions (word-level styled subtitles)

**Best approach:** faster-whisper `word_timestamps=True` + VAD → generate ASS with `\k` karaoke tags → FFmpeg `ass=` burn-in.

**Why this beats everything else:**
- CapCut can't export word-level timing
- WhisperX is more accurate but heavier (wav2vec2 dependency)
- We already have faster-whisper installed

**Implementation:**
```
audio → faster-whisper (word_timestamps=True, vad_filter=True)
  → word-level JSON [{word, start, end, confidence}, ...]
  → Python ASS generator (karaoke \k tags, styled)
  → FFmpeg ass= filter burn-in
```

**Style presets to offer:**
- `minimal` — white text, bottom center, no highlight
- `karaoke` — word-by-word highlight (primary → secondary color)
- `bold` — large text, center screen, background box (TikTok/Reels style)
- `news` — lower third, outline, no animation

**Key decisions:**
- Use ASS format (not SRT) — only format that supports word-level animation
- faster-whisper word timestamps are good enough for most content
- Add optional WhisperX alignment for precision-critical work

---

### 2. TTS Voiceover

**Best approach:** edge-tts (primary) + macOS `say` (fallback).

**Why edge-tts wins:**
- Free neural voices (same as Azure paid API)
- 400+ voices, 74 languages
- **Word-level timing metadata** — returns WordBoundary events
- pip install, no GPU, no API key
- Quality comparable to ElevenLabs for narration

**Offline alternatives:** Kokoro (82M params, near-commercial quality), Piper (fastest, lightest)

**Implementation:**
```
script text → edge-tts (with word boundaries)
  → WAV audio + word timing JSON
  → optional: generate ASS captions from same timing data
  → place on declip timeline
```

**Key features:**
- Voice selection by name (en-US-GuyNeural, en-US-JennyNeural, etc.)
- Rate/pitch/volume control via SSML
- Auto-chunk long text at sentence boundaries (<2000 chars per call)
- Resample output to 48kHz to match video audio
- Word-level timing output for caption sync

**Risk:** edge-tts uses an unofficial Microsoft endpoint. Could be throttled. Mitigate with offline fallback.

---

### 3. Storyboard Assembly

**Best approach:** Shot-list schema that compiles to existing track format + `"start": "auto"` sequential mode.

**Key insight from research:** Every successful declarative video tool (Editly, Shotstack, Remotion) converges on the same pattern. The #1 pain point is manual timestamp math.

**Implementation — two features:**

**A. Auto-sequencing (`start: "auto"`):**
Add to existing schema. When a clip has `"start": "auto"`, compute placement from previous clip's end minus transition overlap. Eliminates timestamp math entirely.

**B. Shot-list format (higher-level input):**
```json
{
  "shots": [
    {"asset": "intro.mp4", "duration": 3, "transition": "dissolve"},
    {"narration": "Welcome to the future", "asset": "hero.mp4"},
    {"narration": "Everything changed", "b_roll": "explosion.mp4"},
    {"asset": "outro.mp4", "duration": 5}
  ],
  "music": "bg_music.mp3",
  "voice": "en-US-GuyNeural",
  "style": "bold"
}
```
This compiles to: TTS generates narration audio → audio duration drives shot timing → auto-caption from same audio → music ducked under speech → full project.json generated → render.

**Speech duration estimation:** `word_count / 130 * 1.1` (130 WPM + 10% pause buffer). Or generate TTS first and use actual duration.

---

### 4. Multi-Platform Export

**Best approach:** Platform preset profiles + parallel FFmpeg jobs + 3 reframe strategies.

**Three reframe targets cover everything:**
- 16:9 → YouTube, LinkedIn, Twitter (master as-is)
- 9:16 → Shorts, Reels, TikTok (needs reframe)
- 1:1 or 4:5 → Instagram Feed (needs crop)

**Reframe strategies (user picks per export):**
- `center_crop` — fast, loses edges
- `blur_bg` — blurred zoomed copy behind sharp original (looks pro)
- `smart_crop` — offset the crop window (manual x offset or future AI)

**Platform presets:**

| Preset | Resolution | Aspect | LUFS | Max Size | Codec |
|--------|-----------|--------|------|----------|-------|
| `youtube` | 1920x1080 | 16:9 | -14 | 256 GB | h264/aac |
| `youtube-4k` | 3840x2160 | 16:9 | -14 | 256 GB | h264/aac |
| `shorts` | 1080x1920 | 9:16 | -14 | 256 GB | h264/aac |
| `reels` | 1080x1920 | 9:16 | -11 | 4 GB | h264/aac |
| `tiktok` | 1080x1920 | 9:16 | -11 | 287 MB | h264/aac |
| `twitter` | 1280x720 | 16:9 | -14 | 512 MB | h264/aac |
| `linkedin` | 1920x1080 | 16:9 | -14 | 5 GB | h264/aac |
| `instagram-feed` | 1080x1080 | 1:1 | -11 | 4 GB | h264/aac |
| `instagram-4x5` | 1080x1350 | 4:5 | -11 | 4 GB | h264/aac |

**Implementation:**
```
master.mp4 + platform list
  → parallel FFmpeg jobs (one per platform)
  → each: reframe → loudnorm to target LUFS → encode
  → output: youtube.mp4, tiktok.mp4, reels.mp4, etc.
```

**Key details:**
- Always export at CRF 18, let platforms re-compress
- Target -1.5 dBTP true peak (platforms clip at 0)
- Add `-colorspace bt709` tags to prevent color shifts
- Burned-in captions for vertical (standard for short-form)
- Use parallel jobs (Pattern B) not single-command multi-output

---

## PART 3: Priority Order

### Phase 1 — Fix what's broken (quick wins)
1. Fix watermark `pass` in ffmpeg.py
2. Fix audio crossfade in project renderer
3. Fix amix normalize=0
4. Add -avoid_negative_ts to trim
5. Switch OCR to ocrmac on macOS
6. Scene detection → PySceneDetect
7. Contact sheet: scene-based sampling
8. Review pipeline: add blackdetect + freezedetect

### Phase 2 — New pipeline tools
9. Auto-captions (faster-whisper word-level → ASS → burn-in)
10. TTS voiceover (edge-tts with word timing)
11. Multi-platform export (presets + reframe + loudnorm)
12. Auto-sequencing (`start: "auto"` in schema)

### Phase 3 — Polish existing tools
13. Smart trim (keyframe-aware hybrid cut)
14. Smart concat (demuxer when codecs match)
15. Expand transitions to all 44 xfade types
16. Loudness upgrade (ebur128 time-series)
17. Transcription word-level (faster-whisper word_timestamps=True)
18. Chunked reverse for long videos

### Phase 4 — Advanced
19. Shot-list format → project compiler
20. minterpolate slow-mo
21. colorbalance/curves/temperature
22. basic-pitch for polyphonic MIDI
23. Silero VAD for speech detection
24. gifski backend
25. Smart reframe with face detection (future)
