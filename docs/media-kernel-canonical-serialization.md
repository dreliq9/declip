# Media Kernel Canonical Serialization v0

**Status:** Phase 0 persistence/hash baseline  
**Date:** 2026-08-24  
**Format:** deterministic CBOR profile based on RFC 8949 core deterministic encoding

## 1. Purpose

The canonical serialization answers:

> **What exact architecture-independent bytes represent this semantic kernel object for persistence, hashing, replay, and cross-language interchange?**

It is deliberately separate from the native C ABI.

```text
C ABI
    native process boundary
    pointers/views/alignment

Canonical serialization
    persistent bytes
    no native pointers
    deterministic
    architecture independent
    content-hashable
```

## 2. Why CBOR

The kernel needs:

- exact integers and byte strings;
- compact maps/arrays;
- generic decoding without native schema layout;
- unknown-field preservation;
- deterministic encoding rules suitable for hashing;
- straightforward implementations in Odin, C/C++, Python, Swift, Java/Kotlin, etc.

RFC 8949 defines core deterministic CBOR restrictions including preferred shortest encodings, definite-length items, and deterministic map-key ordering. The Media Kernel profile further narrows the data model so semantic serialization has one representation.

## 3. Core deterministic requirements

All canonical kernel bytes MUST:

1. use RFC 8949 core deterministic encoding;
2. use preferred/shortest integer and length encodings;
3. use definite-length arrays/maps/strings/byte strings;
4. sort map keys according to deterministic encoded-byte ordering;
5. reject duplicate map keys;
6. use one schema-defined representation for each semantic value;
7. contain no native pointer/address/padding bytes;
8. contain no non-semantic process-local handles.

A decoder may accept a broader valid CBOR input for import, but any object admitted into canonical State is normalized/re-encoded into this profile before content hashing.

## 4. Floating point policy

Canonical State, Editorial IR, revision records, dependency records, lowering reports, and Admission records use **no CBOR floating-point numbers in v0 semantic fields** unless a future schema explicitly opts in with a deterministic numeric contract.

Use:

```text
integer
MediaTime [value, scale]
MediaRate [numerator, denominator]
Ratio [numerator, denominator]
Decimal64 [coefficient, exponent10]
```

This prevents binary-float choices/NaN/signed-zero/width differences from entering semantic hashes.

Provider telemetry that is inherently floating-point must either:

- use an explicitly versioned non-semantic diagnostic payload; or
- define a canonical decimal/integer representation before becoming a hashed semantic field.

## 5. Map-key profile

Core schema maps use **unsigned integer field IDs only**.

Reasons:

- compact;
- stable across language bindings;
- deterministic ordering straightforward;
- renaming an implementation field does not change persistence;
- unknown numeric fields can be preserved generically.

Keys are never reused with a different meaning inside the same schema lineage.

## 6. Record envelope

Canonical typed records reserve:

```text
0 -> type name (namespaced UTF-8 text)
1 -> schema version (unsigned integer)
```

Schema fields begin at key 2 unless a type-specific specification reserves additional envelope keys.

Example conceptual record:

```text
{
  0: "media.editorial.clip",
  1: 1,
  2: <clip-id>,
  3: <asset-ref>,
  4: <timeline-start>,
  5: <source-in>,
  6: <duration>
}
```

Type names are controlled semantic identifiers, not Odin/Python/C class names.

## 7. Required/optional/default fields

For each schema version:

- required fields are always encoded;
- optional absent fields are omitted, not encoded as `null`, unless the schema explicitly distinguishes absent from null;
- a field with a schema-defined default has one rule: **omit when equal to the default** unless the schema explicitly requires materialization;
- encoders cannot choose arbitrarily between omitted/default-present forms.

This prevents two byte representations for the same semantic object.

## 8. IDs

`mk_id128` serializes as a 16-byte CBOR byte string:

```text
high 64 bits, big-endian
low  64 bits, big-endian
```

All-zero retains the ABI's null/absent meaning where a schema permits a null ID.

Do not serialize IDs as implementation-specific UUID strings in canonical State.

Human/UI adapters may display them differently.

## 9. Content hashes

v0 content hash algorithm registry begins with:

```text
1 -> SHA-256
```

Canonical representation:

```text
[algorithm_id, digest_bytes]
```

For SHA-256:

```text
[1, bstr(32)]
```

The hash of a semantic object is SHA-256 over the exact canonical CBOR bytes defined for that object's hash domain.

Do not hash:

- native C struct memory;
- pretty JSON;
- dictionary iteration order;
- process-local pointer values.

Future algorithms can be added without changing old content-hash meaning.

## 10. Exact time/rate/ratio encodings

### MediaTime

```text
[value, scale]
```

with already-frozen constraints:

- signed i64 value;
- positive i64 scale;
- GCD reduced;
- zero `0/1`.

### MediaRate / Ratio

```text
[numerator, denominator]
```

with schema-specific positivity constraints.

### TimeRange

```text
[start_time, duration_time]
```

and nonnegative duration.

No tagged decimal/fraction alternative is accepted as canonical for these core values.

## 11. Wall time

Canonical wall time is:

```text
[unix_seconds, nanoseconds, flags]
```

where nanoseconds is `0..999999999`.

Do not use ISO-8601 text as the canonical hash representation.

## 12. Strings

Strings are UTF-8 CBOR text strings.

### Registry/type identifiers

Controlled kernel names are restricted to a canonical ASCII-compatible naming grammar defined by their registry, e.g. lowercase namespaced identifiers.

### User-authored text

User text is preserved as its exact Unicode scalar sequence after valid UTF-8 decoding. The kernel does **not** silently Unicode-normalize creative text merely to make hashes match.

If a particular semantic identifier requires NFC/case normalization, that field's schema defines it explicitly.

## 13. Collections

### Ordered collections

Timeline track order, operation order, channel order, and other semantic sequences encode as arrays in semantic order.

### Sets/unordered collections

A schema that defines a logical set must define a canonical sort key.

Examples:

```text
object set -> ascending 16-byte ObjectId
extension set -> type name then version then canonical payload hash
```

Do not serialize hash-map iteration order.

### Object tables

State object tables encode as arrays sorted by durable ObjectId unless a more specific schema defines another canonical order.

## 14. Unknown fields

A compatible decoder of a known type may encounter unknown field IDs.

Rules:

- generic CBOR value must remain valid;
- unknown fields are retained when the object is round-tripped by a compatibility-preserving State/adapter path;
- known-field semantic operations do not invent meaning for unknown fields;
- a schema may mark an extension/field critical through its typed extension contract; unknown critical semantics fail closed.

Canonical re-encoding sorts the preserved unknown keys with all other map keys.

## 15. Extensions

Core ABI extension payloads are opaque bytes at the ABI boundary.

A persistent extension defines its own canonical payload contract.

Recommended default for kernel-owned extensions:

```text
deterministic CBOR under this same profile
```

The containing object stores:

```text
extension type
version
criticality
canonical payload bytes/hash according to extension schema
```

Unknown noncritical extension payload bytes can be preserved exactly.

## 16. Snapshot hashing

Snapshot semantic hash excludes incidental runtime metadata.

A canonical Snapshot hash domain includes at least:

```text
snapshot schema/version
project identity
canonical root/object table
canonical durable dependency state included by snapshot schema
critical semantic extensions
```

It excludes unless explicitly semantic:

```text
memory addresses
file handles
local cache paths
provider sessions
UI selection state
wall-clock save time
render progress
```

Wall-clock creation time may live in the Revision record without contaminating the semantic Snapshot hash.

## 17. Revision hashing

Revision identity and semantic snapshot hash are separate.

A revision record may bind:

```text
revision ID
project ID
parent revision refs
snapshot hash
candidate/operation batch hash
provenance/dependency refs
schema version
created-at metadata
```

The exact revision-record hash domain is defined by the State serialization schema. Do not use timestamp order as lineage authority.

## 18. CandidateDelta serialization

Candidates serialize deterministically from:

```text
candidate ID
project ID
exact base revision/snapshot refs
ordered operations
preconditions
dependency/invalidation declarations
proposer/provenance bindings
schema version
```

A candidate hash changes if a consequential operation/precondition changes.

Human comments/UI descriptions may be excluded from semantic candidate hashing when the schema explicitly classifies them as non-semantic metadata.

## 19. Editorial IR serialization

Typed Editorial IR records use the same record envelope and exact-time primitives.

Durable object identity is explicit.

Executable node IDs/provider handles never appear as replacements for editorial object identity.

## 20. Executable IR / plan serialization

Executable plans may also use deterministic CBOR for plan hashing/receipts.

Their schema is separate because executable node identity/ordering/normalization rules differ from persistent Editorial IR.

Plan hashing must be stable for semantically/canonically equivalent plans after the defined canonicalization pass, not dependent on memory allocation order.

## 21. Lowering / Admission / receipts

`LoweringReport`, execution receipts, checker results, and `AcceptanceRecord` all use deterministic versioned schemas and exact content/ref bindings.

This enables:

```text
source IR hash
    -> target plan hash
        -> artifact hash
            -> acceptance record
```

without any layer depending on Python/C/Odin object-memory identity.

## 22. Decoder validity levels

Keep three levels separate:

```text
CBOR well-formed
    syntax can be parsed

CBOR/profile valid
    deterministic profile, no duplicate keys, allowed primitive forms

schema/semantic valid
    type/version/required fields/invariants/reference rules pass
```

A well-formed CBOR document is not automatically valid kernel State.

## 23. Security constraints

Decoders must enforce configurable limits before allocation/recursion:

- maximum nesting depth;
- maximum collection counts;
- maximum string/byte lengths;
- maximum unknown-extension payload;
- duplicate map-key rejection;
- integer range constraints before narrowing to ABI/Odin types.

Canonical decoding is an input boundary and must not trust advertised lengths blindly.

## 24. File/container framing

Canonical semantic objects are CBOR items. A future project/bundle file format may add outer framing for:

```text
magic/version
indexing
multiple objects
compression
signatures
attachments/assets
```

Outer framing is not part of an individual semantic object's content hash unless its schema explicitly says so.

Do not prematurely make the project bundle format the same thing as one Snapshot CBOR item.

## 25. Phase 1 implementation rule

The first State implementation should provide one canonical encoder/decoder module used by:

```text
snapshot persistence
candidate hashes
revision records
operation replay fixtures
Editorial IR persistence
```

No subsystem gets a second independent "equivalent" JSON hash serializer.

A human-readable diagnostic JSON projection is allowed but is not canonical identity.

## 26. Conformance requirements

Before State persistence is trusted:

1. same object constructed in different insertion order -> identical bytes/hash;
2. Python/Odin reference encoders -> identical bytes for golden fixtures;
3. invalid non-reduced `MediaTime` rejected or normalized before canonical encode;
4. no float accepted in v0 semantic schema;
5. duplicate map key rejected;
6. indefinite-length CBOR rejected for canonical State;
7. unknown optional field round-trips;
8. unknown critical extension fails semantic compatibility;
9. object table ordering independent of map insertion;
10. one-byte change in semantic field changes SHA-256 content hash;
11. excluded non-semantic metadata does not change Snapshot semantic hash;
12. decoder bounds prevent pathological nesting/allocation;
13. ARM64/x86-64 produce identical canonical bytes.

## 27. Exit criterion

> The same semantic State/IR object produces the same canonical bytes and SHA-256 content hash across supported languages and architectures, independent of native struct layout, map iteration order, or process-local state.
