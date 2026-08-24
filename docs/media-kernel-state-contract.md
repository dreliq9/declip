# Media Kernel State / Revision / Candidate-Delta Contract

**Status:** Phase 0 State contract baseline  
**Date:** 2026-08-24  
**Owner:** Media State Kernel

## 1. Governing question

The State Kernel answers:

> **What exact media/project version exists?**

It owns persistent identity, immutable revisions, snapshots, branch/head publication, transactions, and durable dependency identity. It does not decide creative intent, lowering strategy, provider selection, artifact acceptance, or authorization policy.

## 2. Core rule

> **Committed State is immutable. All change is proposed as a typed candidate delta, verified against an exact base snapshot, and published atomically as a new revision by State.**

No subsystem receives a mutable pointer to canonical project state.

## 3. Identity model

### Project identity

A project has one durable opaque `ProjectId`.

### Durable object identity

Objects such as:

```text
Sequence
Track
Clip
AssetRef
Transition
AudioRoute
OutputIntent
NestedComposition
```

receive opaque durable `ObjectId`s.

Rules:

- IDs do not encode type, authority, ordering, storage location, or timestamps;
- an ID identifies one logical object within its owner scope;
- a durable ID is never silently reused for a different logical object after deletion;
- an object's field values are snapshot-scoped, not mutable properties attached to the ID globally;
- references are resolved against an exact snapshot/revision unless they explicitly bind an external version/hash.

### Execution identity is separate

Executable Media IR nodes, frame handles, resource handles, provider objects, and cache entries use separate computation/resource identities.

A `ClipId` may appear as provenance/source scope in an executable node, but it is not the executable node ID.

## 4. Revision

A revision is an immutable publication record.

Conceptually:

```text
Revision {
    revision_id
    project_id
    parents[]
    snapshot_ref
    snapshot_hash
    candidate_delta_hash
    operation_batch_hash
    dependency_epoch/hash
    provenance_ref
    created_at
    schema_version
}
```

### Revision properties

- immutable after publication;
- exact parent lineage is recorded;
- binds an exact snapshot/content hash;
- binds the candidate/operation batch that produced it when applicable;
- can be addressed independently of a branch head;
- historical meaning is never rewritten because a newer revision supersedes it;
- timestamps are metadata, not ordering authority; parent/sequence relationships define lineage.

### Parent count

Phase 1 needs one-parent revisions for normal editing. The representation should permit multiple parents later for explicit merge revisions without changing the identity model.

## 5. Snapshot

A snapshot is a complete logical view of canonical project State at one revision/projection.

Conceptually:

```text
Snapshot {
    snapshot_id
    project_id
    revision_ref
    schema_version
    object_table / typed roots
    dependency_root
    content_hash
}
```

A snapshot is:

- immutable;
- deterministic under canonical serialization;
- content-hash bound;
- sufficient to resolve all internal durable references in its projection;
- independent of transient executable/provider state.

### Snapshot vs revision

A revision is the **history/publication record**.

A snapshot is the **exact state view** bound to that revision.

Different projections/materializations may exist for one logical revision, but each projection must declare its identity/schema and exact content binding rather than pretending to be the same bytes.

## 6. Branch / head

A branch is a named or identified lineage pointer whose current head is a `RevisionRef`.

Branch-head publication uses compare-and-swap semantics:

```text
expected_head == actual_head
    -> publish new revision atomically

expected_head != actual_head
    -> CONFLICT
```

There is no implicit last-write-wins and no silent auto-rebase.

A higher layer may request rebase/merge as a new explicit operation.

## 7. CandidateDelta

A candidate delta is an immutable proposal to change an exact base State.

Conceptually:

```text
CandidateDelta {
    candidate_id
    project_id
    base_revision_ref
    base_snapshot_ref
    operations[]
    preconditions[]
    declared_dependencies[]
    declared_invalidations[]
    proposer/provenance refs
    candidate_hash
}
```

It is not a revision and does not become canonical merely because it validates.

### Candidate properties

- binds an exact base revision/snapshot;
- can be inspected without commit;
- can be previewed/lowered through a candidate projection without modifying canonical State;
- operations are ordered when order is semantically relevant;
- preconditions are explicit;
- deterministic canonical encoding produces a stable candidate hash;
- rejection leaves the base revision unchanged;
- validation does not imply authority to commit;
- an agent/plugin may have `propose` authority without `commit` authority.

### Candidate lifecycle

Avoid a mutable `accepted=true` flag on the candidate.

Instead, durable events/results reference the immutable candidate:

```text
CandidateValidated(candidate_ref, validation_result)
CandidateRejected(candidate_ref, diagnostics)
RevisionPublished(candidate_ref, revision_ref)
```

State alone creates the revision/publication binding.

## 8. Typed operations

Operations are typed semantic edits, not arbitrary object mutation patches.

Initial Phase 1 operation families:

```text
CreateProject
CreateSequence
AddTrack
InsertClip
TrimClip
MoveClip
SplitClip
RippleDelete
SetTransition
SetAudioRoute
SetOutputIntent
```

Every operation has:

```text
operation_id
operation_type
schema_version
target scope
payload
preconditions
dependency/invalidation declaration
```

The in-memory/Editorial representation is typed. A durable serialization may use a tagged/versioned envelope, but core operations do not become an untyped JSON-patch language.

## 9. Preconditions

A candidate/operation may require conditions such as:

```text
base revision is R
object X exists
object X does not exist
object X has expected content/version
track T has media kind VIDEO
clip C still occupies expected range
asset A still binds expected hash/version
branch head is H
```

Preconditions are checked against the exact candidate base.

Failure is explicit and typed; it is not resolved through best-effort mutation.

## 10. Conflict taxonomy

At minimum State distinguishes:

```text
STALE_BASE
BRANCH_HEAD_CHANGED
OBJECT_NOT_FOUND
OBJECT_ALREADY_EXISTS / ID_COLLISION
OBJECT_VERSION_MISMATCH
PRECONDITION_FAILED
SCHEMA_INCOMPATIBLE
REFERENCE_INVALID
TRANSACTION_CANCELLED
```

Transformation/Editorial verification may report additional semantic errors, but State owns whether publication is conflict-free.

## 11. Candidate application

State applies a candidate into an isolated candidate snapshot/workspace:

```text
base Snapshot
     |
     v
apply typed operations
     |
     v
candidate Snapshot
     |
     +--> structural/reference validation
     +--> Editorial semantic verification
     +--> dependency/invalidation derivation
     +--> optional preview/lowering
```

The base remains immutable throughout.

The candidate snapshot is not addressable as a committed `RevisionRef` before publication. If it needs a temporary reference, the reference type/scope must identify it as candidate/transient rather than masquerading as committed State.

## 12. Commit / publication

Commit is a State-owned atomic transition:

```text
validated CandidateDelta
       +
exact expected branch head
       +
commit authority (interpreted by Governance)
       |
       v
State transaction
       |
       +-- recheck base/preconditions/head
       +-- allocate revision identity
       +-- persist canonical snapshot/content
       +-- persist revision/lineage/dependencies/provenance
       +-- atomically publish branch head
       v
RevisionRef + SnapshotRef
```

If the atomic publication cannot complete, no partial canonical revision is exposed.

## 13. Idempotency

Retries must not accidentally publish duplicate semantically identical commits.

Active State API should support a caller-provided or State-issued idempotency/invocation identity binding:

```text
same idempotency key + same candidate hash
    -> return prior publication result if already committed

same idempotency key + different candidate hash
    -> conflict/error
```

Exact active API shape is frozen with the function ABI, not in the passive Core ABI.

## 14. Operation log and snapshot relationship

The kernel keeps both concepts:

```text
operation/candidate history
    audit/replay/intent lineage

canonical snapshot
    exact materialized State at revision
```

Do not make either one pretend to be the other.

Required property:

> Replaying the canonical operation lineage from its declared base under the same schema rules must reproduce the exact committed snapshot hash for the tested deterministic operation set.

Snapshots may be checkpointed/materialized for efficiency.

## 15. Undo, checkout, and revert

"Undo" is not inverse-mutation magic.

At the State level:

- checkout may move the application's selected revision to an ancestor;
- a branch head may deliberately move according to branch policy;
- editing from an older revision creates a new lineage/branch if necessary;
- a durable linear-history product may instead create an explicit revert candidate whose resulting snapshot matches a prior state.

The UI chooses the user experience. State preserves exact revisions either way.

## 16. Deletion

Deletion removes an object from a new snapshot; it does not retroactively erase that object from historical snapshots.

Rules:

- historical refs to old revisions remain resolvable according to retention policy;
- deleted durable IDs are not silently recycled for unrelated objects;
- external artifact deletion/garbage collection is separate from semantic object deletion;
- destructive storage cleanup must respect referenced historical snapshots/retention policy.

## 17. Internal vs external references

### Internal project reference

A clip-to-track or transition-to-clip relationship may use a durable object ID whose version is implicitly the containing snapshot.

### External/versioned reference

An asset, model, policy, plugin, external artifact, or other independently versioned object should use a Core ABI `ObjectRef`/specialized ref with exact version/content binding where consequential.

A locator/path is retrieval metadata and never authoritative identity.

## 18. Deterministic canonicalization and hashing

Committed State hashing requires a canonical serialization contract.

At minimum:

- object ordering is canonical and independent of hash-map iteration;
- numeric/time values use canonical exact representations;
- default/absent values have one canonical encoding;
- string normalization policy is explicit where strings participate in hashes;
- unknown extensions are preserved according to compatibility rules;
- hash algorithm/version is declared;
- native pointer values, memory addresses, wall-clock creation timestamps, and provider handles never contaminate semantic content hashes unless explicitly part of the semantic object.

## 19. Dependency ownership

State owns one authoritative durable dependency graph for committed objects/revisions.

Other kernels declare dependencies; they do not each invent incompatible durable dependency stores.

For a candidate:

```text
Transformation declares affected/preserved/invalidated semantics
Execution declares plan/artifact dependencies
Admission declares checker/profile dependencies
Governance declares policy/capability references where needed
State publishes durable dependency edges with the committed revision
```

The owner of a derived object decides what an invalidation means; State provides the authoritative dependency/change facts.

## 20. Authority boundary

The State API may carry actor/capability references from Core ABI, but State does not interpret Governance policy independently.

Likewise:

- a validated candidate is not authorization to commit;
- a commit-capable actor is not permission to bypass semantic validation;
- rollback of State cannot erase an external effect that already happened.

## 21. Initial Phase 1 data model

The first persistent implementation should be deliberately small:

```text
Project
Sequence
Track
Clip
AssetRef
Transition
AudioRoute
OutputIntent
Revision
Snapshot
Branch
CandidateDelta
OperationBatch
```

Do not add general-purpose effect graphs, collaboration CRDTs, or every professional metadata schema before the revision model proves itself.

## 22. Phase 1 conformance tests

Required early tests:

1. candidate application cannot mutate base snapshot;
2. rejected candidate leaves every committed hash/ref unchanged;
3. successful commit creates exactly one new immutable revision;
4. stale branch head fails atomically;
5. precondition mismatch fails before publication;
6. replay reproduces exact snapshot hash;
7. deterministic serialization is independent of insertion/map order;
8. deleted IDs are not recycled;
9. candidate and committed refs cannot be confused by type/API;
10. durable IDs and executable node/resource IDs cannot be substituted;
11. idempotent retry cannot double-publish;
12. unknown critical extension fails compatibility checks;
13. historical snapshot remains interpretable after later edits/deletes;
14. branch/check-out from an ancestor preserves prior lineage;
15. multi-parent representation can be added without changing one-parent revision identity semantics.

## 23. First implementation exit criterion

> Starting from revision 0, a deterministic sequence of typed edits can produce inspectable candidate snapshots, reject invalid/stale proposals without canonical mutation, atomically publish valid proposals into immutable revisions, and replay the committed operation lineage to the exact same snapshot/content hashes.
