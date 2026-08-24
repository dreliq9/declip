# Media Kernel Language and ABI Bakeoff

**Status:** Phase 0 decision record  
**Date:** 2026-08-23  
**Decision:** Rust for the Phase 1 semantic core; stable C ABI as the durable public boundary; C/C++ adapters explicitly permitted for native media integrations; Odin retained as a priority candidate for a later execution-runtime bakeoff.

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
        |
        +-- Odin execution/runtime provider is explicitly eligible for later bakeoff
```

The implementation-language decision is deliberately weaker than the ABI decision:

> **C ABI is constitutional; Rust is selected for Phase 1 but remains an implementation choice.**

A future subsystem may be written in C++, C, Odin, Zig, a GPU language, or another native language without changing the kernel's application contract when evidence warrants it.

Zig is not selected for the semantic core at this stage. Odin also does not displace Rust for the semantic core, but its measured build speed, binary footprint, direct C interop, and data-oriented language model make it materially more interesting than Zig for a future frame/resource/execution subsystem. That question is deliberately left open until an execution-specific bakeoff exists.

## 2. Question tested

The bakeoff was designed to answer a kernel-specific question rather than a generic language question:

> Which language best balances semantic/ownership safety, media-ecosystem integration, ABI stability, toolchain maturity, and native performance for a versioned media State/Transformation kernel?

Raw rendering throughput was not the primary selection criterion. The kernel will reuse mature media/GPU implementations and should not spend most of its time performing rational arithmetic or manipulating project objects.

The addition of Odin created a second question:

> Does Odin's low-level/data-oriented fit justify changing the semantic-core decision, or at least justify treating execution as a separately selectable implementation domain?

This bakeoff answers the first half. It does **not** claim to benchmark a real GPU/frame scheduler, so the execution-language question remains an explicit later experiment rather than an inference from a semantic microkernel.

## 3. Equivalent implementation slice

Four implementations were built from the same behavioral specification:

- C++20;
- Rust 1.97.1;
- Zig 0.16.0;
- Odin `dev-2026-08-nightly:902106f`.

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

The bakeoff intentionally did **not** attempt to implement the complete future media IR, GPU resource graph, color system, admission kernel, plugin system, or production execution scheduler. The point was to expose the language characteristics that appear early in the kernel's trusted semantic core.

## 4. Test environment

Measured on fresh GitHub-hosted Ubuntu 24.04 runners.

Replicated toolchain set for the four-way run:

- g++ 13.3.0;
- rustc 1.97.1;
- cargo 1.97.1;
- Zig 0.16.0;
- Odin `dev-2026-08-nightly:902106f`;
- libavformat 60.16.100.

The original three-language experiment was measured twice on fresh runners. Odin was then added and the four-language experiment was also run twice on fresh hosted runners.

Hosted-runner load varied enough that absolute cold-build and microbenchmark numbers should not be treated as laboratory measurements. Relative behavior was stable, particularly Odin's build/size profile and broad performance position.

## 5. Functional result

All four candidates passed the same behavioral and ABI checks.

The following were identical across C++, Rust, Zig, and Odin:

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

### 6.1 Original three-way fresh-run measurements

| Metric | C++ | Rust | Zig |
|---|---:|---:|---:|
| Cold build, run A | 1.30 s | 7.42 s | 44.74 s |
| Cold build, run B | 5.19 s | 18.74 s | 53.70 s |
| Stripped shared library | 35,200 B | 335,096 B | 52,368 B* |
| Native benchmark median, run A (10M iterations) | 0.340 s | 0.460 s | 0.965 s |
| Native benchmark median, run B (10M iterations) | 0.204 s | 0.409 s | 0.951 s |

`*` Zig measured 52,128 B in the first run and 52,368 B in the second; C++ and Rust were stable at the sizes shown.

### 6.2 Four-way run including Odin

Two independent fresh-run measurements were taken after Odin was added.

| Metric | C++ | Rust | Zig | Odin |
|---|---:|---:|---:|---:|
| Cold build, four-way run A | 3.29 s | 18.40 s | 51.39 s | **3.27 s** |
| Cold build, four-way run B | 3.09 s | 9.63 s | 49.39 s | **3.08 s** |
| Warm no-change rebuild, run A | 1.12 s | **0.02 s** | 0.58 s | 0.61 s |
| Warm no-change rebuild, run B | 1.08 s | **0.01 s** | 0.57 s | 0.58 s |
| Stripped shared library | 35,200 B | 335,096 B | 52,368 B | **34,720 B** |
| Native benchmark median, run A (10M) | **0.192 s** | 0.462 s | 0.975 s | 0.555 s |
| Native benchmark median, run B (10M) | **0.203 s** | 0.409 s | 0.947 s | 0.526 s |

Interpretation:

- C++ remained the fastest candidate in this synthetic exact-time workload.
- Rust remained comfortably native-speed and had the strongest no-change Cargo rebuild behavior, but its `cdylib` was much larger than the other three tiny spikes.
- Zig retained the highest cold-build cost by a wide margin, although its cached rebuild remained fast.
- Odin's cold build was essentially tied with C++ in both fresh runs and its stripped shared library was slightly smaller than the C++ spike.
- Odin's arithmetic microbenchmark was slower than Rust in both four-way runs, but substantially faster than Zig. This is not a rendering benchmark and should not be extrapolated into a GPU-performance claim.
- Odin's measurements were stable across the two fresh runs: 3.27/3.08 s cold build, 0.61/0.58 s warm rebuild, 34,720 B binary, and 0.555/0.526 s benchmark.
- Implementation line counts were collected but are excluded from ranking because formatting density and container strategies differed materially.

## 7. Interop findings

### FFmpeg/libav

All four candidates directly called the same system `libavformat` and returned the same version. FFmpeg therefore does not force the semantic core to be C++.

FFmpeg's public libraries are C APIs with versioned library interfaces. The kernel should wrap them behind backend/provider boundaries rather than expose FFmpeg objects through the public media ABI.

Odin's direct `foreign import ... "system:avformat"` path worked without a C/C++ shim. That is a meaningful integration strength.

### C ABI boundary

All four candidates exported the same C ABI successfully.

Odin supports direct C-calling procedures and exported symbol names cleanly. One boundary-specific ergonomic requirement appeared during the spike: exported `proc "c"` functions that call normal Odin procedures relying on implicit context must establish an Odin runtime context (for example `context = runtime.default_context()`). This is not a blocker, but it is exactly the kind of boundary invariant that should be centralized in an FFI layer rather than repeated across semantic code.

### OpenFX

OpenFX reinforces the choice of a C public ABI. Its API is deliberately specified in C to avoid C++ symbol-mangling/ABI problems between hosts and plugins.

The kernel's native plugin model need not be identical to OpenFX, but the same ABI lesson applies.

### OpenColorIO and C++-native libraries

OpenColorIO's public core headers are C++. This is a real integration advantage for a C++ implementation and should not be minimized.

The selected architecture handles this by permitting narrow C/C++ adapter libraries behind the kernel ABI. Rust or Odin should not attempt to recreate mature C++ media libraries merely to keep the implementation language uniform.

If C++-only integrations grow to dominate a particular subsystem, that subsystem may itself be implemented in C++ behind the stable C ABI.

### Graphics and execution ecosystem

Odin deserves separate consideration for execution because its language/runtime design emphasizes explicit allocation and data-oriented systems code, and its maintained package ecosystem includes direct graphics/platform bindings useful to media execution.

However, this bakeoff did not create GPU resources, schedule asynchronous command buffers, exercise hardware-video decode surfaces, or test Metal/Vulkan/D3D lifetime behavior. Those claims therefore remain **motivation for a later execution bakeoff**, not evidence from this experiment.

## 8. Safety and semantic-model findings

### C++

C++ made the spike extremely compact and integrates naturally with both C and C++ media ecosystems. It is the strongest candidate if direct ecosystem integration and minimum binary/build overhead dominate the problem.

The downside is that ownership, aliasing, thread-safety, mutation discipline, and invalid-state prevention remain architectural conventions enforced through API design, review, sanitizers, smart pointers, and tests.

For a renderer/effects engine this trade could favor C++. For this project's trusted semantic core, however, immutable committed state, candidate deltas, snapshots, typed IR, transformation legality, invalidation, and eventually concurrent resource ownership increase the value of compile-time ownership and type constraints.

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

### Odin

Odin materially improved on the case that motivated adding it:

- direct C/library interop was straightforward;
- shared-library output was tiny;
- cold builds were C++-class rather than Zig-class;
- the language made fixed-layout, data-oriented state straightforward;
- explicit allocation was easy to isolate in the tiny spike;
- the C ABI could be exported directly.

Its semantic-core disadvantage is the same basic category as C++ and Zig: Odin does not provide Rust's ownership/borrowing model or equivalent compile-time concurrency guarantees. The project can encode candidate/committed/verified states as distinct types, but lifetime, aliasing, and concurrent resource ownership remain programmer-enforced invariants.

The Odin spike deliberately used bounded arrays so container-library behavior would not dominate the experiment. A production State kernel would need a deliberate allocator/arena/collection policy rather than inheriting this test representation.

For the semantic State/Transformation core, Odin therefore does not overcome Rust's primary advantage. For a frame/resource execution engine, however, manual allocation and data-oriented control may be benefits rather than costs. That is why Odin remains an explicit execution candidate instead of being dismissed after the semantic result.

## 9. Weighted semantic-core decision matrix

This matrix is a decision aid, not an objective language ranking. Weights reflect the planned **semantic** kernel, particularly its small trusted core and strong state/transformation invariants.

| Criterion | Weight | C++ | Rust | Zig | Odin |
|---|---:|---:|---:|---:|---:|
| Semantic/ownership safety | 30% | 6.5 | 9.5 | 7.5 | 7.0 |
| Native media ecosystem integration | 20% | 10.0 | 8.0 | 7.5 | 8.5 |
| Stable C ABI / foreign-language interop | 15% | 9.0 | 9.0 | 9.5 | 9.5 |
| Toolchain/build maturity | 10% | 9.5 | 9.0 | 7.0 | 7.5 |
| Cross-platform/package outlook | 10% | 9.0 | 9.5 | 8.5 | 8.5 |
| Runtime/footprint | 10% | 10.0 | 7.5 | 8.0 | 9.5 |
| Diagnostics/testing/fuzzing ecosystem | 5% | 8.5 | 9.5 | 7.5 | 7.0 |
| **Weighted score** | **100%** | **85.8** | **88.8** | **79.0** | **81.3** |

The narrow Rust/C++ margin remains important. C++ is not a fallback candidate of last resort; it is a strong second choice whose biggest advantage is direct access to the professional media ecosystem. Rust wins the semantic-core weighting because this kernel's differentiating work is expected to live in state/transformation correctness rather than in reinventing rendering libraries.

Odin's 81.3 semantic-core score should not be interpreted as a poor language result. The matrix intentionally gives 30% of its weight to ownership/semantic safety. Odin's strongest advantages belong to a different domain—explicit data/resource execution—which is why a future execution-specific matrix must use different criteria rather than reusing this score.

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

### Execution language remains deliberately open

Do **not** introduce Odin as a second implementation language merely because its semantic spike performed well.

When `media-execution` reaches the point where frame pools, temporal scheduling, CPU/SIMD processing, asynchronous GPU ownership, hardware decode surfaces, and Metal/Vulkan/D3D providers are concrete, run an execution-specific bakeoff. At minimum compare:

```text
C++
Rust
Odin
```

and retain Zig if its ecosystem/toolchain position materially improves or it has a specific provider advantage.

That bakeoff should measure:

- frame/buffer-pool allocation and reuse;
- typed memory-domain/resource handles;
- DAG scheduling overhead;
- multi-threaded cancellation and ownership;
- CPU/SIMD frame kernels;
- FFI/provider-call overhead;
- Vulkan on Linux;
- Metal/VideoToolbox on macOS;
- D3D/Media Foundation on Windows;
- asynchronous GPU resource lifetime correctness;
- build/package complexity across those targets.

A Rust-semantic/Odin-execution split is now a **plausible architecture**, not a selected architecture.

### Unsafe/FFI policy

Adopt these rules from the beginning:

1. semantic crates should use `#![forbid(unsafe_code)]` where practical;
2. raw pointers and native-library calls live in dedicated FFI/provider crates;
3. every unsafe block requires a stated safety invariant;
4. no foreign-library object crosses the stable public C ABI as an exposed implementation type;
5. ownership of every opaque ABI handle is explicit and documented;
6. sanitizers/fuzzers/conformance tests exercise the C boundary independently of Rust's internal safety.

### C/C++ and other native providers

C and C++ are first-class implementation languages for integration layers when they materially reduce risk or complexity:

- OpenColorIO adapter;
- OpenFX host compatibility;
- vendor codec/GPU SDK integration;
- OS/platform-specific media APIs;
- performance-critical code where profiling demonstrates a real problem that cannot be solved cleanly in Rust.

Odin is likewise permitted for a provider/execution subsystem if its execution-specific bakeoff demonstrates a concrete advantage.

Do not rewrite proven native media libraries in Rust, Odin, or any other language for ideological consistency.

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
- plugin unload/cancellation and asynchronous GPU ownership;
- the dedicated C++/Rust/Odin execution-runtime bakeoff described above.

These are re-evaluation checkpoints, not reasons to delay Phase 1.

## 12. Reconsideration triggers

Revisit the Rust-core decision if evidence shows one of the following:

- C/C++/Odin provider code grows into a majority of the kernel implementation rather than remaining provider/execution-boundary code;
- required platform/vendor SDKs cannot be wrapped without unacceptable correctness or maintenance cost;
- profiling identifies an unavoidable Rust/FFI overhead that is material to end-user media performance;
- toolchain/platform support blocks a required production target;
- the chosen C ABI cannot represent a necessary ownership/resource contract cleanly.

A reconsideration should not automatically change the public ABI.

## 13. Phase 0 conclusion

The four-language bakeoff changes the conclusion slightly but does not reverse it:

> **Start the foundational media kernel's semantic core in Rust. Make the stable C ABI the real long-term commitment. Use C/C++ aggressively at media ecosystem boundaries. Odin is now the priority non-Rust candidate for a later execution/runtime bakeoff because it demonstrated C++-class build/footprint characteristics and clean C interop, but do not incur a two-language core until execution-specific evidence justifies it. Zig remains available for narrow native components but is not selected for the semantic core today.**

This is sufficient to proceed with the Phase 1 State/IR work once the remaining Phase 0 exact-time and canonical-IR decisions are completed, while preserving a deliberate checkpoint before the execution subsystem's implementation language is frozen.
