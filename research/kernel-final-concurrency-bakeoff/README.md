# Final Media-Kernel Concurrency Language Gate

This disposable research slice tests the remaining implementation-language question for the foundational media kernel: whether an architecture-centric Odin implementation remains clean and correct once ownership becomes concurrent and asynchronous.

The same scheduler/resource model is implemented in C++20, Rust, Zig, and Odin. The gate exercises bounded producer/worker queues, backpressure, concurrent generational-handle retain/release, cancellation, deferred reclamation behind simulated asynchronous fences, provider/device loss, multiple seeds and worker counts, and candidate-specific safety instrumentation. A small Vulkan probe validates the fence lifecycle against a real Vulkan implementation on the hosted Linux runner (normally Mesa/Lavapipe); it is not a GPU-performance benchmark.

The research branch is not intended for merge. Durable conclusions belong on `planning/media-kernel`.
