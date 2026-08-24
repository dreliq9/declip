# Media Kernel Whole-Architecture Language Bakeoff

**Status:** Phase 0 follow-on decision record  
**Date:** 2026-08-23  
**Candidates:** C++20, Rust 1.97.1, Zig 0.16.0, Odin `dev-2026-08-nightly:902106f`  
**Decision:** Odin becomes the leading candidate for a unified media-kernel implementation, but the language is not frozen until a concurrent/asynchronous resource-ownership gate is passed. The stable C ABI remains the durable public commitment. C/C++ remain first-class provider languages. Rust remains the safety-first fallback. Zig is not selected as the primary kernel language.

This document follows `media-kernel-language-bakeoff.md`. The earlier bakeoff weighted a small State/Transformation semantic core heavily toward compiler-enforced ownership safety and selected Rust. This follow-on asks a different question:

> If the media kernel encodes its important invariants architecturally — immutable revisions, candidate commits, stable identity, generational resource handles, centralized state, explicit DAG validation, and a stable C ABI — which language produces the cleanest *whole-kernel* foundation rather than merely the safest semantic microkernel?

For current planning, this document **refines and supersedes the implementation-language conclusion** of the earlier semantic-only bakeoff. The earlier document remains valid evidence about Rust's safety advantage and the first C++/Rust/Zig/Odin measurements.

## 1. Why this second bakeoff was necessary

The first language comparison gave Rust a 30% weighting for semantic/ownership safety. That was appropriate for the experiment, but it implicitly assumed that many correctness properties should be represented through the implementation language's ownership model.

The kernel research points toward a different possibility:

```text
Durable objects       -> stable IDs, not arbitrary object pointers
Committed project     -> immutable snapshot/revision
Change                -> typed candidate delta -> validate -> commit
Ephemeral resource    -> slot + generation handle
Resource lifetime     -> centralized resource store
Execution             -> validated typed DAG
Backend access        -> provider boundary
Public compatibility  -> stable C ABI
```

If those structures are non-bypassable, substantial correctness moves from programmer convention *and* from implementation-language cleverness into the kernel architecture itself.

That could favor a simpler/data-oriented systems language such as Odin while retaining the same externally enforceable invariants.

## 2. Experiment design

Four implementations were built against one C ABI and one behavioral specification.

The common slice contained:

### Semantic state

- exact rational `MediaTime` arithmetic with widened intermediates;
- assets with bounded source durations;
- clips with source-range and transition validation;
- immutable committed revision number;
- candidate trim proposals bound to an exact base revision;
- atomic commit to a new revision;
- stale-base conflict rejection;
- deterministic committed-state hash.

### Ephemeral resource model

- fixed-capacity resource store;
- `ResourceHandle { slot, generation }`;
- allocation with explicit size/domain metadata;
- retain/release accounting;
- slot reuse only through a new generation;
- stale-handle rejection after final release;
- deterministic resource-state hash.

This deliberately tests the architectural alternative to exposing arbitrary frame/resource pointers.

### Executable-plan model

- typed `Source`, `Transform`, and `Sink` nodes;
- explicit dependency IDs;
- optional generational resource binding;
- duplicate-node rejection;
- missing-dependency rejection;
- source/sink structural obligations;
- cycle detection;
- stale-resource rejection;
- deterministic plan hash.

### Native boundary

- the same exported C ABI from all four languages;
- direct call to the same system `libavformat`;
- Python `ctypes` consumer shared by all candidates.

All four implementations used fixed-capacity stores. This was intentional: the experiment evaluates the architecture and language expression of that architecture rather than turning into a benchmark of `std::vector`, `Vec`, a Zig container, or an Odin dynamic array.

## 3. Failure-resistance workload

A common deterministic harness ran more than the happy path.

### Resource misuse stress

Each candidate executed 30,000 seeded operations consisting of:

- allocations in several resource domains;
- retains;
- releases;
- touches;
- refcount queries;
- repeated use of stale handles;
- slot reuse with generation advancement.

The harness maintained an independent reference model and asserted every returned status. It also compared the complete status digest and final resource hash between languages.

### Plan failure stress

Each candidate executed 1,200 seeded plan cases covering:

- valid acyclic execution DAGs;
- missing dependencies;
- cycles;
- stale resource bindings.

Again, status digests and final resource state had to match exactly.

### Important limitation

This is a strong test of *architecturally visible* correctness. It is not a proof of memory safety, data-race freedom, asynchronous GPU lifetime correctness, or cancellation correctness. Those remain a separate hard gate before the implementation language is frozen.

## 4. Toolchains

Both replicated architecture runs used GitHub-hosted Ubuntu 24.04 runners with:

- g++ 13.3.0;
- rustc 1.97.1;
- cargo 1.97.1;
- Zig 0.16.0;
- Odin `dev-2026-08-nightly:902106f`;
- libavformat 60.16.100.

Rust required an explicit Cargo link declaration for `libavformat` in `build.rs`. C++ linked it directly in the compiler invocation, Zig linked it directly in its build command, and Odin used `foreign import ... "system:avformat"`.

The Rust issue was a build-configuration omission, not a runtime limitation, but it is useful evidence that integration friction belongs in the comparison.

## 5. Functional result

**All four candidates passed both complete runs.**

Every equivalence field matched across C++, Rust, Zig, and Odin:

- exact-time result;
- revision result;
- committed-state hash;
- resource-state hash;
- execution-plan hash;
- known-good plan hash;
- reused handle slot/generation;
- libavformat version;
- 30,000-operation resource stress status digest;
- resource-stress final hash;
- resource token/active counts;
- 1,200-case plan stress status digest;
- plan-stress resource hash;
- native benchmark checksum.

The key architecture result is therefore:

> **For the invariants represented in this slice, none of the four languages had to depend on a borrow checker or C++ ownership convention to produce the correct externally observable behavior. The kernel structures themselves carried the semantics.**

That does not eliminate Rust's defense-in-depth advantage; it demonstrates that the architecture can carry much more of the correctness burden than the first bakeoff assumed.

## 6. Replicated measurements

### Run A

| Metric | C++ | Rust | Zig | Odin |
|---|---:|---:|---:|---:|
| Cold optimized build | **2.56 s** | 4.32 s | 38.64 s | 3.18 s |
| Immediate no-change build | 0.38 s | **0.01 s** | 0.29 s | 0.49 s |
| Stripped shared library | **22,760 B** | 324,680 B | 39,992 B | 38,816 B |
| Native exact-time benchmark, 5M | **0.159 s** | 0.309 s | 0.373 s | 0.257 s |
| Resource misuse stress, 30k* | 0.476 s | 0.475 s | 0.475 s | 0.474 s |
| Plan failure stress, 1,200* | 0.00826 s | 0.00810 s | **0.00806 s** | 0.00814 s |

### Run B

| Metric | C++ | Rust | Zig | Odin |
|---|---:|---:|---:|---:|
| Cold optimized build | **2.57 s** | 4.16 s | 51.11 s | 3.56 s |
| Immediate no-change build | 0.48 s | **0.02 s** | 0.37 s | 0.61 s |
| Stripped shared library | **22,760 B** | 324,680 B | 39,896 B | 38,816 B |
| Native exact-time benchmark, 5M | **0.152 s** | 0.262 s | 0.472 s | 0.263 s |
| Resource misuse stress, 30k* | 0.779 s | 0.746 s | 0.747 s | **0.738 s** |
| Plan failure stress, 1,200* | 0.01140 s | 0.01128 s | 0.01143 s | 0.01141 s |

`*` The stress timings are substantially Python/FFI-driver dominated. Their important result is identical behavior/digests, not tiny timing differences.

### Source-size reference

| Metric | C++ | Rust | Zig | Odin |
|---|---:|---:|---:|---:|
| UTF-8 source bytes | **15,849** | 20,352 | 16,306 | 19,809 |
| Nonblank lines | **437** | 706 | 461 | 717 |

This directly rejects an over-strong version of the Odin hypothesis:

> **Odin was not the shortest implementation.**

Raw LOC actually favored C++ and Zig in this particular spike. Formatting and language idiom differ enough that LOC is not a selection metric, but Odin's cleanliness case must therefore be about architecture and system composition rather than fewer lines of code.

## 7. What “cleaner” means after the bakeoff

The evidence supports a narrower claim:

> **Odin can plausibly produce the cleanest overall media-kernel architecture if we deliberately make identity, mutation, and resource lifetime kernel concepts instead of leaning on host-language object ownership.**

That claim has four components.

### 7.1 One vocabulary from semantics through execution

A unified Odin implementation can use the same direct data model for:

```text
State
Revisions
Editorial IR
Executable IR
Transformation passes
Resource tables
Frame pools
Scheduling
Admission
C ABI boundary
GPU/provider orchestration
```

The architecture would still use C/C++ shims where an external library requires them, but it would not require an internal Rust-to-execution-language boundary merely to obtain a different low-level programming model.

Rust can also implement all of those layers, but its strongest advantage is in ownership-enforced semantic/concurrency correctness rather than in reducing the amount of explicit resource architecture the media system itself needs.

### 7.2 Architecture-neutral resource identity

The generational-handle model worked identically in every language:

```text
Frame_Handle {
    slot
    generation
}
```

That representation is useful independently of implementation language because it:

- detects stale reuse;
- crosses the C ABI naturally;
- can represent CPU/GPU/provider resource tables;
- avoids durable raw pointers between subsystems;
- makes lifetime state inspectable and testable;
- permits centralized synchronization/fence policy later.

This is a stronger long-term kernel contract than exposing Rust `Arc`, C++ `shared_ptr`, or native GPU objects through architectural boundaries.

### 7.3 Odin's measured systems characteristics are excellent

In both whole-architecture runs Odin stayed close to C++ on cold build and binary size:

- 3.18/3.56 s cold build versus C++ 2.56/2.57 s;
- 38.8 KB shared library versus C++ 22.8 KB;
- approximately 0.26 s in the native sanity benchmark, effectively tied with Rust in run B and faster than Rust in run A.

There is no evidence here of a performance or binary-cost reason to reject Odin.

### 7.4 The C boundary is direct, but should be designed properly

The test implementation establishes `runtime.default_context()` in each C-exported Odin procedure because normal Odin procedures carry implicit context.

This repetition is **not intrinsic to the pure kernel core**. Odin officially supports the `"contextless"` calling convention, which is the Odin calling convention without the implicit context pointer. Pure arithmetic/state/verification helpers can be designed as contextless procedures, while allocator/logging/error paths can receive an explicit kernel context or establish one at a narrow boundary.

Reference: https://odin-lang.org/docs/overview/#calling-conventions

A production Odin kernel should therefore avoid scattering ambient default context through semantic logic. The architecture should make allocator/logging/thread context explicit where consequential.

## 8. Candidate assessment

### C++

**What the bakeoff validated**

- shortest implementation in the spike;
- smallest binary;
- fastest native sanity benchmark;
- fastest cold build alongside Odin;
- unmatched direct access to C and C++ media ecosystems;
- identical architecture/failure behavior.

**Remaining cost**

C++ has the largest language/ABI complexity surface and the weakest default defense against lifetime, aliasing, use-after-free, and data-race mistakes. Those can be controlled through the kernel architecture, RAII, sanitizers, restricted coding rules, and review, but they remain ongoing engineering obligations.

C++ is the strongest choice if ecosystem integration and mature tooling dominate every other criterion. It is not obviously the cleanest language in which to define a deliberately small, easily-audited new kernel.

### Rust

**What the bakeoff validated**

- excellent functional result;
- best no-change build behavior;
- strong native performance;
- strongest compile-time ownership/concurrency defense;
- mature testing/fuzzing/package ecosystem.

**Observed/structural cost**

The C-facing spike needed explicit raw-pointer/`unsafe` boundary code and explicit native-library link configuration. A production implementation can and should quarantine this into small FFI crates, leaving semantic crates safe.

The architectural question is whether that extra defense is worth making Rust's ownership model a major implementation constraint when the durable kernel contracts already use IDs, revisions, candidate deltas, resource tables, and generation handles.

Rust remains the best safety-first choice.

### Zig

**What the bakeoff validated**

- compact source;
- direct C interop;
- small binary;
- clear explicit memory model;
- identical architecture/failure behavior;
- good warm build time.

**Observed cost**

Zig's fresh optimized build was 38.6–51.1 seconds in this small C-linked slice, dramatically above all other candidates. Its native sanity benchmark was also the slowest in both replicated runs. Neither result proves a production media runtime would be slow, but Zig did not produce a compensating advantage over Odin in this experiment.

Zig remains useful for targeted components but does not lead the primary-kernel decision.

### Odin

**What the bakeoff validated**

- identical semantic and failure behavior without relying on Rust ownership types;
- direct libavformat/C ABI integration;
- C++-class cold build behavior;
- C++/Zig-class tiny binary;
- native sanity performance around Rust in the replicated architecture runs;
- a direct data-oriented representation of state, handles, and execution nodes;
- plausible single-language path from semantic state into frame/GPU execution.

**Remaining cost**

Odin does not provide Rust's borrow checker or equivalent `Send`/`Sync` compile-time protection. If the kernel architecture is bypassed internally, memory/lifetime/concurrency bugs remain possible. The language/tooling ecosystem is also substantially younger than Rust or C++.

This means Odin's case depends on actually following the architecture tested here rather than treating it as optional guidance.

## 9. Whole-kernel decision matrix

The first bakeoff intentionally weighted semantic/ownership safety very heavily. This matrix instead weights the project's current question: *cleanliness of a unified foundational media kernel*.

It is a decision aid, not an objective ranking.

| Criterion | Weight | C++ | Rust | Zig | Odin |
|---|---:|---:|---:|---:|---:|
| Architectural directness / domain-shaped code | 20% | 8.0 | 8.0 | 9.0 | **9.5** |
| Language-surface / maintenance simplicity | 15% | 6.5 | 7.5 | 8.5 | **9.5** |
| Safety / defense in depth | 15% | 6.5 | **10.0** | 7.5 | 7.5 |
| Whole-kernel semantic + execution fit | 15% | **9.5** | 8.5 | 8.5 | **9.5** |
| Native media / C / GPU interop outlook | 15% | **10.0** | 8.0 | 9.5 | 9.5 |
| Build / footprint | 10% | **10.0** | 7.5 | 7.0 | 9.5 |
| Toolchain / testing maturity | 10% | **10.0** | 9.5 | 7.5 | 7.5 |
| **Weighted whole-kernel score** | **100%** | **8.48** | **8.40** | **8.35** | **9.00** |

The important result is not the second decimal place. It is the change in ordering produced by changing the actual problem definition:

- **Safety-first semantic core:** Rust leads.
- **Existing-ecosystem/performance-first native engine:** C++ leads.
- **Unified architecture/cleanliness-first new media kernel:** Odin leads.
- **Zig:** technically viable but does not lead a decisive axis in the current evidence.

## 10. Decision

The whole-architecture bakeoff changes the working language decision.

### Previous working decision

```text
Rust semantic core
        +
C/C++ providers
        +
possible Odin execution runtime later
```

### Revised working decision

```text
                    Stable C ABI
                         |
                         v
             Odin unified-kernel candidate
          /          |          |          \
       State     Transform   Execution   Admission
                                  |
                     C / C++ / platform providers
```

**Odin is now the leading implementation candidate for the kernel as a whole.**

Rust should no longer be considered automatically frozen as the Phase 1 semantic-core language. The bakeoff demonstrated that the critical State/resource/DAG invariants can be encoded directly in language-neutral kernel structures and produce identical failure behavior in all four implementations.

However, this is still a **provisional lead**, not a final language freeze.

## 11. Final hard gate before language freeze

The remaining question is precisely where Rust's strongest advantage lives and where this experiment did not test:

> concurrent and asynchronous resource ownership.

Before starting irreversible production implementation, build one more focused execution/concurrency slice comparing at minimum:

```text
Odin
Rust
C++
```

Keep Zig only if there is a specific execution/provider reason to retain it.

The gate must exercise:

- multiple CPU worker threads;
- cancellation while work is outstanding;
- resource retain/release from concurrent tasks;
- generation-safe reuse under contention;
- bounded work queues/backpressure;
- explicit ownership transfer between scheduler stages;
- simulated GPU fence completion;
- resource reclamation only after fence completion;
- device/provider loss and cancellation;
- sanitizer/fuzzer/stress instrumentation appropriate to each language.

Then extend that model to a real Vulkan resource on Linux and later Metal/VideoToolbox and D3D/Media Foundation.

### Freeze rule

Select Odin as the production language if it can implement this model without substantially more synchronization/lifetime machinery or failure surface than Rust.

Select Rust if the concurrent-resource implementation shows that compile-time ownership materially simplifies or hardens the real scheduler despite the extra FFI/integration structure.

Select C++ only if its native ecosystem integration produces a decisive implementation advantage that outweighs the added long-term safety/language complexity burden.

## 12. Architectural rules if Odin wins

An Odin implementation should not attempt to imitate ordinary C/C++ object ownership. Its cleanliness depends on making the architecture non-bypassable:

1. Durable semantic objects use stable IDs/references, not cross-module owning pointers.
2. Committed snapshots are immutable outside State.
3. All semantic changes are candidate deltas followed by validation and atomic commit.
4. Ephemeral resources use generational handles owned by centralized resource stores.
5. Resource stores have explicit allocator domains.
6. Thread ownership and scheduler mutation authority are explicit.
7. GPU lifetime is tied to explicit fence/submission state, not lexical scope assumptions.
8. Public/provider boundaries use the stable C ABI or deliberately narrow native adapters.
9. Pure core helpers should prefer contextless procedures; allocator/logging/runtime context should be explicit at consequential boundaries.
10. Sanitizers, tracking allocators, fuzzers, deterministic replay, and conformance tests are part of the safety model, not optional hardening.

## 13. Conclusion

The bakeoff supports the user's underlying architectural hypothesis, but with an important qualification:

> **Odin is not automatically cleaner because it can manually reproduce Rust's invariants. It becomes cleaner if the kernel itself owns those invariants so thoroughly that the implementation language no longer needs to represent them through pervasive ownership mechanics.**

The tested State/resource/DAG slice demonstrates that this approach works for a meaningful portion of the kernel. On that basis, Odin moves from “interesting execution language” to **leading unified-kernel candidate**.

The remaining concurrency/GPU ownership gate is necessary because it tests the one part of the problem where Rust's compiler-enforced model may still justify a more complex mixed implementation.
