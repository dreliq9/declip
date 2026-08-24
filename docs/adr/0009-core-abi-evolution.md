# ADR-0009 — Core ABI uses fixed leaves and pointer-nested growable descriptors

**Status:** Accepted  
**Date:** 2026-08-24

## Decision

Within the native C ABI:

- fixed leaf values may embed by value;
- growable/versioned descriptors begin with `mk_struct_header` and evolve append-only;
- a growable descriptor never embeds another growable descriptor by value;
- collections of growable descriptors are arrays of descriptor pointers;
- raw ABI struct bytes are never durable serialization.

## Rationale

The first v0.1 conformance pass exposed that append-only child growth shifts fields in a parent that embeds the child, while contiguous arrays of growable structs break old element stride. Pointer nesting isolates each descriptor's `struct_size`/version.

## Consequences

- Core ABI baseline is v0.2, not v0.1;
- C/C++/Odin bindings validate each nested descriptor independently;
- borrowed pointer lifetimes are defined later by active function/result-handle contracts;
- fixed-leaf layout changes require an ABI-generation decision.

## Evidence

Corrected conformance matched 38 C/C++/Odin type layouts and 48 field offsets; future `MediaType` and `ObjectRef` growth remained safe behind pointers; extension pointer arrays and ASan/UBSan compatibility passed.

See `../media-kernel-core-abi-v0.md` and `../spec/media_kernel_abi_v0.h`.
