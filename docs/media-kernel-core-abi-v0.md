# Media Kernel Core ABI v0

**Status:** Phase 0 passive-schema baseline — frozen for Phase 1  
**Date:** 2026-08-24  
**ABI revision:** 0.1  
**Normative C header:** `docs/spec/media_kernel_abi_v0.h`

## 1. Purpose

The Media Kernel Core ABI defines the shared representation contracts used at boundaries among State, Transformation, Execution, Admission, Governance, providers, bindings, and applications.

It follows the same governing rule established in the earlier Graph Kernel Core ABI research:

> **Shared representation does not imply shared semantic authority.**

The Core ABI may describe an object, reference, budget, effect, dependency, diagnostic, or acceptance reference. It does not decide whether that object is valid, authorized, accepted, semantically legal, or committed.

## 2. Owns

Core ABI v0 owns passive interoperability representations for:

```text
ABI / struct versions
exact media time and rates
wall-clock timestamps
opaque identifiers
content hashes
borrowed string/byte views
version/content-bound object references
extensions
media/stream descriptors
diagnostics
dependencies and invalidation descriptors
provenance envelopes
resource handles, budgets, and usage
effect descriptors
lowering losses/reports
kernel invocation/result envelopes
opaque active-runtime handle declarations
```

It also owns compatibility rules for those representations.

## 3. Does not own

The Core ABI must not:

- commit or mutate persistent State;
- resolve revision conflicts;
- validate Editorial IR semantics;
- perform Transformation passes;
- choose execution providers;
- schedule media work;
- authorize effects;
- enforce capabilities/budgets;
- certify rendered artifacts;
- infer factual truth from provenance;
- define Declip workflows or creative intent.

A `CapabilityRef` in a struct does not authorize anything. An `AcceptanceRef` does not mean an artifact is accepted unless Admission resolves it as such. A valid `ObjectRef` does not imply the caller may read the object.

## 4. C ABI is not the persistence format

This distinction is constitutional.

```text
C ABI
    in-process native interoperability
    pointers/views allowed with explicit lifetime

Serialized kernel state / IR / receipts
    durable canonical encoding
    no raw native pointers
    architecture-independent
    unknown extensions preserved according to schema rules
```

Raw bytes of a C struct must **never** be written as the project/state serialization format.

Reasons include:

- native endianness;
- pointer size;
- platform ABI alignment;
- compiler padding;
- borrowed-memory lifetimes;
- future append-only fields.

A separate canonical serialization contract will encode the same semantic fields.

## 5. ABI versioning

The baseline advertises:

```text
MK_ABI_MAJOR = 0
MK_ABI_MINOR = 1
```

`mk_abi_version` is:

```c
struct {
    uint16_t major;
    uint16_t minor;
    uint32_t reserved;
}
```

### Phase 1 compatibility rule

Once Phase 1 production implementation begins:

- public tested layouts in this baseline are append-only;
- existing field meaning cannot change silently;
- existing numeric constants cannot be repurposed;
- fixed leaf primitive layout cannot change in place;
- a breaking native representation requires an explicit ABI-generation decision rather than an unannounced edit.

The project remains pre-1.0, but "pre-1.0" is not permission to let Declip/provider bindings drift casually.

## 6. Versioned descriptor header

Extensible descriptors begin with:

```c
mk_struct_header {
    uint32_t struct_size;
    uint16_t type_version;
    uint16_t flags;
}
```

`struct_size` supports old/new binary participants safely.

### Reader rules

A reader:

1. verifies the supplied struct is large enough for every field it intends to read;
2. reads no bytes beyond `struct_size`;
3. understands only declared `type_version` semantics;
4. ignores additive trailing fields it does not understand;
5. does not assume zero bytes exist beyond `struct_size`.

### Writer rules

A writer:

1. zero-initializes the known structure;
2. sets `struct_size = sizeof(known_type)`;
3. sets the correct `type_version`;
4. fills only fields it semantically owns;
5. sets reserved fields to zero.

The conformance spike passed an old-reader/new-append-only-struct scenario and rejected a truncated prefix before reading an unavailable field.

## 7. Fixed leaf primitives

Small foundational values intentionally do **not** carry `mk_struct_header`. Their layout is part of the ABI generation.

### Identity

```c
mk_id128 {
    uint64_t high;
    uint64_t low;
}
```

Properties:

- opaque 128-bit identity;
- all-zero is null/absent;
- consumers do not infer type, authority, ordering, storage location, or chronology from bits;
- owner kernels define lifecycle.

The ABI does not require UUID semantics even if a UUID-compatible generator is used initially.

### Content hash

```c
mk_content_hash {
    uint32_t algorithm;
    uint32_t byte_count;
    uint8_t  bytes[32];
}
```

v0 reserves a 256-bit payload. Algorithm codes are registry-controlled and must not be guessed from length.

### Exact media time

Frozen separately in `docs/media-kernel-exact-time.md`:

```c
mk_media_time {
    int64_t value;
    int64_t scale;  // > 0
}
```

### Media rate

```c
mk_media_rate {
    int64_t numerator;
    int64_t denominator;
}
```

A valid rate has positive numerator/denominator.

### Time range

```c
mk_time_range {
    mk_media_time start;
    mk_media_time duration;
}
```

The semantic contract remains half-open `[start, start + duration)` and rejects negative duration.

### Wall time

```c
mk_wall_time {
    int64_t unix_seconds;
    uint32_t nanoseconds;
    uint32_t flags;
}
```

Wall time is deliberately distinct from semantic media time.

### Resource handle

```c
mk_resource_handle {
    uint64_t store;
    uint32_t slot;
    uint32_t generation;
}
```

This preserves the resource-generation model validated in the final language/concurrency gate. A handle is not a pointer and cannot be assumed live without asking its owning resource store.

## 8. Borrowed views and ownership

C ABI strings/bytes are explicit views:

```c
mk_string_view { const char *data; uint64_t size; }
mk_bytes_view  { const uint8_t *data; uint64_t size; }
```

Rules:

- UTF-8 string views need not be NUL terminated;
- `(NULL, 0)` is the canonical empty view;
- a nonzero size requires a valid pointer for the declared lifetime;
- views never transfer ownership implicitly;
- active API contracts must state whether views are caller-owned, borrowed library-owned, or attached to an opaque result handle;
- Odin slices, C++ strings/vectors, and other language-specific containers never cross the public C boundary directly.

The active function/lifetime API is frozen separately; v0 only establishes these passive shapes.

## 9. Extension model

Versioned descriptors may expose `mk_extension_view` containing `mk_extension` records:

```text
type_name
extension_version
extension_flags
payload
```

Extension type names use controlled namespaced UTF-8 identifiers such as:

```text
media.core.*
media.state.*
media.transform.*
media.execution.*
media.admission.*
media.governance.*
media.provider.ffmpeg.*
```

### Criticality

`MK_EXTENSION_FLAG_CRITICAL` means:

> A consumer that does not understand this extension cannot safely claim to understand the containing object.

Unknown critical extensions therefore fail closed.

Unknown noncritical extensions may be semantically ignored by a consumer that does not understand them, but durable serializers/transcoders should preserve them where their contract promises round-trip preservation.

The compatibility smoke verified both behaviors.

## 10. Object references

`mk_object_ref` carries:

```text
object_type
object_id
optional exact version_id
optional content_hash
ref_flags
extensions
```

This separates three questions:

```text
What logical object?      object_id
Which durable version?    version_id
Which exact bytes/state?  content_hash
```

### Binding rules

- durable versioned State references should bind a version when exact revision meaning matters;
- derived/render/admission/provenance relationships should bind a content hash when exact content matters;
- references may carry both;
- absence is explicit through `ref_flags`;
- resolution never implies authorization;
- object type names are namespaced semantic types, not native-language class names.

Specialized aliases such as `mk_snapshot_ref`, `mk_revision_ref`, `mk_artifact_ref`, `mk_capability_ref`, and `mk_acceptance_ref` preserve the common representation while owner kernels preserve semantic authority.

## 11. Media and stream descriptors

### Media type

`mk_media_type` is deliberately backend-neutral.

Core fields include:

```text
kind
format_name
video dimensions
color descriptor
sample rate
channel count
sample format name
channel layout name
extensions
```

Important rule:

> `AVPixelFormat`, Metal texture formats, Vulkan formats, DXGI formats, codec IDs, and provider-native structs do not become canonical `MediaType` values merely because an adapter consumes them.

Namespaced semantic format/layout names are used at the ABI level. Provider adapters perform explicit mapping/lowering.

The flat v0 structure intentionally leaves irrelevant fields zero for a media kind. This keeps the C layout predictable without forcing a C union into every language binding. Typed Odin/editorial wrappers may present a more ergonomic sum type internally.

### Color

The ABI reserves explicit fields for:

```text
primaries
transfer
matrix
range
chroma location
alpha mode
bit depth
flags
```

The numeric semantic registry for those fields is part of the `MediaType` contract work and must not silently inherit one backend's private enum numbering.

### Stream descriptor

A stream descriptor binds:

```text
stream identity
MediaType
nominal MediaRate
time domain
flags/extensions
```

Nominal rate does not replace exact VFR sample timestamps.

## 12. Diagnostics

`mk_diagnostic` carries:

- opaque diagnostic identity;
- severity;
- namespaced code;
- human-readable UTF-8 message;
- optional subject reference;
- optional media range/location flags;
- extensions.

Diagnostic codes must be stable and machine-readable. Messages are explanatory text, not the API contract.

## 13. Dependency and invalidation descriptors

The Core ABI defines representations, not invalidation policy.

`mk_dependency_descriptor` binds:

```text
dependent ref
dependency ref
dependency kind
strength
optional affected media range
extensions
```

Expected namespaced/core kinds include the already established concepts:

```text
READS
DERIVED_FROM
MATERIALIZED_FROM
LOWERED_FROM
USES_COLOR_CONFIG
USES_MODEL
USES_POLICY
CHECKED_AGAINST
```

State owns durable dependency publication. Transformation/Execution/Admission declare their dependencies. Each owner decides what a dependency change means for its own cached/derived objects.

`mk_invalidation_descriptor` is an impact/change representation, not permission for Core ABI to delete caches or revoke acceptance.

## 14. Provenance envelope

`mk_provenance_event` carries identity, event type, subject, actor reference, invocation binding, wall time, payload hash, flags, and extensions.

The envelope does not collapse:

```text
origin
trust
verification
human approval
synthetic status
licensing
factual truth
```

Those remain separate owner/domain concepts.

## 15. Resources

Resource budgets and usage use integer counters and an exact base-10 money representation.

v0 includes fields for:

```text
wall time
CPU time
GPU time
RAM
VRAM
storage
network
model calls
tool calls
external cost
```

A `valid_fields` bitmask distinguishes "unset" from a legitimate zero budget/usage value.

Governance enforces budgets. Execution meters usage. Transformation or planning may estimate. Core ABI only carries the values.

## 16. Effects

`mk_effect_descriptor` carries:

```text
effect identity
effect class
target reference
idempotency key
reversibility class
risk class
authority references
input hash
extensions
```

Authority references are inert references until Governance interprets them.

Rollback of State cannot imply that an already-executed external effect never occurred.

## 17. Lowering loss/report

The ABI freezes the established top-level lowering statuses:

```text
EXACT
EXACT_WITH_INSERTED_CONVERSION
APPROXIMATED
BAKED_LOSS_OF_EDITABILITY
UNSUPPORTED
```

`mk_lowering_loss` also carries a loss-dimension bitset covering at least:

```text
precision
uncertainty
provenance detail
reversibility
editability
time
color
audio
media type
```

Each loss binds its source reference, target operation, stable code, explanation, and extensions.

`mk_lowering_report` binds source IR hash, target plan hash, losses, and diagnostics.

This makes semantic loss a first-class result of Transformation rather than backend prose.

## 18. Invocation/result envelopes

`mk_kernel_invocation` and `mk_kernel_result` provide a common passive envelope for cross-kernel/native-boundary calls.

They include:

- ABI version;
- invocation identity;
- caller/producer/target names;
- operation/payload type;
- actor and snapshot references;
- resource budget/usage;
- input/output references;
- payload views;
- diagnostics/dependencies/effects;
- trace/time fields;
- extensions.

A successful C function return does not mean a successful kernel decision. Transport status and `mk_kernel_result.status` are separate concepts.

Active runtime objects remain opaque (`mk_kernel_handle`, `mk_result_handle`) until the function/lifetime ABI is frozen.

## 19. Compatibility rules

### Same ABI generation

Compatible additive evolution may:

- append fields to versioned descriptors;
- add new optional noncritical extensions;
- add new symbolic/numeric constants without repurposing old values;
- add new operation/payload types;
- add new owner-defined reference types.

It must not:

- reorder existing fields;
- change existing field widths/signedness;
- change fixed leaf layouts;
- change the meaning of an existing code;
- reinterpret reserved bits without an explicit version contract;
- make a previously optional field mandatory without a type/version transition.

### Unknown data

- unknown trailing fields: old readers ignore safely using `struct_size`;
- unknown noncritical extension: ignore semantically and preserve where promised;
- unknown critical extension: fail closed;
- unknown owner-defined payload type: target kernel decides compatibility, not Core ABI.

## 20. Native ABI coding rules

Public C-facing ABI must avoid:

- `long` / `unsigned long`;
- `size_t` in persisted semantic fields;
- C bitfields;
- native C enum storage as struct fields;
- `_Bool`/compiler-specific boolean layouts;
- flexible array members in shared descriptors;
- C++ STL/types;
- Odin slices/strings/maps as exported fields;
- packed structs unless a separately justified wire-format contract requires them;
- raw owning pointers in passive descriptors.

Use fixed-width integer fields and explicit pointer+length borrowed views.

## 21. Conformance evidence

The tested research header was compiled and probed as:

```text
C11 / GCC
C++20 / g++
Odin dev-2026-08
```

On the 64-bit Ubuntu runner:

- **26 tested type layouts matched exactly across C, C++, and Odin**;
- **32 tested field offsets matched exactly**;
- C and C++ append-only compatibility smokes passed;
- unknown noncritical extension behavior passed;
- unknown critical extension rejection passed;
- ASan/UBSan compatibility smoke passed.

Representative frozen layouts:

| Type | Size | Align |
|---|---:|---:|
| `mk_abi_version` | 8 | 4 |
| `mk_struct_header` | 8 | 4 |
| `mk_id128` | 16 | 8 |
| `mk_content_hash` | 40 | 4 |
| `mk_media_time` | 16 | 8 |
| `mk_media_rate` | 16 | 8 |
| `mk_time_range` | 32 | 8 |
| `mk_wall_time` | 16 | 8 |
| `mk_resource_handle` | 16 | 8 |
| `mk_extension` | 48 | 8 |
| `mk_object_ref` | 120 | 8 |
| `mk_media_type` | 128 | 8 |
| `mk_stream_descriptor` | 192 | 8 |
| `mk_resource_budget` | 128 | 8 |
| `mk_lowering_loss` | 208 | 8 |
| `mk_lowering_report` | 144 | 8 |

Hosted result:

```text
CORE_ABI_LAYOUT_PASS
CORE_ABI_COMPAT_PASS  (C)
CORE_ABI_COMPAT_PASS  (C++)
CORE_ABI_COMPAT_PASS  (ASan/UBSan)
```

This proves same-target C/C++/Odin layout compatibility on the tested 64-bit System V ABI. It does **not** make raw struct bytes portable serialization and does not replace later ARM64/Windows ABI conformance runs.

## 22. Remaining ABI work

The passive ABI v0 baseline is now sufficient to unblock Phase 0 domain contracts.

Still separate:

1. canonical durable serialization/wire format;
2. active function and result-handle lifetime ABI;
3. exact registry values for media/color/format symbols;
4. Windows calling/export macros and ABI validation;
5. ARM64/macOS ABI validation;
6. generated binding strategy;
7. 1.0 compatibility commitment after real Declip/provider integration exercises v0.

These are not reasons to delay State/IR contract work, but must be completed before claiming a mature external binary SDK.

## 23. Phase 1 rule

> Treat `docs/spec/media_kernel_abi_v0.h` as the tested passive C layout baseline. Add through append-only/versioned mechanisms; do not casually edit existing tested fields once Phase 1 begins.
