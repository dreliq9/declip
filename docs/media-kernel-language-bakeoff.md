# Media Kernel Language and ABI Bakeoff

**Status:** Phase 0 decision record  
**Date:** 2026-08-23  
**Decision:** Rust for the Phase 1 semantic core; stable C ABI as the durable public boundary; C/C++ adapters explicitly permitted for native media integrations.

## 1. Decision

The foundational media kernel should begin with:

```text
Applications / bindings
        |
        v
Stable C ABI                    <- constitutional compatibility boundary
        |
        v
Rust semantic core             <- selected Phase 1 implementation
        |
        +-- C APIs directly: FFmpeg/libav, OpenFX-style APIs, OS APIs where suitable
        |
        +-- C/C++ adapter shims: OpenColorIO, C++-only SDKs, vendor integrations
        |
        +-- specialized native/GPU implementations as justified by evidence
```

The implementation-language decision is deliberately weaker than the ABI decision:

> **C ABI is constitutional; Rust is selected for Phase 1 but remains an implementation choice.**

A future subsystem may be written in C++, C, Zig, a GPU language, or another native language without changing the kernel's application contract when evidence warrants it.

Zig is not selected for the semantic core at this stage. It remains a plausible language for small C-facing/platform glue if that produces a concrete advantage.

## 2. Question tested

The bakeoff was designed to answer a kernel-specific question rather than a generic language question:

> Which language best balances semantic/ownership safety, media-ecosystem integration, ABI stability, toolchain maturity, and native performance for a versioned media State/Transformation kernel?

Raw rendering throughput was not the primary selection criterion. The kernel will reuse mature media/GPU implementations and should not spend most of its time performing rational arithmetic or manipulating project objects.

## 3. Equivalent implementation slice

Three implementations were built from the same behavioral specification:

- C++20;
- Rust 1.97.1;
- Zig 0.16.0.

All exported the same C ABI and were driven from the same Python `ctypes` harness.

The slice exercised:

1. exact rational time normalization;
2. exact rational addition/comparison with widened intermediate arithmetic;
3. persistent project state containing assets and clips;
4. source-range and transition semantic validation;
5. candidate trim proposal without mutating committed state;
6. atomic revision commit;
7. stale-base conflict rejection;
8. deterministic FFmpeg lowering;
9. direct `libavformat` C-library interop;
10. a native exact-time arithmetic benchmark as a runtime sanity check.

The C ABI included opaque project handles and operations for exact time, project/revision state, candidate trim/commit, FFmpeg lowering, an FFmpeg version probe, and benchmarking.

The bakeoff intentionally did **not** attempt to implement the complete future media IR, GPU resource graph, color system, admission kernel, or plugin system. The point was to expose the language characteristics that appear early in the kernel's trusted semantic core.

## 4. Test environment

Measured on fresh GitHub-hosted Ubuntu 24.04 runners.

Primary replicated toolchain set:

- g++ 13.3.0;
- rustc 1.97.1;
- cargo 1.97.1;
- Zig 0.16.0;
- libavformat 60.16.100.

Two independent fresh-run measurements were observed. The second run additionally measured an immediate no-change rebuild.

Hosted-runner load varied enough that absolute cold-build and microbenchmark numbers should not be treated as laboratory measurements. Relative behavior was stable.

## 5. Functional result

All three candidates passed the same behavioral and ABI checks.

The following were identical across C++, Rust, and Zig:

- exact-time result for `1001/30000 + 1/48000`: `2671/80000`;
- duplicate asset conflict behavior;
- invalid source-range rejection;
- candidate proposal leaving committed revision unchanged;
- successful commit producing revision 1;
- stale-base proposal conflict;
- `libavformat` version returned through the candidate library;
- deterministic FFmpeg lowering;
- benchmark checksum.

The common lowered command was:

```text
ffmpeg -i a.mp4 -i b.mp4 -filter_complex "[0:v]trim=start=0/1:duration=5/1[v0];[1:v]trim=start=0/1:duration=5/1[v1];[v0][v1]xfade=duration=1/2[x1]" out.mp4
```

This establishes that none of the candidates failed the fundamental C-ABI or FFmpeg-C-interop requirement.

## 6. Measured results

### 6.1 Fresh-run measurements

| Metric | C++ | Rust | Zig |
|---|---:|---:|---:|
| Cold build, run A | 1.30 s | 7.42 s | 44.74 s |
| Cold build, run B | 5.19 s | 18.74 s | 53.70 s |
| Stripped shared library | 35,200 B | 335,096 B | 52,368 B* |
| Native benchmark median, run A (10M iterations) | 0.340 s | 0.460 s | 0.965 s |
| Native benchmark median, run B (10M iterations) | 0.204 s | 0.409 s | 0.951 s |

`*` Zig measured 52,128 B in the first run and 52,368 B in the second; C++ and Rust were stable at the sizes shown.

### 6.2 Immediate no-change rebuild, run B

| Candidate | Time |
|---|---:|
| C++ | 1.15 s |
| Rust | 0.01 s |
| Zig | 0.60 s |

Interpretation:

- C++ had the smallest binary, fastest runtime in this synthetic slice, and lowest cold build cost.
- Rust's larger `cdylib` footprint is real, although still small in the context of a media application and its native dependencies.
- Zig's very large cold-build cost was mostly amortized by its cache: the immediate warm rebuild dropped to 0.60 s. It therefore should not be described as having a universally slow development loop.
- Rust/Cargo's no-change rebuild was effectively free.
- Raw g++ was intentionally invoked without a build cache such as ccache, so its 1.15 s warm figure represents a full recompilation with warm filesystem/header caches rather than an integrated no-op build.
- The arithmetic benchmark is a sanity check only. Rendering, graph scheduling, allocation strategy, cache behavior, and GPU/native-provider boundaries will dominate real workloads.

Implementation line counts were collected during the spike but are excluded from language ranking because formatting density differed substantially: the C++ spike deliberately compressed many functions onto single lines while Rust and Zig were normally formatted.

## 7. Interop findings

### FFmpeg/libav

All three candidates directly called the same system `libavformat` and returned the same version. FFmpeg therefore does not force the semantic core to be C++.

FFmpeg's public libraries are C APIs with versioned library interfaces. The kernel should wrap them behind backend/provider boundaries rather than expose FFmpeg objects through the public media ABI.

### OpenFX

OpenFX reinforces the choice of a C public ABI. Its API is deliberately specified in C to avoid C++ symbol-mangling/ABI problems between hosts and plugins.

The kernel's native plugin model need not be identical to OpenFX, but the same ABI lesson applies.

### OpenColorIO and C++-native libraries

OpenColorIO's public core headers are C++. This is a real integration advantage for a C++ implementation and should not be minimized.

The selected architecture handles this by permitting narrow C/C++ adapter libraries behind the kernel ABI. Rust should not attempt to recreate mature C++ media libraries merely to keep the implementation language uniform.

If C++-only integrations grow to dominate a particular subsystem, that subsystem may itself be implemented in C++ behind the stable C ABI.

## 8. Safety and semantic-model findings

### C++

C++ made the spike extremely compact and integrates naturally with both C and C++ media ecosystems. It is the strongest candidate if direct ecosystem integration and minimum binary/build overhead dominate the problem.

The downside is that ownership, aliasing, thread-safety, mutation discipline, and invalid-state prevention remain architectural conventions enforced through API design, review, sanitizers, smart pointers, and tests.

For a renderer/effects engine this trade could favor C++. For this project, however, the trusted core includes immutable committed state, candidate deltas, snapshots, typed IR, transformation legality, invalidation, and eventually concurrent execution/resource ownership. Those semantics increase the value of compile-time ownership and type constraints.

### Rust

Rust maps most directly onto the desired kernel invariants:

- immutable committed state can be represented naturally;
- candidate/committed/verified states can be distinct types;
- ownership and borrowing constrain accidental aliasing and lifetime bugs;
- concurrency boundaries can carry `Send`/`Sync` constraints;
- enums and newtypes make illegal semantic states harder to express;
- safe semantic crates can forbid `unsafe` entirely.

The spike contained `unsafe` and raw pointers because the public ABI and libavformat are foreign interfaces. That is expected and desirable if quarantined: production architecture should isolate FFI/unsafe code in audited boundary crates while keeping State, IR, Transformation, and Admission logic safe Rust by default.

Rust therefore shifts cost toward a narrower interop boundary instead of requiring ownership correctness to be maintained by convention throughout the semantic core.

### Zig

Zig demonstrated excellent C interoperability, a small binary, explicit control, and a fast cached rebuild after its expensive cold start.

Its principal disadvantage for this kernel is not native capability; it is that the language provides fewer compile-time ownership/concurrency guarantees than Rust for the part of the system where those guarantees are unusually valuable.

The spike also used explicitly bounded arrays for project state rather than depending on changing collection APIs. That was acceptable for the bakeoff but highlights that a production implementation would need to make more allocator/lifetime policy explicit. Zig remains attractive for narrow low-level components but does not currently displace Rust for the semantic center.

## 9. Weighted decision matrix

This matrix is a decision aid, not an objective language ranking. Weights reflect the planned media kernel, particularly its small trusted core and strong semantic invariants.

| Criterion | Weight | C++ | Rust | Zig |
|---|---:|---:|---:|---:|
| Semantic/ownership safety | 30% | 6.5 | 9.5 | 7.5 |
| Native media ecosystem integration | 20% | 10.0 | 8.0 | 7.5 |
| Stable C ABI / foreign-language interop | 15% | 9.0 | 9.0 | 9.5 |
| Toolchain/build maturity | 10% | 9.5 | 9.0 | 7.0 |
| Cross-platform/package outlook | 10% | 9.0 | 9.5 | 8.5 |
| Runtime/footprint | 10% | 10.0 | 7.5 | 8.0 |
| Diagnostics/testing/fuzzing ecosystem | 5% | 8.5 | 9.5 | 7.5 |
| **Weighted score** | **100%** | **85.8** | **88.8** | **79.0** |

The narrow Rust/C++ margin is important. C++ is not a fallback candidate of last resort; it is a strong second choice whose biggest advantage is direct access to the professional media ecosystem. Rust wins because this kernel's differentiating work is expected to live in semantic state/transformation correctness rather than in reinventing rendering libraries.

## 10. Selected architecture

### Semantic core

Use Rust for Phase 1 modules that own semantic state and correctness:

```text
media-core
media-state
media-ir
media-transform
media-admission
planner/resource contracts
```

The exact crate split will follow the final repository design rather than this list mechanically.

### Unsafe/FFI policy

Adopt these rules from the beginning:

1. semantic crates should use `#![forbid(unsafe_code)]` where practical;
2. raw pointers and native-library calls live in dedicated FFI/provider crates;
3. every unsafe block requires a stated safety invariant;
4. no foreign-library object crosses the stable public C ABI as an exposed implementation type;
5. ownership of every opaque ABI handle is explicit and documented;
6. sanitizers/fuzzers/conformance tests exercise the C boundary independently of Rust's internal safety.

### C/C++ adapters

C and C++ are first-class implementation languages for integration layers when they materially reduce risk or complexity:

- OpenColorIO adapter;
- OpenFX host compatibility;
- vendor codec/GPU SDK integration;
- OS/platform-specific media APIs;
- performance-critical code where profiling demonstrates a real problem that cannot be solved cleanly in Rust.

Do not rewrite proven C/C++ media libraries in Rust for ideological consistency.

### Public API

Expose a versioned C ABI with opaque handles, explicit ownership, status/diagnostic results, size-query buffer patterns where needed, and machine-checkable ABI/version negotiation.

Bindings should be generated or implemented above that boundary. Python is first because Declip is the reference client.

## 11. What remains unproven

This bakeoff does **not** close every implementation-language question.

Before a production v1 ABI freeze, run additional conformance/integration work for:

- macOS + Metal/VideoToolbox;
- Windows + D3D/Media Foundation;
- OpenColorIO C++ adapter ergonomics;
- libplacebo/GStreamer integration as those backends become concrete;
- large persistent state and graph traversal;
- multi-threaded scheduler/resource lifetimes;
- fuzzing of serialized state and the C ABI;
- plugin unload/cancellation and asynchronous GPU ownership.

These are re-evaluation checkpoints, not reasons to delay Phase 1.

## 12. Reconsideration triggers

Revisit the Rust-core decision if evidence shows one of the following:

- C/C++ shim code grows into a majority of the kernel implementation rather than remaining provider-boundary code;
- required platform/vendor SDKs cannot be wrapped without unacceptable correctness or maintenance cost;
- profiling identifies an unavoidable Rust/FFI overhead that is material to end-user media performance;
- toolchain/platform support blocks a required production target;
- the chosen C ABI cannot represent a necessary ownership/resource contract cleanly.

A reconsideration should not automatically change the public ABI.

## 13. Phase 0 conclusion

The bakeoff validates the original prior with a narrower, evidence-backed formulation:

> **Start the foundational media kernel's semantic core in Rust. Make the stable C ABI the real long-term commitment. Use C/C++ aggressively at media ecosystem boundaries rather than forcing the whole kernel into one language. Do not select Zig as the semantic core today, while leaving it available for narrow native components.**

This decision is sufficient to proceed with the Phase 1 repository and core-state/IR implementation once the remaining Phase 0 exact-time and canonical-IR decisions are completed.
