# Media Kernel IR Architecture

**Status:** Phase 0 decision — frozen for Phase 1  
**Date:** 2026-08-24  
**Decision:** typed/versioned Editorial IR lowers through controlled Transformation into an operation-oriented Executable Media IR.

## Decision

The kernel will use **two semantically different IR levels** rather than forcing durable editorial state and transient execution into one generalized operation container.

```text
Persistent Media State
    Project / Sequence / Track / Clip / AssetRef / ...
                    |
                    | immutable snapshot / typed projection
                    v
            Editorial Media IR
       typed, versioned, media-shaped
                    |
          verify / canonicalize
                    |
          controlled Transformation
                    |
        lowering + semantic-loss report
                    v
          Executable Media IR
       op / graph / dialect oriented
                    |
        capability planning / scheduling
                    v
          execution providers
```

The two representations may share passive Core ABI concepts such as exact time, object references, media types, diagnostics, dependencies, provenance, and resource descriptors. They do **not** share object identity semantics or mutation authority.

## 1. Editorial IR

Editorial IR represents **what the media program means**, independent of how it will execute.

Core editorial concepts should be strongly shaped, typed, and versioned, for example:

```text
Project
Sequence
Track
Clip
AssetRef
Gap
Transition
AudioRoute
OutputIntent
NestedComposition
EffectIntent / ExtensionRef
```

These are not arbitrary key/value operation bags.

Required core fields are structural schema members. Semantic constraints still require verification; a typed `Clip` can still reference a missing asset or request a source range outside the asset. The point is not to make every invalid semantic state unrepresentable. The point is to keep the durable representation explicit, inspectable, serializable, evolvable, and media-shaped.

### Editorial identity

Editorial objects carry durable IDs/references associated with State snapshots/revisions. Those IDs survive serialization, replay, branching, and application restarts according to State rules.

Executable nodes must not reuse those identities as if they were the same objects.

## 2. Transformation boundary

Transformation is an explicit semantic boundary, not miscellaneous mutation code.

A transformation pass may:

- verify prerequisites;
- canonicalize equivalent authoring forms;
- infer required media types;
- normalize gaps/track ordering/transition ranges;
- resolve references against an exact snapshot;
- lower higher-level editorial meaning into executable operations;
- insert explicit conversions;
- report unsupported or approximated semantics.

Passes operate through controlled rewrite/candidate-delta mechanisms. They declare analyses/dependencies they preserve or invalidate.

Transformation never silently commits persistent State. State remains the authority that commits revisions.

## 3. Executable Media IR

Executable Media IR represents **how a verified media program can be computed**.

It should use an operation/graph model inspired by compiler IRs:

```text
Decode / Source
SourceRange / Trim
TimeTransform
Scale
ColorConvert
Composite
Transition
AudioDecode
Gain
AudioMix
Encode
Mux
Sink
```

Execution operations may expose versioned dialects, traits, and interfaces such as:

```text
Pure
Deterministic
Replayable
Idempotent
Cacheable
TemporalDependency
ResourceEstimate
MemoryDomain
CapabilityRequirement
Lowering
Invalidation
Provenance
Effect
```

This is where MLIR-like ideas are strongest. The decision does **not** require MLIR itself as a dependency.

### Executable identity

Executable node/value identity is transient computation identity. It may be reconstructed for a plan, optimized away, fused, duplicated, or replaced during lowering.

A durable `ClipId` may be referenced as provenance/source scope, but it is not an executable node ID.

## 4. Semantic-loss contract

Lowering from Editorial IR to Executable IR is always status-bearing.

At minimum the kernel preserves the established taxonomy:

```text
EXACT
EXACT_WITH_INSERTED_CONVERSION
APPROXIMATED
BAKED_LOSS_OF_EDITABILITY
UNSUPPORTED
```

The architecture spike exercised a transition through two target profiles:

```text
target supports transition operation
    -> EXACT

target cannot preserve editable transition,
but can bake equivalent rendered appearance
    -> BAKED_LOSS_OF_EDITABILITY
```

Both editorial representations lowered into the same executable semantic plan and produced the same loss result. This validates that semantic-loss accounting belongs at the transformation/lowering boundary rather than inside one backend compiler.

## 5. Why not one generalized IR for everything?

A generalized operation/dialect representation is technically capable of representing durable editorial state. The Phase 0 spike proved that it could:

- encode the same project;
- validate the same source ranges and transition constraints;
- lower into the same executable plan;
- produce the same semantic digest;
- produce the same semantic-loss results.

But it paid costs that do not buy enough at the durable editorial layer.

In the representative spike:

| Editorial representation | Nonblank LOC | Bytes | Dynamic attribute lookups | Kind-switch sites |
|---|---:|---:|---:|---:|
| Typed media-shaped | **71** | **2,391** | **0** | **0** |
| Generalized op/attribute | 180 | 6,566 | 15 | 1 |

LOC is not the selection criterion, and this small fixture naturally favors direct structs. The stronger evidence is structural:

- a typed core field is visible in the schema and tooling;
- a generic required attribute can simply be absent and must be rediscovered through schema verification;
- generic attribute access introduces repeated lookup/type-conversion machinery into ordinary editorial reads;
- durable serialization becomes a compiler-op encoding rather than a direct description of the user's media program;
- persistent identity and transient operation identity become easier to conflate;
- application bindings become less natural because every consumer must understand the generic op/attribute layer.

The generalized representation's flexibility is valuable where operations are inherently extensible and transformable: **Executable IR and extension/dialect boundaries**.

## 6. Extensibility without turning Editorial IR into an attribute bag

Typed Editorial IR must still evolve without centralizing every future feature forever.

The intended mechanism is versioned extension points, not an untyped escape hatch for all core semantics.

Core objects may expose deliberately scoped extension references, for example:

```text
EffectIntent {
    extension_type_id
    extension_version
    payload_ref / typed payload
}
```

or versioned tagged unions/dialect-owned payloads where justified.

Rules:

- core time/routing/color/reference semantics stay typed;
- unknown extensions are preserved or rejected according to declared compatibility policy;
- extensions declare verification/lowering interfaces;
- extension payloads cannot mutate unrelated canonical state directly;
- unsupported extension semantics appear in `LoweringReport`, never disappear.

## 7. Relationship to edit operations

The **Operation Layer** is separate from Editorial IR.

An edit such as:

```text
TrimClip
MoveClip
SetTransition
RippleDelete
```

is a typed operation/candidate delta that proposes a change to State. It is not the durable representation of the resulting clip.

```text
Operation / CandidateDelta
          |
          | validate
          v
      State commit
          |
          v
new immutable snapshot
          |
          v
   Editorial IR projection
```

This preserves the graph-kernel principle that transformations propose typed deltas while State alone commits canonical versions.

## 8. Verification architecture

### Editorial verification

Editorial IR verification should proceed through stable stages:

1. encoding/version validation;
2. structural/schema validation;
3. exact-time/range validation;
4. object/reference validation;
5. media-type/routing validation;
6. cross-object semantic obligations;
7. extension obligations;
8. target legality only when lowering to a target/profile.

### Executable verification

Executable IR additionally verifies:

- operation/dialect version legality;
- typed input/output ports;
- dependency/DAG legality;
- temporal footprint;
- memory/resource domains;
- capability requirements;
- provider legality;
- declared conversions/losses;
- deterministic/replayable/cache traits where claimed.

## 9. Relationship to OTIO

OpenTimelineIO remains an important interchange and semantic reference, especially for editorial hierarchy, rational timing, nesting, and schema evolution.

It does **not** become the kernel's literal canonical Editorial IR.

The intended relationship is:

```text
OTIO
  <->
OTIO adapter
  <->
Kernel Editorial IR
```

The adapter reports any representation mismatch/loss. Kernel semantics may be richer than OTIO where execution, routing, color, dependencies, admission, or extension contracts require it.

## 10. Relationship to MLIR/compiler research

The prior graph-compiler research remains directly useful, but its concepts are assigned to the layer where they fit:

**Adopt conceptually:**

- typed/versioned operations;
- dialects;
- traits/interfaces;
- analyses separate from transformations;
- controlled rewrite transactions;
- pass management;
- preservation/invalidation declarations;
- target legality profiles;
- explicit lowering loss;
- candidate deltas rather than unrestricted mutation.

**Do not assume:**

- MLIR runtime/library dependency;
- one universal op representation for persistent user state;
- SSA values as durable media-object references.

A later implementation spike may still choose MLIR or another compiler framework for parts of Transformation/Executable IR if its dependency weight and cross-platform embedding costs are justified.

## 11. Phase 0 spike evidence

The Odin architecture spike encoded the same exact-time project twice:

- two 20-second video assets;
- one 60-second audio asset;
- two 5-second video clips;
- exact 12-frame dissolve at 30000/1001 (`1001/2500` seconds);
- an audio bed;
- 1920x1080 output at 30000/1001 with explicit color intent.

Both representations:

- passed the valid fixture;
- rejected an out-of-bounds clip;
- rejected an overlong transition;
- produced semantic hash `7450667640047346483`;
- lowered to the same 11-node executable plan;
- produced full-target plan hash `16726581129033438851` with `EXACT` loss status;
- produced fallback plan hash `11395136983633091391` with `BAKED_LOSS_OF_EDITABILITY`;
- passed AddressSanitizer.

The generalized representation also demonstrated that a required clip-duration attribute could be removed from the serialized/editorial op and was rejected only during attribute-schema verification. The typed representation has a duration field structurally, though invalid duration values still require semantic verification.

Hosted result:

```text
IR_ARCHITECTURE_SPIKE_PASS
ASAN PASS
```

## 12. Frozen architecture rules

Phase 1 should treat these as design rules:

1. Persistent State and canonical Editorial IR use typed/versioned media-shaped schemas.
2. Edit operations/candidate deltas are separate from the resulting durable objects.
3. Editorial IR does not contain backend/compiler objects.
4. Transformation is the only normal route from Editorial IR toward executable representations.
5. Executable Media IR is operation/graph oriented and may use dialects/traits/interfaces.
6. Durable object IDs are distinct from executable node/value IDs.
7. Every lowering returns structured semantic-loss information.
8. Core exact-time, media-type, color, routing, identity, dependency, and provenance concepts stay explicit and typed.
9. Extensibility uses versioned scoped extension contracts rather than converting core objects into generic attribute bags.
10. OTIO is an adapter/interchange target, not the canonical in-memory or serialized kernel IR.
11. MLIR ideas are adopted selectively; MLIR itself remains an implementation option, not an architectural requirement.
12. Transformation passes declare preservation/invalidation and cannot directly commit State.

## Reconsideration triggers

Reconsider this split only if a substantial real media domain cannot be represented without pervasive extension wrappers in the typed Editorial IR, or if maintaining two IR levels demonstrably creates more semantic duplication than it prevents.

Do not collapse them merely because a compiler framework makes one generalized operation container convenient to implement.
