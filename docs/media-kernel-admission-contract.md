# Media Kernel Admission / Acceptance Contract

**Status:** Phase 0 Admission baseline  
**Date:** 2026-08-24  
**Owner:** Media Admission Kernel

## 1. Governing question

Admission answers:

> **Does this exact artifact satisfy this exact declared delivery/acceptance profile, under these checker versions, assumptions, and evidence?**

It does **not** answer:

- whether the edit is creatively good;
- whether the source footage is factually true;
- whether provenance proves truth;
- whether a user was authorized to render/publish;
- whether another artifact with the same filename is accepted;
- whether a future platform requirement is still the same as today's.

## 2. Render success is not acceptance

These are distinct states:

```text
Execution succeeded
    -> artifact bytes exist

Admission accepted
    -> artifact satisfies profile P under exact checks/evidence
```

A renderer may successfully create a file that:

- is truncated;
- has wrong dimensions;
- has wrong audio layout;
- has A/V drift;
- carries inconsistent HDR/color metadata;
- fails decode-through;
- violates a delivery profile;
- lacks required provenance.

That artifact is **rendered but not accepted**.

## 3. Only Admission creates AcceptanceRecord

There is no generic mutable:

```text
verified = true
accepted = true
```

field that arbitrary callers may set.

Only Admission creates an `AcceptanceRecord` after evaluating a declared profile.

Other kernels may produce evidence/check results, but cannot mint an Admission-owned acceptance decision.

## 4. Exact binding

Every acceptance record binds at least:

```text
artifact_ref + content_hash
acceptance_profile_id/version
checker identities/versions
project revision / snapshot where relevant
execution-plan hash
output intent/profile bindings
assumptions
evidence/check results
acceptance vector
record lifecycle/status
```

If artifact bytes change, the old acceptance record does not transfer.

If profile/checker semantics change, the historical record remains evidence for the old profile/checker binding and does not silently become a record under the new version.

## 5. CheckResult

A checker produces a typed result:

```text
CheckResult {
    checker_id
    checker_version
    check_class
    artifact_hash
    bound_snapshot/revision/plan refs
    status
    certificate_mode
    findings[]
    evidence_refs[]
    assumptions[]
    dependencies[]
}
```

### Check status

```text
PASS
FAIL
INDETERMINATE
ERROR
```

#### PASS

The checker established its exact declared proposition.

#### FAIL

The checker deterministically/validly established that the requirement is not satisfied.

#### INDETERMINATE

Available evidence is insufficient to establish PASS or FAIL under the checker contract.

Examples:

- required source metadata unavailable;
- external certificate cannot be validated;
- a statistical quality criterion lacks sufficient sample evidence.

Do not collapse indeterminate into pass.

#### ERROR

The checker could not complete its own procedure due to execution/tool failure.

Do not confuse checker error with artifact failure.

## 6. Certificate / evidence modes

At minimum distinguish:

```text
KERNEL_CHECKABLE
DETERMINISTIC_REPLAY
REPRODUCIBLY_COMPUTED
SIGNED_ATTESTATION
TRUSTED_EXTERNAL_CHECKER
OPAQUE_ASSERTION
UNSAFE_OVERRIDE
```

A statement's evidence mode matters.

Examples:

```text
"MP4 parses and all frames decode"
    deterministic local checker

"Broadcast facility certified loudness"
    signed/trusted external attestation

"LLM says this looks correct"
    opaque/statistical evidence, not deterministic structural proof
```

## 7. Acceptance vector

Do not reduce qualification to one boolean before preserving dimension-level status.

First generic media acceptance vector:

```text
STRUCTURAL
DECODABILITY
DURATION_TIMING
FRAME_INTEGRITY
AV_SYNC
VIDEO_MEDIA_TYPE
AUDIO_MEDIA_TYPE
COLOR_PIPELINE
LOUDNESS_AUDIO_POLICY
CAPTIONS_ACCESSIBILITY
PROVENANCE_COMPLETENESS
DELIVERY_PROFILE
NONDETERMINISM_DISCLOSURE
```

Each dimension can be:

```text
PASS
FAIL
INDETERMINATE
NOT_APPLICABLE
```

Profiles decide which dimensions are required.

## 8. Acceptance profile

An acceptance profile is a versioned deterministic policy over check results.

Conceptually:

```text
AcceptanceProfile {
    profile_id
    profile_version
    required_dimensions
    checker requirements
    require[]
    forbid[]
    require_any[]
    assumptions policy
    indeterminate policy
    dependency/invalidation policy
}
```

The profile is data/contract, not hard-coded mutable platform folklore in random checker code.

## 9. First stable profile: `kernel.basic_delivery_mp4.v1`

This is the first Phase 0/vertical-slice profile.

It intentionally validates a generic deterministic MP4 delivery artifact rather than claiming to encode a mutable YouTube/Instagram/broadcast policy.

### Required bindings

The admission invocation binds:

```text
artifact hash
committed project revision
execution-plan hash
OutputIntent
profile kernel.basic_delivery_mp4.v1
```

### Required checks

#### Structural

- artifact exists/readable;
- container parses as MP4/ISO-BMFF profile allowed by the checker contract;
- expected primary video stream exists;
- declared required audio stream exists when OutputIntent requires audio;
- no fatal structural/parser errors.

#### Decodability / integrity

- primary encoded streams decode through the declared artifact duration without fatal decode error;
- no missing/truncated terminal data that violates the profile;
- frame/sample count/timestamp continuity meets the checker contract.

#### Output intent match

- raster dimensions match exact OutputIntent;
- declared frame-rate/cadence semantics match the output intent/profile;
- video duration matches exact expected timeline semantics within the explicitly defined encoded-boundary tolerance;
- audio sample rate/layout matches OutputIntent;
- required stream count/type matches intent.

#### A/V synchronization

- first/last timestamps and duration relationship remain within an explicitly versioned synchronization tolerance;
- no hidden constant drift beyond policy.

Tolerance is profile/checker data, never an undocumented `abs(x-y)<magic` in application code.

#### Color

- encoded color metadata is consistent with the declared output color intent to the extent the container/codec can represent it;
- required primaries/transfer/matrix/range metadata is present where the profile requires it;
- a known lowering deviation must match the bound `LoweringReport`; unexpected deviation fails/blocks.

#### Provenance completeness

At minimum the receipt/provenance graph can bind:

```text
artifact hash
project revision
execution plan
source/input hashes as required
backend/tool versions
lowering report
```

This dimension proves provenance completeness, not factual truth.

### Not initially required

`kernel.basic_delivery_mp4.v1` does not claim universal requirements for:

- broadcast loudness;
- captions/accessibility;
- platform upload policy;
- editorial quality;
- subjective visual quality;
- legal/licensing clearance.

Those dimensions are `NOT_APPLICABLE` or outside this profile unless separately bound.

## 10. Profile result logic

A profile produces `ACCEPTED` only when all required dimensions satisfy profile rules.

v0 logic:

```text
required FAIL
    -> REJECTED

required ERROR
    -> ERROR / not accepted

required INDETERMINATE
    -> INDETERMINATE unless profile explicitly permits it

all required PASS
    -> ACCEPTED
```

No default profile treats indeterminate as accepted.

## 11. AcceptanceRecord

Conceptually:

```text
AcceptanceRecord {
    acceptance_id
    artifact_ref/hash
    profile_ref/version
    project_revision_ref
    execution_plan_hash
    checker_results[]
    acceptance_vector
    evidence_refs[]
    assumptions[]
    dependency_refs[]
    accepted_at
    lifecycle
}
```

The record is immutable. Lifecycle events reference it rather than rewriting its historical contents.

## 12. Lifecycle

Acceptance can have lifecycle states/events such as:

```text
ACTIVE
STALE
SUSPENDED
CONTESTED
REVOKED
SUPERSEDED
```

Examples:

### Stale

A bound checker/profile/dependency is superseded and current use requires requalification.

### Contested

New evidence challenges the record without erasing the fact that it was previously issued.

### Revoked

Admission/authority process withdraws its use under declared policy.

### Superseded

A newer acceptance record replaces it for current workflow purposes.

Historical record remains immutable.

## 13. Dependency invalidation

Acceptance depends on exact:

```text
artifact hash
profile version
checker versions
assumptions/evidence dependencies
```

Changing the project after render does not mutate the old artifact's record.

Rendering a new artifact from the new revision requires new Admission.

If a checker/profile is updated due to a bug or policy change, owner policy decides whether old records become stale/revoked/currently unacceptable; the old evidence record is not rewritten.

## 14. Acceptance vs lowering

Lowering and Admission answer different questions.

```text
LoweringReport:
    what semantics changed while creating the target plan?

AcceptanceRecord:
    does the resulting artifact satisfy delivery profile P?
```

A profile may forbid certain lowering findings.

Example archival profile:

```text
forbid BAKED_LOSS_OF_EDITABILITY
forbid APPROXIMATED color
```

A review proxy profile may permit them with disclosure.

Admission consumes the exact lowering report/plan binding rather than re-deriving undocumented backend assumptions.

## 15. Acceptance vs provenance/truth

A provenance-complete artifact can still contain false information.

A factually true-looking artifact can have unknown provenance.

Admission keeps these concepts distinct.

`PROVENANCE_COMPLETENESS = PASS` means the required origin/transformation record is complete under the profile; it does not mean the depicted claims are true.

## 16. Nondeterministic providers

If an artifact incorporates nondeterministic AI/provider output, Admission may require disclosure/provenance/checker binding.

The artifact hash itself is exact even if regeneration would not reproduce it.

Profiles can require:

```text
model/provider identity
input/output hashes
seed if meaningful
prompt/config hash
human approval reference
synthetic/modified origin labels
```

without claiming deterministic replay.

## 17. Checker classes for early implementation

Initial checker families:

```text
structural/container
codec/decode-through
media type / stream metadata
duration/timestamps
A/V synchronization
color metadata
hash/provenance completeness
lowering/plan consistency
```

Later:

```text
loudness
caption/accessibility
statistical perceptual quality
broadcast/platform profiles
signature/C2PA verification
human approval/authority
```

## 18. First vertical-slice acceptance vector

For the first two-video-clip + dissolve + audio-bed fixture:

```text
STRUCTURAL              REQUIRED
DECODABILITY            REQUIRED
DURATION_TIMING         REQUIRED
FRAME_INTEGRITY         REQUIRED
AV_SYNC                 REQUIRED
VIDEO_MEDIA_TYPE        REQUIRED
AUDIO_MEDIA_TYPE        REQUIRED
COLOR_PIPELINE          REQUIRED
PROVENANCE_COMPLETENESS REQUIRED
DELIVERY_PROFILE        REQUIRED
LOUDNESS_AUDIO_POLICY   N/A
CAPTIONS_ACCESSIBILITY  N/A
NONDETERMINISM_DISCLOSURE N/A unless provider path introduces it
```

The expected accepted artifact must have zero unreported semantic deviation from its bound OutputIntent/LoweringReport.

## 19. Conformance tests

Required early tests:

1. render succeeds but truncated artifact fails Admission;
2. wrong dimensions reject;
3. wrong audio sample rate/layout reject;
4. intentional output without audio treats audio checks as N/A, not FAIL;
5. A/V drift beyond profile tolerance rejects;
6. color metadata mismatch rejects or becomes indeterminate according to checker evidence, never silently passes;
7. artifact hash change prevents reuse of old acceptance;
8. profile version change requires new acceptance binding;
9. checker ERROR differs from artifact FAIL;
10. INDETERMINATE required check does not become accepted by default;
11. lowering report with forbidden loss blocks profile;
12. provenance-complete synthetic material does not become "truth verified";
13. historical accepted artifact remains historically bound after later project edits;
14. only Admission can construct the accepted record through public kernel API;
15. same artifact can legitimately be accepted under one profile and rejected under another.

## 20. Exit criterion

> A rendered artifact can be independently and reproducibly qualified against a versioned profile, with dimension-level evidence and exact artifact/plan/revision/checker bindings, so "export succeeded" is never confused with "this deliverable is demonstrably ready for its declared purpose."
