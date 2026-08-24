# Media Kernel Core ABI v0

**Status:** Phase 0 passive-schema baseline — frozen for Phase 1  
**Date:** 2026-08-24  
**ABI revision:** 0.2  
**Normative C header:** `docs/spec/media_kernel_abi_v0.h`

## 1. Purpose

The Media Kernel Core ABI defines passive native interoperability contracts shared by State, Transformation, Execution, Admission, Governance, providers, bindings, and applications.

The governing rule is:

> **Shared representation does not imply shared semantic authority.**

A capability reference does not authorize. An acceptance reference does not certify. An object reference does not grant read access. Core ABI carries the reference; the owning kernel interprets it.

## 2. C ABI is not serialization

This distinction is constitutional.

```text
C ABI
    native in-process interoperability
    borrowed pointer/length views
    platform ABI layout

Canonical serialization
    durable project/revision/IR/receipt encoding
    no raw native pointers
    architecture independent
    deterministic/hashable
```

Never persist raw C struct bytes as project State or IR.

## 3. Fixed leaf vs growable descriptor rule

The first v0.1 conformance pass exposed a subtle but serious ABI problem before Phase 1 began.

An append-only descriptor cannot safely embed another append-only descriptor **by value**. If the child later grows, every following field in the parent moves. Likewise, an array of growable structs cannot safely use contiguous old-size elements because old code uses the old stride.

v0.2 therefore freezes this rule:

> **Only fixed leaf values embed by value. Growable/versioned descriptors nest through pointers. Collections of growable/versioned descriptors are arrays of pointers.**

### Fixed leaves

Examples:

```text
mk_abi_version
mk_struct_header
mk_id128
mk_content_hash
mk_media_time
mk_media_rate
mk_ratio
mk_time_range
mk_wall_time
mk_decimal64 / mk_money
mk_string_view / mk_bytes_view
mk_resource_handle
mk_color_descriptor
```

Changing a fixed leaf layout requires a new ABI-generation decision.

### Growable descriptors

Examples:

```text
mk_object_ref
mk_extension
mk_channel_position
mk_media_type
mk_stream_descriptor
mk_diagnostic
mk_dependency_descriptor
mk_provenance_event
mk_resource_budget
mk_effect_descriptor
mk_lowering_loss
mk_kernel_invocation/result
```

Each begins with `mk_struct_header` and may evolve append-only within the ABI generation.

When nested:

```c
const mk_media_type *media_type;
const mk_object_ref *subject;
const mk_resource_budget *resource_budget;
```

not embedded by value.

When collected:

```c
const mk_extension *const *data;
```

not a contiguous `mk_extension[]` whose stride could later change.

This is a major v0.2 correction and the reason v0.1 must not be used as a production baseline.

## 4. Versioned descriptor header

Growable descriptors begin with:

```c
mk_struct_header {
    uint32_t struct_size;
    uint16_t type_version;
    uint16_t flags;
}
```

Reader rules:

1. check `type_version` semantics;
2. verify `struct_size` covers every field to be read;
3. never read beyond `struct_size`;
4. ignore unknown appended trailing fields;
5. follow nested descriptor pointers and independently check the child descriptor's header.

Writer rules:

1. zero initialize the known descriptor;
2. set `struct_size = sizeof(known_type)`;
3. set `type_version`;
4. set reserved fields to zero;
5. keep borrowed pointees alive for the active API's promised lifetime.

## 5. ABI version

The corrected baseline advertises:

```text
MK_ABI_MAJOR = 0
MK_ABI_MINOR = 2
```

Phase 1 treats tested v0.2 fields as append-only. Existing numeric codes and existing field meaning are not casually repurposed.

## 6. Identity and references

`mk_id128` is an opaque 128-bit identity. All-zero is null/absent.

Consumers must not infer:

- type;
- authority;
- time/order;
- storage location;
- UUID semantics;

from the bits themselves.

`mk_object_ref` separates:

```text
logical identity   -> object_id
exact version      -> version_id, when present
exact content      -> content_hash, when present
semantic type      -> namespaced object_type
```

Specialized aliases such as snapshot/revision/artifact/capability/acceptance refs reuse the representation while preserving owner authority.

## 7. Exact time and rates

The ABI carries the already frozen time contract:

```c
mk_media_time { int64_t value; int64_t scale; }
```

with positive scale and normalized exact semantics.

`mk_media_rate` is a positive rational cadence. `mk_ratio` is the same fixed binary shape for other exact ratios such as sample aspect ratio, without conflating the semantic concepts.

`mk_time_range` remains half-open `[start, start + duration)` with nonnegative duration.

Wall-clock time is a separate leaf and does not become semantic media time.

## 8. Borrowed data views

Native strings/bytes use explicit pointer + length views:

```c
mk_string_view
mk_bytes_view
```

Rules:

- UTF-8 strings need not be NUL terminated;
- `(NULL, 0)` is empty;
- nonzero length requires valid storage;
- no implicit ownership transfer;
- Odin slices/strings/maps and C++ STL containers never cross the public boundary directly.

The active function/result-handle ABI will define exact lifetime guarantees.

## 9. Extension model

`mk_extension` is a growable descriptor containing:

```text
namespaced type name
extension version
criticality flags
opaque payload bytes
```

`MK_EXTENSION_FLAG_CRITICAL` means a consumer that does not understand the extension cannot safely claim to understand the containing descriptor.

- unknown critical extension -> fail closed;
- unknown noncritical extension -> may ignore semantically, preserve when round-trip contract promises preservation.

Extension collections use pointer arrays so an individual extension descriptor can grow without changing collection stride.

## 10. MediaType and StreamDescriptor

`mk_media_type` is backend-neutral semantic media typing, not an FFmpeg/Metal/Vulkan/DXGI enum wrapper.

### Video fields

v0.2 includes:

```text
format name
width / height
sample aspect ratio
field order
color descriptor
video flags
```

Color descriptor explicitly carries:

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

Primaries/transfer/matrix use standardized CICP/H.273 code points where a standard code exists. Kernel-owned registries cover concepts that do not map directly to those standardized code points. Provider enum numbering is never silently reused as canonical semantic numbering.

### Audio fields

v0.2 includes:

```text
sample rate
channel count
channel order
sample format name
channel layout name
explicit channel positions[]
audio flags
```

Channel count alone is not a complete audio layout. `mk_channel_position` is a growable descriptor with a namespaced semantic position name, and a custom/ambisonic layout can expose an ordered pointer-array of positions.

### Stream descriptor

A stream binds:

```text
stream identity
pointer to MediaType
nominal MediaRate
time domain
flags/extensions
```

The pointer is deliberate: `MediaType` may grow without moving later fields in `StreamDescriptor`.

Nominal rate does not replace exact VFR timestamps.

## 11. Resource identity and budgets

`mk_resource_handle` is fixed:

```text
store
slot
generation
```

It preserves the concurrency-gate model. It is not a native pointer and must be validated by its owning resource store before use.

Budgets/usage are growable descriptors with a `valid_fields` mask for:

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

Governance enforces; Execution meters; Core ABI only transports.

## 12. Dependencies and invalidation

Dependency descriptors bind pointers to exact object references plus:

```text
dependency kind
strength
optional affected media range
extensions
```

The representation is shared; State owns durable dependency publication. Transformation/Execution/Admission declare their dependencies and owner-specific invalidation behavior.

Initial semantic kinds include:

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

## 13. Provenance

The provenance event envelope carries event identity/type, subject and actor reference pointers, invocation binding, wall time, payload hash, flags, and extensions.

It intentionally does not collapse:

```text
origin
trust
verification
human approval
synthetic status
licensing
truth
```

## 14. Effects and authority references

Effect descriptors carry target pointer, class, idempotency key, reversibility/risk metadata, authority-reference view, input hash, and extensions.

Authority refs are inert until Governance interprets them.

State rollback never implies an already executed external effect did not occur.

## 15. Lowering loss/report

The ABI freezes:

```text
EXACT
EXACT_WITH_INSERTED_CONVERSION
APPROXIMATED
BAKED_LOSS_OF_EDITABILITY
UNSUPPORTED
```

Loss dimensions include:

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
metadata
```

A `mk_lowering_loss` points to its source descriptor rather than embedding a growable `ObjectRef` by value.

A `mk_lowering_report` binds source IR hash, target plan hash, pointer-array loss view, diagnostics, and extensions.

## 16. Invocation/result envelopes

The shared invocation/result envelopes carry:

- ABI version;
- invocation identity;
- caller/target/producer names;
- operation/payload type;
- actor/snapshot refs by pointer;
- resource budget/usage by pointer;
- pointer-array input/output refs;
- borrowed payload;
- diagnostics/dependencies/effects;
- trace/time fields;
- extensions.

Transport/function return status is distinct from the kernel-result semantic status.

Active runtime handles remain opaque until function/lifetime ABI is frozen.

## 17. Compatibility rules

Within the ABI generation, compatible evolution may:

- append fields to a growable descriptor;
- add new optional noncritical extensions;
- add new constants without reusing old values;
- add new payload/operation/object types.

It must not:

- reorder or resize existing fields;
- alter fixed leaf layout;
- change an existing code's meaning;
- embed growable children by value;
- use contiguous arrays of growable descriptors;
- make a previously optional v1 field mandatory without a version transition.

Unknown trailing fields are skipped using `struct_size`. Unknown critical extensions fail closed.

## 18. Native ABI coding rules

Public C ABI avoids:

- `long` / `unsigned long`;
- native C enum storage in struct fields;
- C bitfields;
- compiler-specific booleans;
- `size_t` for semantic contract fields;
- C++ STL/classes;
- Odin slices/strings/maps;
- raw owning pointers;
- packed structs;
- flexible arrays of growable descriptors.

Use fixed-width integers and explicit borrowed pointers/views.

## 19. Corrected conformance evidence

The v0.2 header was compiled/probed under:

```text
C11 / GCC
C++20 / g++
Odin dev-2026-08
```

on a 64-bit Ubuntu System V ABI.

Final corrected results:

- **38 type sizes/alignments identical across C, C++, and Odin**;
- **48 tested field offsets identical**;
- standalone append-only child descriptor growth passed;
- future `MediaType` growth remained readable through an unchanged `StreamDescriptor` pointer field;
- future `ObjectRef` growth remained safe behind a diagnostic subject pointer;
- growable extension collections worked as pointer arrays;
- unknown noncritical extension behavior passed;
- unknown critical extension rejection passed;
- C and C++ compatibility smokes passed;
- ASan/UBSan compatibility smoke passed.

Representative v0.2 layouts:

| Type | Size | Align |
|---|---:|---:|
| `mk_abi_version` | 8 | 4 |
| `mk_struct_header` | 8 | 4 |
| `mk_id128` | 16 | 8 |
| `mk_content_hash` | 40 | 4 |
| `mk_media_time` | 16 | 8 |
| `mk_media_rate` | 16 | 8 |
| `mk_ratio` | 16 | 8 |
| `mk_time_range` | 32 | 8 |
| `mk_resource_handle` | 16 | 8 |
| `mk_color_descriptor` | 32 | 4 |
| `mk_extension` | 48 | 8 |
| `mk_object_ref` | 120 | 8 |
| `mk_channel_position` | 48 | 8 |
| `mk_media_type` | 176 | 8 |
| `mk_stream_descriptor` | 72 | 8 |
| `mk_dependency_descriptor` | 120 | 8 |
| `mk_lowering_loss` | 96 | 8 |
| `mk_lowering_report` | 144 | 8 |
| `mk_kernel_invocation` | 224 | 8 |
| `mk_kernel_result` | 192 | 8 |

Hosted result:

```text
CORE_ABI_LAYOUT_PASS
CORE_ABI_COMPAT_PASS (C)
CORE_ABI_COMPAT_PASS (C++)
CORE_ABI_COMPAT_PASS (ASan/UBSan)
```

This validates same-target native layout. It does not claim raw-binary portability across Windows/ARM64/macOS and does not replace the future serialization contract.

## 20. Remaining ABI work

Separate later work still includes:

1. canonical durable serialization;
2. active function/result-handle lifetime ABI;
3. complete semantic registries for media/color/channel symbols;
4. Windows export/calling-convention validation;
5. ARM64/macOS layout validation;
6. generated binding strategy;
7. 1.0 compatibility commitment after real Declip/provider integration.

These do not block State/IR contract implementation.

## 21. Phase 1 rule

> `docs/spec/media_kernel_abi_v0.h` v0.2 is the tested passive native baseline. Fixed leaves stay fixed; growable descriptors evolve append-only, nest by pointer, and collect by pointer array.
