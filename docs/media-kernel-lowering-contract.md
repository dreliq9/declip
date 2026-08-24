# Media Kernel Lowering / Semantic-Loss Contract

**Status:** Phase 0 Transformation baseline  
**Date:** 2026-08-24  
**Owner:** Media Transformation Kernel

## 1. Governing question

Transformation/lowering answers:

> **Can this verified source representation be transformed into this target-legal representation while preserving the declared meaning, and if not, exactly what changes?**

It does not answer:

- whether the user likes the result;
- whether an approximation is commercially acceptable;
- whether an artifact passes delivery/QC;
- whether a caller is authorized to invoke a provider;
- whether the result should be committed to State.

Those are policy, Admission, Governance, and State concerns.

## 2. No silent lowering

Every consequential lowering returns a structured `LoweringReport`.

A backend/provider must never turn:

```text
unsupported effect
HDR -> SDR
custom transition -> hard cut
editable graph -> baked pixels
48 kHz -> 44.1 kHz
unknown color -> Rec.709 assumption
```

into a successful-looking render plan without a structured record.

## 3. Source and target binding

Every report binds at least:

```text
source_ir_hash
target_plan_hash
target legality/profile identity through the invocation/context
loss/conversion findings[]
diagnostics[]
```

The report refers to exact input/output representations, not merely human-readable project names.

A report for source hash A cannot be reused as evidence for source hash B without an explicit equivalence/canonicalization proof.

## 4. Status taxonomy

The frozen top-level status vocabulary is:

### `EXACT`

The target representation preserves the declared source semantics without a consequential inserted conversion.

Examples:

- canonical dissolve lowers directly to a provider-native dissolve with equivalent temporal/color behavior;
- gain operation maps directly to equivalent provider gain semantics.

### `EXACT_WITH_INSERTED_CONVERSION`

Source meaning remains preserved, but the target requires one or more explicit conversions/adapter operations.

Examples may include:

- layout-preserving sample-format conversion proven exact for the values/domain in use;
- explicit CPU -> GPU memory transfer when no semantic media conversion occurs **does not** itself require this status, because memory domain is not MediaType; however a pixel representation conversion inserted alongside the transfer does;
- an explicit canonical channel reordering that preserves the declared channel semantics.

The inserted conversion must appear in Executable IR/plan; the report cannot claim a conversion that is invisible in the plan.

### `APPROXIMATED`

The target can produce a useful result, but some declared source semantics/precision cannot be preserved exactly.

Examples:

- precision reduction;
- approximate resampling/filter implementation relative to a stronger declared contract;
- color transform using an approximation profile;
- temporal interpolation/retiming approximation.

Approximation is never silently treated as exact merely because it is visually small.

### `BAKED_LOSS_OF_EDITABILITY`

Rendered appearance/observable output can be preserved sufficiently, but the target representation loses editable semantic structure.

Examples:

- unsupported transition/effect is pre-rendered into pixels;
- nested composition is flattened;
- procedural effect becomes a rendered intermediate;
- live text becomes rasterized/baked output.

This status is distinct from visual approximation. A bake may be pixel-exact while still losing semantic editability.

### `UNSUPPORTED`

No legal target representation is available under the declared target capabilities/policy without violating a required semantic constraint.

No executable target plan may be presented as semantically successful.

## 5. Loss dimensions

Each structured finding carries one or more dimensions:

```text
PRECISION
UNCERTAINTY
PROVENANCE_DETAIL
REVERSIBILITY
EDITABILITY
TIME
COLOR
AUDIO
MEDIA_TYPE
METADATA
```

Dimensions are orthogonal to status.

Examples:

```text
APPROXIMATED + COLOR + PRECISION
BAKED_LOSS_OF_EDITABILITY + EDITABILITY + REVERSIBILITY
UNSUPPORTED + AUDIO + MEDIA_TYPE
EXACT_WITH_INSERTED_CONVERSION + MEDIA_TYPE
```

Future dimensions can be added without reinterpreting existing bits.

## 6. Finding identity and stable codes

Human prose is not the machine contract.

Every finding uses a stable namespaced code, for example:

```text
media.lowering.video.color.precision_reduced
media.lowering.effect.baked_for_target
media.lowering.audio.resample_inserted
media.lowering.transition.unsupported
media.lowering.metadata.dropped_noncritical
```

Diagnostics may provide explanatory messages.

Automation and policies key off code/status/dimensions, not localized prose.

## 7. Scope

A loss/conversion must identify its source semantic object/operation through an exact reference where possible.

Time/range-specific scope should be represented by a Transform-owned namespaced extension until a dedicated range field is proven necessary in a later Core ABI descriptor revision.

Example extension concept:

```text
media.transform.loss_scope.v1 {
    time_domain
    affected_range
}
```

Do not encode a time range in a message string.

## 8. Inserted conversions are executable facts

An inserted conversion is both:

```text
Transformation fact
    -> reported in LoweringReport

Executable operation
    -> present in Executable Media IR / target plan
```

The two must be traceably bound.

Examples:

```text
ColorConvert
Scale
Resample
ChannelRemap
PixelFormatConvert
SampleFormatConvert
FrameRateConvert
AlphaConvert
MetadataMap
```

A provider adapter cannot silently perform a conversion inside an opaque call and still claim an exact plan unless the semantic conversion is surfaced by the planner/report.

## 9. Target legality profile

Lowering occurs against an explicit target legality/capability profile.

Conceptually:

```text
TargetProfile {
    target identity/version
    legal executable dialects/ops
    supported media types
    supported temporal behavior
    supported color behavior
    memory/resource capabilities
    provider constraints
    optional policy constraints
}
```

Transformation verifies legality; Execution chooses/schedules concrete implementations among legal alternatives.

A target profile is versioned. Changing provider capabilities cannot retroactively change a historical lowering report.

## 10. Target capability vs policy

Keep these separate:

```text
Capability fact:
    provider can bake this effect

Policy:
    final archival master forbids editability loss
```

Transformation reports the available lowering and its consequence. Policy decides whether to proceed.

This allows the same kernel to serve:

- interactive preview;
- review proxy;
- final master;
- archival/interchange export;

without lying about the semantics.

## 11. Overall report status

`overall_status` summarizes the report for coarse routing, while individual findings remain authoritative detail.

Aggregation rule v0:

1. any blocking `UNSUPPORTED` -> overall `UNSUPPORTED`;
2. otherwise any `BAKED_LOSS_OF_EDITABILITY` -> overall `BAKED_LOSS_OF_EDITABILITY`;
3. otherwise any `APPROXIMATED` -> overall `APPROXIMATED`;
4. otherwise any `EXACT_WITH_INSERTED_CONVERSION` -> overall `EXACT_WITH_INSERTED_CONVERSION`;
5. otherwise `EXACT`.

This ordering is an operational summary, not a claim that editability loss is universally worse than every approximation. Policies inspect findings/dimensions for nuanced decisions.

## 12. Required vs optional semantics

Source/target profiles may mark semantics as:

```text
REQUIRED
PREFERRED
ADVISORY
```

A target inability to preserve a required semantic generally becomes `UNSUPPORTED` unless the calling policy explicitly authorizes a different candidate lowering and records that policy choice.

A preferred/advisory semantic may produce approximation/loss findings.

Do not downgrade a required semantic merely because a fallback exists.

## 13. Unknown extensions

For Editorial/Executable extensions:

- unknown critical extension -> cannot claim exact understanding; target lowering fails/blocks unless a qualified handler exists;
- unknown noncritical extension -> may pass through or be ignored according to its owner contract, with any consequential loss recorded;
- dropped noncritical metadata still appears as a metadata/provenance-detail finding when the drop matters to the declared target contract.

## 14. Backend fallback

When multiple backends/providers exist:

```text
Provider A -> EXACT
Provider B -> APPROXIMATED
Provider C -> UNSUPPORTED
```

Capability planning may select Provider A.

If only B is available, the planner reports the approximation and policy decides.

Never choose B silently because it is installed locally when the caller requested exact semantics.

## 15. Preview vs final

Preview and final may select different implementations but share one declared project meaning.

Example:

```text
Preview policy
    allows APPROXIMATED scaling/filter
    records approximation

Final policy
    requires EXACT / stronger implementation
```

The preview plan does not mutate the committed Editorial IR to reflect the cheaper implementation.

## 16. Baked intermediates

A bake is an explicit derived artifact with dependencies/provenance.

It must bind:

```text
source revision / Editorial IR hash
source operation/scope
bake plan hash
provider/tool versions
artifact hash
loss report
```

If an input changes, dependency invalidation can dirty the bake.

Baked output is never substituted for the editable source object in historical State unless an explicit edit/commit does so.

## 17. Examples

### Exact transition

```text
Editorial Transition(dissolve, 12 frames)
    -> exec.transition.dissolve

status: EXACT
losses: none
```

### Baked transition for limited interchange target

```text
Editorial Transition(custom procedural)
    -> rendered intermediate

status: BAKED_LOSS_OF_EDITABILITY
dimensions: EDITABILITY | REVERSIBILITY
```

### HDR target unavailable

```text
Editorial/output intent requires HDR
Target supports SDR only
Policy forbids tone-map fallback

status: UNSUPPORTED
dimensions: COLOR | PRECISION
```

### Explicit allowed tone mapping

```text
HDR -> SDR ColorConvert/ToneMap inserted

status: APPROXIMATED
dimensions: COLOR | PRECISION
```

### Audio rate conversion

```text
44100 Hz source -> 48000 Hz required execution port
Resample inserted

status depends on declared semantic/quality contract;
never hidden inside decoder/provider setup
```

## 18. Verification rules

A valid `LoweringReport` must satisfy:

- source hash is exact/non-null according to hash contract;
- target plan hash binds the produced target representation;
- every finding has a known status and stable code;
- dimensions are consistent with the finding code/status;
- source ref, if present, resolves in the bound source snapshot/IR scope;
- every reported inserted conversion is traceable to target-plan operations;
- every target-plan consequential conversion has a report finding unless the contract explicitly defines it as semantic identity;
- `overall_status` matches deterministic aggregation;
- `EXACT` cannot contain non-exact findings;
- `UNSUPPORTED` cannot be paired with a supposedly successful semantically legal final target plan.

## 19. Conformance cases

Phase 1/2 tests should include:

```text
exact direct lowering
lossless explicit conversion
precision approximation
HDR -> SDR policy cases
sample-rate conversion
channel-layout conversion
editable transition -> baked target
unsupported extension
provider A exact / provider B approximate selection
preview approximation vs exact final
multiple simultaneous findings and deterministic aggregation
stale source hash prevents report reuse
```

## 20. Exit criterion

> For any target plan produced from Editorial/Executable IR, the kernel can explain in machine-readable form whether meaning was preserved exactly, preserved through explicit conversion, approximated, baked with editability loss, or unsupported—and no provider can hide a consequential conversion behind a successful render call.
