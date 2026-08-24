# Media Kernel Dependency / Invalidation Contract

**Status:** Phase 0 dependency baseline  
**Date:** 2026-08-24  
**Durable owner:** Media State Kernel

## 1. Governing distinction

A dependency edge answers:

> **What exact object/result does this object/result rely on?**

Invalidation answers:

> **Given this exact change, which dependent semantics are no longer valid, and over what scope/range?**

Do not collapse those into one concept.

A dependency can remain true while a specific change is irrelevant to a dependent analysis.

Example:

```text
TranscriptAnalysis depends on Clip

Clip title/color metadata changes
    dependency still exists
    transcript remains valid
```

## 2. One authoritative durable dependency graph

State owns the durable dependency graph for committed objects/results.

Other kernels **declare** dependencies:

- Transformation declares analyses/rewrites/lowering dependencies;
- Execution declares plan/artifact/cache dependencies;
- Admission declares checker/profile/artifact dependencies;
- Governance declares policy/capability references where consequential.

They do not each maintain incompatible canonical dependency graphs.

Transient local execution graphs may exist for scheduling, but they do not replace State's durable dependency facts.

## 3. Edge direction

Canonical direction:

```text
DEPENDENT  --kind-->  DEPENDENCY
```

Example:

```text
Transcript#42 --DERIVED_FROM--> Clip#7@Revision9
RenderPlan#A   --LOWERED_FROM--> EditorialIRHash
Artifact#B     --MATERIALIZED_FROM--> RenderPlan#A
Admission#C    --CHECKED_AGAINST--> DeliveryProfile#P
```

If the dependency changes, the dependent is a candidate for invalidation analysis.

## 4. Exact binding

Consequential edges bind exact versions/content where appropriate.

Do not record only:

```text
Transcript depends on "clip 7"
```

when the actual claim is:

```text
Transcript depends on clip 7 as represented in Snapshot S / content H
```

External/versioned dependencies such as models, color configs, policies, plugins, or source assets bind version/hash through `ObjectRef`.

## 5. Core dependency kinds

Initial semantic kinds:

### `READS`

The dependent directly reads semantic state/content from the dependency.

### `DERIVED_FROM`

The dependent is an analysis/derived semantic product computed from the dependency.

### `MATERIALIZED_FROM`

The dependent is a concrete artifact/materialization produced from the dependency.

### `LOWERED_FROM`

The dependent representation/plan is produced by semantic lowering from the dependency.

### `USES_COLOR_CONFIG`

Color-dependent computation binds an exact color configuration/version.

### `USES_MODEL`

AI/ML analysis/generation binds the exact model/provider configuration that materially affects its result.

### `USES_POLICY`

A result is policy-dependent, such as preview/final planner decisions or acceptance rules.

### `CHECKED_AGAINST`

A verification/admission result binds the exact checker/profile/reference it evaluated against.

Additional namespaced kinds may be defined by owner kernels/extensions.

## 6. Strength

Core ABI supports:

```text
HARD
SOFT
ADVISORY
```

### Hard

If the bound dependency is unavailable/incompatible, the dependent cannot be treated as valid without recomputation/requalification.

### Soft

The dependency affects behavior/quality but owner policy may permit degraded use with an explicit status.

### Advisory

Dependency is contextual/explanatory and not necessarily invalidating.

Strength does not replace owner-specific invalidation logic.

## 7. Dependency is not provenance

Examples:

```text
Artifact DERIVED_FROM Clip
```

is a computation dependency.

```text
Clip originated from CameraFile
```

is provenance/origin information.

They may refer to the same objects but answer different questions.

Likewise dependency does not imply trust, truth, authority, or acceptance.

## 8. Change set

A committed revision should expose a deterministic change set relative to its parent/base.

Conceptually:

```text
ChangeSet {
    old_revision
    new_revision
    changed_objects[]
    created_objects[]
    deleted_objects[]
    changed_semantic_fields/classes[]
    affected_ranges[]
    dependency_edge_changes[]
}
```

Do not require downstream owners to diff arbitrary serialized bytes just to know what semantically changed.

The exact persisted encoding may evolve, but State should provide semantic change facts.

## 9. Invalidation declaration

Transformation/analysis/execution operations declare how a change affects their result class.

At minimum:

```text
PRESERVED
INVALIDATED
CONDITIONALLY_PRESERVED
```

### Preserved

The change is proven irrelevant to the dependent result under the operation's contract.

### Invalidated

The dependent result can no longer be claimed valid for the changed scope.

### Conditionally preserved

Validity depends on a predicate/range mapping/capability condition that must be evaluated.

If a component cannot prove preservation, default to conservative invalidation rather than optimistic reuse.

## 10. Analysis-preservation contract

A transformation/pass declares named analyses it preserves.

Example:

```text
SetTitleColor
    preserves:
        transcript
        scene_detection
        object_tracking
        source_audio_analysis

    invalidates:
        title_composite
        downstream_render_tiles touching title range
```

This is the key to avoiding whole-project recomputation.

Passes cannot simply say "no changes" because the source object identity is the same; they must reason about semantic fields/ranges.

## 11. Range-aware invalidation

Temporal media needs range scope.

An edge/invalidation may include an affected `TimeRange` in a declared time domain.

Example:

```text
Clip trim changes sequence range [10s, 14s)

Transcript tied to source range outside changed source span
    -> may remain preserved

Composite/render cache covering [10s, 14s)
    -> invalidated

Downstream transition whose temporal footprint overlaps boundary
    -> invalidated over expanded footprint
```

## 12. Temporal footprint

Executable/analysis operations declare temporal dependency footprints.

Examples:

```text
Per-frame LUT
    footprint(t) = t

Temporal denoiser
    footprint(t) = [t-N, t+M]

Dissolve
    depends on both source clips over transition range

Audio reverb
    may have history/tail beyond source edit boundary
```

Invalidation expands dirty ranges through these footprints instead of assuming one-input-frame -> one-output-frame.

## 13. Source vs presentation ranges

Dirty-range mapping must name a time domain.

A trim/move can alter:

```text
source-time dependency
sequence/presentation placement
```

independently.

An analysis tied to source samples may remain valid after moving a clip on the timeline, while a sequence composite becomes dirty at the old and new positions.

This is why the multiple-time-domain model matters operationally.

## 14. Object-level invalidation

Some dependencies cannot be safely narrowed to a temporal range.

Examples:

- output color configuration changed;
- model version changed;
- plugin semantics changed;
- channel layout changed;
- global mix bus topology changed.

In those cases invalidate the whole dependent semantic object/result.

Do not fabricate a range just because the data model permits one.

## 15. Deleted dependencies

If a hard dependency is deleted/unresolvable in the new revision:

- dependent becomes stale/invalid according to owner policy;
- historical result remains attached to the historical snapshot where it was valid;
- no result is silently rewritten to point at a replacement object with a similar name/path.

## 16. Dependency graph cycles

Not every semantic relationship belongs in the dependency graph.

For derived-computation/materialization edges, the effective dependency graph should be acyclic for one exact computation snapshot.

If a domain genuinely requires a cycle, its owner must define:

- cycle semantics;
- invalidation fixed-point behavior;
- stopping condition;
- deterministic ordering.

Do not accidentally create cycles by recording ordinary bidirectional UI/navigation relationships as computation dependencies.

Invalidation traversal always tracks visited edge/result identities to avoid infinite propagation.

## 17. Invalidation propagation

Conceptually:

```text
committed ChangeSet
      |
      v
find direct dependents
      |
      v
owner invalidation rule
  preserved / invalid / conditional
      |
      v
produce InvalidationDescriptor(s)
      |
      v
propagate to dependents of invalidated results
```

Propagation works over exact dependency versions, not merely logical names.

## 18. Stale is not delete

Invalidation normally changes lifecycle/validity state, not historical existence.

A stale derived artifact may remain stored for:

- historical revision playback;
- debugging;
- provenance;
- comparison;
- possible reuse if returning to an earlier revision.

Garbage collection is a separate storage/retention decision.

## 19. Candidate-time invalidation

Before commit, a candidate delta can produce a **candidate invalidation set**.

That supports UX/agents such as:

```text
Proposed edit:
    43 cuts

Would preserve:
    transcript
    speaker labels

Would invalidate:
    12.4 s of render cache
    3 transition analyses

Estimated recomputation:
    1.8 s / $0.00
```

Candidate invalidation does not mutate durable cache validity until State commits the revision.

## 20. Cache identity progression

Do not jump immediately to a universal content-addressed cache.

Build in this order:

1. exact dependency graph;
2. semantic change sets;
3. preservation/invalidation rules;
4. dirty-range propagation;
5. stable computation identity;
6. cacheability/determinism traits;
7. content-addressed intermediate storage where safe.

Content equality is useful only after the kernel can say what semantics/dependencies the cached value represents.

## 21. Determinism and cacheability

An operation/result may declare traits such as:

```text
DETERMINISTIC
REPLAYABLE
CACHEABLE
NONDETERMINISTIC
EXTERNALLY_VERSIONED
```

A nondeterministic model result can still be cached for an exact invocation/content binding, but the kernel must not pretend recomputation is guaranteed bit-identical.

Changing model/provider/version/seed/policy is a dependency change where consequential.

## 22. Admission interaction

Acceptance/admission results depend on:

```text
artifact hash
acceptance profile/version
checker versions
assumptions/policies
```

If any hard dependency changes, the acceptance record for the new object cannot be inherited automatically.

The historical acceptance record remains valid for the exact historical artifact/profile binding unless separately revoked/contested.

## 23. Provenance continuity

When a dependent is recomputed after invalidation, provenance records:

```text
old derived result
invalidation/change reason
new invocation
new result
```

Dependency invalidation is not itself a provenance event replacement; the two systems link through exact refs/invocation IDs.

## 24. Example: title color edit

```text
Revision R1
    Clip source
      -> Transcript
      -> SceneAnalysis
      -> Composite
            -> RenderTile A/B/C

Candidate: SetTitleColor

Preserve:
    Clip source identity/content
    Transcript
    SceneAnalysis

Invalidate:
    Title composite over title's active TimeRange
    Render tiles whose temporal/spatial dependency intersects it

Commit R2
    R1 results remain historically valid
    R2 can reuse Transcript + SceneAnalysis
    only dirty composite/render work recomputes
```

## 25. Example: clip moved without source edit

```text
Move Clip C from sequence [10,20) -> [30,40)

source-domain transcript:
    PRESERVED

source-domain object tracking:
    PRESERVED

sequence composite:
    old [10,20) dirty
    new [30,40) dirty

neighbor transition at old/new boundary:
    conditionally invalidate based on overlap/footprint
```

## 26. Example: model upgrade

```text
SceneAnalysis#A --USES_MODEL--> Model v1 hash H1

Project State unchanged
Model configuration changes to v2/H2 for recomputation

Existing Analysis#A:
    remains historical result bound to H1

New requested analysis under v2:
    cannot claim equivalence to A without a declared equivalence policy
```

## 27. Conformance tests

Phase 1/2 must include:

1. title/color-only edit preserves transcript fixture;
2. timeline move preserves source-domain analysis but invalidates old/new sequence ranges;
3. source trim invalidates only intersecting source-dependent analysis ranges where contract permits;
4. temporal filter expands dirty range by declared footprint;
5. global color-config change invalidates color-dependent downstream results;
6. model-version change invalidates/requalifies `USES_MODEL` dependents;
7. deleted hard dependency produces stale dependent;
8. historical revision retains old dependency validity;
9. candidate invalidation does not mutate committed cache state;
10. invalidation traversal terminates under duplicate/shared dependencies;
11. inability to prove preservation defaults conservative;
12. nondeterministic result is not falsely marked replay-identical;
13. Admission record is not inherited across artifact/profile hash change;
14. content-addressed reuse, when introduced, requires matching semantic computation identity, not byte hash alone.

## 28. Exit criterion

> Given a committed or proposed semantic edit, the kernel can determine which exact derived results remain valid, which become stale, and what temporal/object scope must be recomputed—without maintaining multiple contradictory dependency graphs or invalidating the entire project by default.
