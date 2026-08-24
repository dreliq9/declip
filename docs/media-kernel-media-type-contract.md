# Media Kernel MediaType / StreamDescriptor Contract

**Status:** Phase 0 semantic baseline  
**Date:** 2026-08-24  
**Core ABI representation:** `mk_media_type`, `mk_stream_descriptor`

## 1. Governing question

`MediaType` answers:

> **What semantic media representation flows through this port/stream?**

It does not answer:

- where the bytes currently live;
- which backend owns them;
- which decoder/GPU/provider will process them;
- whether the user is authorized to access them;
- whether the resulting artifact is acceptable for delivery.

Those belong to Execution, Governance, and Admission.

## 2. Semantic type vs resource placement

This boundary is mandatory:

```text
MediaType
    1920x1080
    video
    exact color semantics
    pixel/sample representation
    audio layout semantics

MemoryDomain / ResourceDescriptor
    CPU
    Metal
    Vulkan
    D3D
    CUDA
    hardware decoder surface
    remote/provider object
```

The same semantic frame may move between memory domains without changing its `MediaType` if no semantic conversion occurs.

A memory transfer that also changes precision/color/sample representation is two explicit operations, not one hidden provider move.

## 3. MediaKind

v0 core kinds:

```text
UNKNOWN
VIDEO
AUDIO
DATA
```

`UNKNOWN` is not a wildcard for planning. It represents missing/undetermined semantics and generally blocks operations that require a concrete type.

Future semantic kinds may be added through versioning/extensions rather than repurposing codes.

## 4. Format names

Format identifiers are controlled namespaced semantic strings.

Examples of the naming style:

```text
media.video.raw.yuv420p10le
media.video.raw.rgba16f
media.audio.raw.f32p
media.audio.raw.s24
media.data.timed_metadata
```

Provider-native enums are adapter inputs, not canonical identifiers.

Do not use the numeric values of:

```text
AVPixelFormat
AVSampleFormat
DXGI_FORMAT
MTLPixelFormat
VkFormat
codec SDK enums
```

as kernel semantic registry values.

### Encoded essence

Phase 0/1 `MediaType` primarily models semantic stream/sample representation used by Editorial/Executable ports. Codec/container/delivery constraints require their own execution/admission descriptors rather than overloading raw media type with every encoder setting.

An encoded representation may be named through a namespaced extension/format contract when needed, but codec configuration does not become a property of an editorial clip merely because a source file is H.264.

## 5. Video type

A concrete video `MediaType` may carry:

```text
format_name
width
height
sample_aspect_ratio
field_order
color
video_flags
```

### Dimensions

For concrete raster video:

```text
width  > 0
height > 0
```

Resolution is semantic at the executable-port/output-intent level. A transform that changes dimensions is explicit.

### Sample aspect ratio

`sample_aspect_ratio` is an exact `mk_ratio`.

It is active only when `MK_VIDEO_FLAG_HAS_SAMPLE_ASPECT_RATIO` is set.

Rules:

- numerator/denominator positive when present;
- square pixels are `1/1`;
- absence is not silently interpreted as `1/1` when source semantics distinguish unknown from square.

Display aspect ratio is derived from dimensions and SAR; do not store a conflicting independent DAR as canonical truth.

### Field order

v0:

```text
UNKNOWN
PROGRESSIVE
TOP_FIRST
BOTTOM_FIRST
```

Interlace/progressive state is semantic. A deinterlacer is an explicit transformation.

## 6. Color contract

Color is kernel-level semantics, not backend metadata decoration.

`mk_color_descriptor` carries:

```text
primaries
transfer
matrix
range
chroma_location
alpha_mode
bit_depth
flags
```

### Registry policy

Where standardized CICP/H.273 code points exist for primaries, transfer characteristics, and matrix coefficients, the kernel uses those semantic code points rather than copying a backend's enum numbering.

Kernel registries define concepts not directly covered by those code points, including alpha/range/chroma-location policy where necessary.

### Explicit unknown vs implicit default

Unknown/unspecified color is a real state.

The kernel must never silently convert:

```text
unknown -> Rec.709
unknown -> sRGB
limited -> full
scene-referred -> display-referred
```

because a backend has a convenient default.

A policy may request an assumption, but the inserted assumption/conversion must appear in the plan/lowering report/provenance as appropriate.

### Bit depth

Bit depth is semantic precision information where applicable. It is distinct from memory container width and from floating-point format naming.

## 7. Audio type

Concrete raw audio may carry:

```text
sample_rate
sample_format_name
channel_count
channel_order
channel_layout_name
channel_positions[]
audio_flags
```

### Sample rate

Sample rate is an integer samples/second for a concrete PCM-like stream.

Resampling is an explicit executable operation with declared quality/precision behavior.

### Sample format

Namespaced semantic examples:

```text
media.audio.raw.s16
media.audio.raw.s24
media.audio.raw.s32
media.audio.raw.f32
media.audio.raw.f32p
media.audio.raw.f64
```

Packed/planar distinctions that affect buffer interpretation are part of the representation.

### Channel count is insufficient

`channel_count = 6` alone does not define whether audio is 5.1, custom six-channel, first-order ambisonics plus extras, or another ordering.

v0 channel-order classes:

```text
UNSPECIFIED
CANONICAL
CUSTOM
AMBISONIC
```

### Canonical layout

For standard layouts, `channel_layout_name` may identify a controlled semantic layout such as stereo/5.1/7.1 variants.

The registry defines exact ordered channel meaning rather than relying on a provider's speaker-mask numeric value.

### Custom positions

Custom layouts expose an ordered pointer-array of `mk_channel_position` descriptors.

Each position uses a namespaced semantic position name, for example:

```text
media.channel.front_left
media.channel.front_right
media.channel.front_center
media.channel.lfe
media.channel.side_left
media.channel.side_right
```

For a concrete custom ordered layout:

```text
positions.count == channel_count
```

unless an extension/version explicitly defines another interpretation.

### Ambisonics

Ambisonic order/normalization/channel semantics require explicit descriptors/extensions; do not collapse them into an ordinary speaker-mask layout.

## 8. Data/timed metadata

`DATA` is reserved for typed timed/non-A/V streams such as metadata, captions, analysis tracks, or control/event data.

Phase 1 should not force all metadata into one generic byte stream. Use namespaced format/extension contracts and explicit time domains.

Caption/subtitle editorial semantics may later warrant richer dedicated types while preserving DATA interoperability where appropriate.

## 9. StreamDescriptor

A stream descriptor binds:

```text
stream_id
pointer -> MediaType
nominal_rate
time_domain
stream_flags
extensions
```

### Stream identity

`stream_id` identifies the logical stream within its owner/context. It is not a decoder/provider handle.

### MediaType pointer

The pointer is an ABI-evolution mechanism, not shared mutable ownership.

The pointee is borrowed/immutable for the declared call/result lifetime. Each descriptor validates its own `struct_size`/version independently.

### Nominal rate

`nominal_rate` expresses cadence when meaningful:

```text
30000/1001 video
48000/1 audio sample cadence
```

It does not replace exact sample/frame timestamps.

For VFR:

- exact timestamps are authoritative;
- nominal rate may be informational/planning intent;
- a planner cannot reconstruct missing exact PTS from nominal rate unless an explicit policy allows it.

## 10. Time domain

Core ABI reserves distinct domains:

```text
SOURCE
PRESENTATION
SEQUENCE
SAMPLE
WALL_CLOCK
INGEST
REVISION
TIMECODE
```

A stream descriptor names which domain its primary timestamps inhabit.

Conversions between time domains are explicit mappings/transforms. Equal numeric `MediaTime` values in two different domains are not automatically the same event.

## 11. Type compatibility

Exact type equality and operation compatibility are separate questions.

### Exact equality

Two concrete types are exactly equal only when all semantically consequential active fields/extensions match after canonical normalization.

### Operation compatibility

An operation declares what it accepts.

Examples:

```text
Gain
    accepts audio, any sample rate/layout it can preserve

StereoDownmix
    accepts audio layouts with declared downmix semantics

ColorConvert
    accepts video with sufficient source color semantics

Composite
    requires compatible raster/color/alpha semantics or explicit inserted conversions
```

The type checker may produce a required-conversion set. It never silently performs those conversions.

## 12. Conversion planning

A mismatch may resolve as:

```text
EXACT
    no semantic conversion

EXACT_WITH_INSERTED_CONVERSION
    e.g. explicit lossless/declared format conversion

APPROXIMATED
    e.g. quality/precision compromise

UNSUPPORTED
    no legal conversion/provider path
```

Loss of editability is normally an operation/lowering property rather than a MediaType conversion.

## 13. Editorial vs Executable use

### Editorial IR

Editorial state should usually express intent rather than lock every clip to one decoded pixel format.

Examples:

```text
AssetRef has source stream descriptors
OutputIntent declares target raster/rate/color/audio intent
EffectIntent declares semantic requirements
```

### Executable IR

Executable operation ports carry/infer concrete `MediaType`s sufficient to plan conversions and providers.

This prevents source codec accidents from becoming canonical editorial semantics while still making execution fully typed.

## 14. Provider lowering

A provider adapter maps:

```text
Kernel MediaType
    <->
provider/native representation
```

Examples:

```text
MediaType -> AVPixelFormat + AVFrame color fields
MediaType -> VkFormat + image/view metadata
MediaType -> MTLPixelFormat + color attachments
MediaType -> AVChannelLayout / native audio layout
```

Mapping can be:

```text
exact
exact with explicit conversion
approximate
unsupported
```

and feeds the `LoweringReport`.

## 15. Validation rules v0

At minimum:

### Common

- recognized/allowed `kind`;
- descriptor version/size valid;
- format names valid UTF-8/namespaced when present;
- unknown critical extensions fail closed.

### Video

- positive raster dimensions for concrete raw video;
- valid SAR if present;
- known/allowed field-order code;
- color fields structurally legal;
- no audio-only fields interpreted as video semantics.

### Audio

- positive sample rate for concrete raw audio;
- positive channel count;
- valid sample-format identifier;
- channel-order/layout consistency;
- custom position count/order constraints;
- no video-only fields interpreted as audio semantics.

### Stream

- non-null valid MediaType pointer;
- valid stream ID according to owner scope;
- positive nominal rate when present/required;
- known time-domain semantics;
- no assumption that nominal rate implies CFR.

## 16. Phase 1 conformance fixtures

Create fixtures for:

```text
1920x1080 Rec.709-ish SDR 8-bit
3840x2160 HDR 10-bit
anamorphic video with non-1/1 SAR
progressive vs interlaced video
stereo 48 kHz f32
5.1 48 kHz
custom ordered channels
ambisonic declaration
44.1 kHz -> 48 kHz required resample
VFR stream with nominal rate + exact PTS
unknown color requiring fail/assumption policy
CPU/GPU versions of identical semantic MediaType
```

Required property for the final pair:

> changing memory domain alone does not change semantic `MediaType` hash/equality.

## 17. Exit criterion

> The kernel can type an editorial/output stream and every executable port strongly enough to determine whether two operations connect exactly, require an explicit conversion, require an approximation/loss record, or are unsupported—without importing a provider-native enum or memory-domain concept into canonical media semantics.
