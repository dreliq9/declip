# Declip → Foundational Media Kernel Mapping

**Status:** Phase 0 migration map  
**Date:** 2026-08-24  
**Reference branch:** `planning/media-kernel`

## 1. Purpose

This document maps the current hardened Declip implementation onto the frozen Media Kernel architecture so extraction can happen incrementally rather than through a rewrite.

Governing split:

> **Kernel:** what temporal media computation means and what guarantees hold.  
> **Declip:** what a user/agent wants to accomplish with those primitives.

The current Declip implementation remains authoritative until a kernel replacement path passes conformance.

## 2. Current Declip flow

Today the relevant project-render path is approximately:

```text
Project JSON / Pydantic schema
        |
        +-- authoring conveniences
        |     start="auto"
        |     optional duration
        |     float seconds
        |
        v
build_render_plan()
        |
        | deep-copy + resolve starts/durations
        | probe media when needed
        | emit fallback warnings
        v
normalized Project
        |
        +-------------------+
        |                   |
        v                   v
FFmpeg capability       MLT capability
        |                   |
        +------ auto selector
                    |
             compiler/provider
                    |
             execution backend
                    |
                 artifact
```

This hardened split is already much better than the original architecture because normalization, compiler, and executor are distinct. The kernel migration should preserve that direction while replacing ad-hoc float/project/backend contracts with versioned semantic ones.

## 3. High-level target flow

```text
Declip authoring schema / agent intent
                |
                v
        Declip adapter/policy
                |
        typed CandidateDelta
                v
        Media State Kernel
        revision / snapshot
                |
                v
      typed Editorial Media IR
                |
       controlled Transformation
                |
                v
      Executable Media IR
                |
       capability / lowering
                |
        LoweringReport
                |
                v
        FFmpeg provider
                |
             execution
                |
          artifact + receipt
                |
                v
            Admission
```

## 4. Time representation

### Current

Declip project semantics use Python `float` seconds throughout:

- `Clip.start` numeric or `"auto"`;
- `Clip.duration`;
- `trim_in` / `trim_out`;
- transitions;
- audio starts/durations;
- filter/text timing;
- `Settings.fps` is an integer.

### Kernel

Canonical time is exact:

```text
MediaTime { i64 value, positive i64 scale }
MediaRate { numerator, denominator }
```

### Migration

Do **not** immediately break the public Declip v1 JSON schema.

Add an adapter boundary:

```text
Declip float / authoring input
        |
        | explicit conversion policy
        v
exact MediaTime / MediaRate
```

For decimal JSON numbers, parse/convert deterministically rather than passing through binary-float arithmetic where possible.

A later Declip schema version can expose exact rational/timecode forms directly.

## 5. `start="auto"`

### Current

`build_render_plan()` resolves automatic starts with a float cursor and subtracts incoming transition duration.

### Kernel destination

`"auto"` is **not** canonical Editorial IR.

It is a Declip authoring convenience that becomes a typed placement operation/policy before commit/canonicalization.

Conceptually:

```text
Declip InsertClip(start=auto)
        |
placement policy resolves exact start
        |
CandidateDelta contains exact placement
        v
State / Editorial IR
```

The kernel may expose a typed operation such as `InsertClipAfter` or a placement policy, but committed clip placement is exact/explicit.

## 6. Optional duration and probing

### Current

`build_render_plan()` resolves duration from:

1. explicit `duration`;
2. `trim_out - trim_in`;
3. freeze-frame fallback 5s;
4. source probe;
5. on probe failure, configurable fallback duration (default 10s) plus warning.

### Kernel destination

Canonical State/Editorial IR must not silently contain guessed duration.

Asset ingest/probe produces a versioned `AssetRef` + `StreamDescriptor`/duration evidence.

If Declip chooses a fallback duration as an authoring policy, that is an explicit candidate assumption/operation and should surface in diagnostics/provenance. It cannot become a backend-specific magic constant.

The current 5s freeze and 10s probe fallback remain compatibility behavior in Declip until replaced, not kernel semantics.

## 7. Asset paths

### Current

`Clip.asset` and audio assets are path strings relative to the project file.

### Kernel

Paths are locators, not durable identity.

Kernel State uses:

```text
AssetRef
    durable object identity
    exact external version/hash when consequential
    stream descriptors
    retrieval locator metadata outside identity
```

### Migration

Declip adapter resolves path -> asset registration/ref.

Changing a file at the same pathname must not silently preserve the old exact asset identity/content binding.

## 8. Track and clip model

### Current

```text
Timeline
  video Tracks[]
    Clip[]
  dedicated AudioTrack[]
```

`Track.id` is a user string; clips have no durable IDs.

### Kernel

Phase 1 introduces durable IDs for:

```text
Sequence
Track
Clip
AssetRef
Transition
AudioRoute
OutputIntent
```

### Migration

Declip string track IDs become labels/external aliases while kernel IDs carry identity.

Clip index is never durable identity.

Current video/audio schema shapes can map into typed kernel tracks/routing without forcing Declip v1 to expose the internal IDs immediately.

## 9. Transition representation

### Current

An incoming transition is nested on the right-hand clip as `transition_in`.

### Kernel

Transition is a first-class editorial object with durable identity and explicit adjacent/source relationships.

```text
Transition {
    transition_id
    left_clip_ref
    right_clip_ref
    exact duration/range
    semantic transition type/extension
}
```

### Migration

Adapter transforms `right_clip.transition_in` into a Transition object.

This eliminates the accidental implication that transition identity is the same thing as a property of the right clip.

## 10. Filters/effects

### Current

`FilterType` is one application enum containing:

```text
fade
brightness/contrast/saturation
greyscale
blur
speed/volume
text
LUT
subtitles
watermark
crop_zoom
...
```

### Kernel split

Not every Declip filter belongs in the foundational core.

#### Kernel-semantic operations/intents

Likely foundational or standardized extensions:

```text
TimeTransform / speed
Gain
Scale/Crop/Transform
ColorConvert / LUT intent
Composite/opacity
Transition
Freeze/hold
Audio routing
```

#### Declip/application intent

Remain above the kernel until a reusable semantic contract is justified:

```text
caption wording/style workflow
watermark presets
social template logic
speech-driven ducking policy
high-level text style UX
provider-specific generation
```

Those may lower into kernel primitives/effect extensions without becoming kernel product features.

## 11. Reverse and freeze-frame

### Current

Boolean/value fields directly on `Clip`.

### Kernel

These are explicit temporal semantics:

```text
TimeTransform(reverse)
Hold/FreezeFrame(source_time, duration)
```

They lower into executable temporal operations with declared dependencies and exact time behavior.

## 12. Position and opacity

### Current

`position` and `opacity` live directly on clips and have incomplete backend parity.

### Kernel

They become explicit compositing/transform semantics in Editorial/Executable IR.

A provider that cannot preserve them returns `UNSUPPORTED` or an explicit bake/approximation result rather than simply omitting them.

## 13. Project settings

### Current

```text
resolution
integer fps
background color
```

### Kernel mapping

```text
resolution        -> OutputIntent / typed raster requirement
fps               -> exact MediaRate
background        -> composition/output semantic intent
```

The background is not a reason to hard-code one provider's color producer semantics.

## 14. Output configuration

### Current

```text
path
container format
video codec
quality preset
audio codec
bitrate
```

These combine several layers.

### Split

#### Declip / destination

```text
output path / destination
named convenience preset
```

#### Kernel OutputIntent

```text
semantic dimensions/rate/color/audio intent
required stream/layout semantics
```

#### Execution/provider configuration

```text
container
codec
encoder implementation
bitrate/quality controls
provider-specific knobs
```

#### Admission profile

```text
what resulting artifact must demonstrably satisfy
```

`Quality.high` is not canonical media semantics. It is Declip policy that maps into encoder/resource/profile decisions.

## 15. Presets

### Current

Named presets mutate Declip project output/resolution.

### Target

Presets remain Declip/product policy.

A preset may generate:

```text
candidate OutputIntent edit
execution profile
admission profile
```

but the foundational kernel does not hard-code mutable social-platform branding/policies.

## 16. Project includes

### Current

`Project.includes` is in the public schema but hardened render-plan normalization rejects it because no backend lowers it safely.

### Kernel

The semantic destination is a real `NestedComposition`/versioned project-artifact reference, not a pre-render path string silently concatenated.

Keep current fail-closed behavior until nested composition exists.

## 17. `build_render_plan()`

### Current responsibilities

- deep copy project;
- reject unsupported includes;
- resolve asset locators;
- resolve omitted durations;
- resolve `auto` placement;
- preserve transition overlap;
- emit warnings.

### Kernel migration

Split those responsibilities:

```text
Asset ingest/State
    asset refs + source duration/streams

Declip authoring adapter / State operations
    auto-placement policy

Transformation
    exact-time normalization
    reference resolution
    gap/transition canonicalization
    Editorial verification

Diagnostics
    explicit assumptions/errors
```

`RenderPlan` as currently shaped eventually disappears. Its successful idea—**normalize semantics exactly once before backend compilation**—survives as Transformation.

## 18. Dangerous current fallback to remove from kernel path

Current render-plan duration fallback is useful compatibility UX but must never cross into the foundational contract as silent truth.

Future behavior:

```text
probe succeeds
    -> exact source metadata dependency

probe unknown
    -> candidate remains unresolved / requires explicit duration
       OR
       Declip deliberately supplies assumed duration with diagnostic/provenance
```

A kernel compiler must not invent 10 seconds because probing failed.

## 19. Backend capability checks

### Current

- FFmpeg `can_handle()` encodes one sequential unpositioned video track/no dedicated audio constraint.
- MLT `unsupported_reasons()` explicitly lists semantics it cannot preserve.
- `prepare_project()` selects FFmpeg first, then MLT.

### Kernel

These become:

```text
provider capability descriptors
TargetProfile / legality
CapabilityResolver
LoweringReport
planner selection reasons
```

The strong existing behavior to preserve is fail-closed backend selection.

The weak behavior to remove is application code owning provider-specific capability logic and human-string-only explanations.

## 20. FFmpeg compiler

### Current strengths

- compilation and execution are separated;
- semantic unsupported cases can fail;
- transition duration is validated;
- provider argv generation is centralized.

### Kernel destination

FFmpeg compiler becomes a provider lowering:

```text
Executable Media IR
        |
        v
FFmpeg capability/lowering adapter
        |
        v
FFmpeg execution plan / argv/filtergraph
```

It no longer consumes Declip's authoring `Project` directly.

## 21. Current hidden media probing in compiler

FFmpeg compilation currently checks input assets for audio streams while constructing the filter graph.

This should move earlier.

Target:

```text
Asset ingest/probe
    -> StreamDescriptor(s)

Transformation/plan
    -> already knows whether source audio exists
```

Compilation should not need to rediscover semantic asset structure as an impure side effect.

## 22. Current synthetic silence

When a video clip has no audio, FFmpeg compiler currently inserts a 48 kHz stereo `anullsrc` so clip audio chains can continue.

This is a **consequential inserted operation**.

Kernel path must represent it explicitly:

```text
SilenceSource(MediaType=48k stereo or output-required layout)
```

and bind the choice to output/audio policy.

It must not remain an invisible compiler implementation detail.

## 23. MLT compiler

### Strong behavior to keep

MLT compiler explicitly rejects semantics it cannot faithfully lower rather than silently omitting them.

This aligns directly with kernel target legality.

### Semantics to remove from canonical path

Current MLT XML hard-codes/derives things such as:

```text
integer FPS
sample aspect 1/1
colorspace 709
frame rounding from float seconds
```

Those become explicit provider conversions/assumptions, or the provider is rejected for a target requiring stronger semantics.

Provider defaults never redefine canonical Editorial IR.

## 24. Execution backend

Current FFmpeg backend already largely has the right boundary:

```text
compile elsewhere
select binary
execute subprocess
report progress/errors
```

Kernel Execution should generalize this into provider execution with:

- plan hash;
- resource usage;
- cancellation;
- bounded scheduling;
- artifact hash;
- receipt/provenance;
- provider/tool version binding.

Declip retains progress/UI formatting.

## 25. `PreparedProject`

Current object combines:

```text
normalized Project
project_dir
RenderPlan
chosen backend
total duration
```

Target decomposition:

```text
Committed/Candidate Snapshot
Editorial IR
Transformation result
Executable plan
LoweringReport
Provider selection
Execution request/result
```

Do not create one new mega-`KernelPreparedProject` that recreates the coupling under a new name.

## 26. Project validation

Current `validate_project()` mainly checks schema and path existence.

Target validation layers:

```text
Declip schema validation
asset locator existence/resolution
State/reference validation
Editorial structural/time/type verification
provider target legality
Admission only after artifact exists
```

A project may be semantically valid even when one local provider cannot render it.

## 27. Direct file edit utilities

`declip.edit` contains convenient one-shot FFmpeg-based transformations such as overlays, transitions, color, crop/resize, subtitle burn, etc.

These are Declip capabilities, not automatically State edits.

Migration options:

### Keep as compatibility utilities

They continue to materialize new files directly.

### Later route through kernel

Construct a small ephemeral media program:

```text
AssetRef
  -> operation/effect intent
  -> Executable IR
  -> provider
  -> derived artifact + receipt
```

Only operations explicitly applied to a project candidate become persistent project edits.

This prevents "using the kernel" from forcing every quick file conversion into a project revision.

## 28. Declip features that should stay above the kernel

At least:

```text
MCP/CLI wording and tool UX
social presets/workflows
highlight selection
transcription strategy/provider choice
caption wording/styling policy
speech-ducking workflow intent
storyboard generation
TTS/generative provider orchestration
publishing destinations
template-variable UX
```

They can consume kernel primitives, but their product logic is not foundational media semantics.

## 29. Declip schema migration phases

### Adapter phase

Keep `Project` v1 stable.

Add:

```text
Project v1 -> candidate State/Editorial adapter
```

### Dual-run conformance phase

For supported fixtures:

```text
current render plan/compiler
vs
kernel-derived plan/provider
```

must produce equivalent declared semantics/artifact properties.

### Kernel-authoritative phase

Declip project rendering uses kernel State/Transformation/Execution path.

Legacy render-plan/compiler adapters remain available for compatibility until fixture/conformance coverage proves replacement.

### Future Declip schema v2

Only then consider exposing:

- exact rational rates/times;
- durable object IDs;
- richer color/audio intent;
- explicit candidate/revision concepts;
- nested compositions;
- extension contracts.

Do not make kernel extraction contingent on redesigning the public application schema first.

## 30. First vertical-slice mapping

Use a deliberately small Declip-originated fixture:

```text
Project v1 authoring
  two video clips
  12-frame dissolve
  one audio bed
  exact target dimensions/rate/color/audio intent
```

Adapter performs:

```text
path -> AssetRefs/StreamDescriptors
auto/float time -> exact MediaTime
transition_in -> Transition object
settings/output -> OutputIntent + execution profile
```

Then:

```text
candidate delta
commit revision 1
Editorial IR
Executable IR
FFmpeg provider
artifact + receipt
Admission kernel.basic_delivery_mp4.v1
```

This fixture becomes the proof that the boundary is real.

## 31. Migration rule

> **Do not move code into the kernel merely because Declip currently contains it. Move a behavior only when it expresses reusable media semantics or guarantees. Keep application intent, convenience policy, and workflow orchestration in Declip.**
