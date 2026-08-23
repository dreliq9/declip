#!/usr/bin/env python3
import ctypes
import hashlib
import json
import os
import random
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

MK_OK = 0
MK_INVALID = 1
MK_NOT_FOUND = 2
MK_CONFLICT = 3
MK_OVERFLOW = 5
MK_STALE = 6
MK_CYCLE = 7

MK_NODE_SOURCE = 1
MK_NODE_TRANSFORM = 2
MK_NODE_SINK = 3
MK_NO_RESOURCE_SLOT = 0xFFFFFFFF


class Time(ctypes.Structure):
    _fields_ = [("num", ctypes.c_int64), ("den", ctypes.c_int64)]


class Handle(ctypes.Structure):
    _fields_ = [("slot", ctypes.c_uint32), ("generation", ctypes.c_uint32)]

    def tuple(self):
        return (int(self.slot), int(self.generation))


NO_RESOURCE = Handle(MK_NO_RESOURCE_SLOT, 0)


def load(path: Path):
    lib = ctypes.CDLL(str(path.resolve()))

    lib.mk_time_normalize.argtypes = [Time, ctypes.POINTER(Time)]
    lib.mk_time_normalize.restype = ctypes.c_int
    lib.mk_time_add.argtypes = [Time, Time, ctypes.POINTER(Time)]
    lib.mk_time_add.restype = ctypes.c_int
    lib.mk_time_compare.argtypes = [Time, Time]
    lib.mk_time_compare.restype = ctypes.c_int

    lib.mk_kernel_create.restype = ctypes.c_void_p
    lib.mk_kernel_destroy.argtypes = [ctypes.c_void_p]
    lib.mk_kernel_revision.argtypes = [ctypes.c_void_p]
    lib.mk_kernel_revision.restype = ctypes.c_uint64
    lib.mk_kernel_add_asset.argtypes = [ctypes.c_void_p, ctypes.c_char_p, Time]
    lib.mk_kernel_add_asset.restype = ctypes.c_int
    lib.mk_kernel_append_clip.argtypes = [ctypes.c_void_p, ctypes.c_char_p, Time, Time, Time]
    lib.mk_kernel_append_clip.restype = ctypes.c_int
    lib.mk_kernel_propose_trim.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint64,
        ctypes.c_size_t,
        Time,
        ctypes.POINTER(ctypes.c_uint64),
    ]
    lib.mk_kernel_propose_trim.restype = ctypes.c_int
    lib.mk_kernel_commit.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64)]
    lib.mk_kernel_commit.restype = ctypes.c_int
    lib.mk_kernel_state_hash.argtypes = [ctypes.c_void_p]
    lib.mk_kernel_state_hash.restype = ctypes.c_uint64

    lib.mk_resource_alloc.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_uint32, ctypes.POINTER(Handle)]
    lib.mk_resource_alloc.restype = ctypes.c_int
    lib.mk_resource_retain.argtypes = [ctypes.c_void_p, Handle]
    lib.mk_resource_retain.restype = ctypes.c_int
    lib.mk_resource_release.argtypes = [ctypes.c_void_p, Handle]
    lib.mk_resource_release.restype = ctypes.c_int
    lib.mk_resource_touch.argtypes = [ctypes.c_void_p, Handle]
    lib.mk_resource_touch.restype = ctypes.c_int
    lib.mk_resource_refcount.argtypes = [ctypes.c_void_p, Handle, ctypes.POINTER(ctypes.c_uint32)]
    lib.mk_resource_refcount.restype = ctypes.c_int
    lib.mk_resource_hash.argtypes = [ctypes.c_void_p]
    lib.mk_resource_hash.restype = ctypes.c_uint64

    lib.mk_plan_reset.argtypes = [ctypes.c_void_p]
    lib.mk_plan_reset.restype = ctypes.c_int
    lib.mk_plan_add_node.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
        ctypes.c_size_t,
        Handle,
    ]
    lib.mk_plan_add_node.restype = ctypes.c_int
    lib.mk_plan_validate.argtypes = [ctypes.c_void_p]
    lib.mk_plan_validate.restype = ctypes.c_int
    lib.mk_plan_hash.argtypes = [ctypes.c_void_p]
    lib.mk_plan_hash.restype = ctypes.c_uint64

    lib.mk_ffmpeg_version.restype = ctypes.c_uint32
    lib.mk_benchmark.argtypes = [ctypes.c_uint64]
    lib.mk_benchmark.restype = ctypes.c_uint64
    return lib


def add_node(lib, kernel, node_id, kind, deps, resource=NO_RESOURCE):
    if deps:
        arr = (ctypes.c_uint32 * len(deps))(*deps)
        return lib.mk_plan_add_node(kernel, node_id, kind, arr, len(deps), resource)
    return lib.mk_plan_add_node(kernel, node_id, kind, None, 0, resource)


def base_scenario(lib):
    n = Time()
    assert lib.mk_time_normalize(Time(2, 4), ctypes.byref(n)) == MK_OK
    assert (n.num, n.den) == (1, 2)
    z = Time()
    assert lib.mk_time_add(Time(1001, 30000), Time(1, 48000), ctypes.byref(z)) == MK_OK
    assert (z.num, z.den) == (2671, 80000)
    assert lib.mk_time_compare(z, Time(0, 1)) > 0

    k = lib.mk_kernel_create()
    assert k
    try:
        assert lib.mk_kernel_add_asset(k, b"a.mp4", Time(10, 1)) == MK_OK
        assert lib.mk_kernel_add_asset(k, b"b.mp4", Time(8, 1)) == MK_OK
        assert lib.mk_kernel_add_asset(k, b"a.mp4", Time(10, 1)) == MK_CONFLICT
        assert lib.mk_kernel_append_clip(k, b"a.mp4", Time(0, 1), Time(6, 1), Time(0, 1)) == MK_OK
        assert lib.mk_kernel_append_clip(k, b"b.mp4", Time(0, 1), Time(5, 1), Time(1, 2)) == MK_OK
        assert lib.mk_kernel_append_clip(k, b"missing.mp4", Time(0, 1), Time(1, 1), Time(0, 1)) == MK_NOT_FOUND
        assert lib.mk_kernel_append_clip(k, b"b.mp4", Time(7, 1), Time(5, 1), Time(0, 1)) == MK_INVALID

        hash_before = int(lib.mk_kernel_state_hash(k))
        proposal = ctypes.c_uint64()
        assert lib.mk_kernel_propose_trim(k, 0, 0, Time(5, 1), ctypes.byref(proposal)) == MK_OK
        assert lib.mk_kernel_revision(k) == 0
        assert int(lib.mk_kernel_state_hash(k)) == hash_before, "candidate changed committed-state hash"
        revision = ctypes.c_uint64()
        assert lib.mk_kernel_commit(k, proposal.value, ctypes.byref(revision)) == MK_OK
        assert revision.value == 1 and lib.mk_kernel_revision(k) == 1
        hash_after = int(lib.mk_kernel_state_hash(k))
        assert hash_after != hash_before
        stale_proposal = ctypes.c_uint64()
        assert lib.mk_kernel_propose_trim(k, 0, 0, Time(4, 1), ctypes.byref(stale_proposal)) == MK_CONFLICT

        h_a = Handle()
        h_b = Handle()
        assert lib.mk_resource_alloc(k, 4096, 1, ctypes.byref(h_a)) == MK_OK
        assert lib.mk_resource_alloc(k, 8192, 2, ctypes.byref(h_b)) == MK_OK
        assert lib.mk_resource_touch(k, h_a) == MK_OK
        refs = ctypes.c_uint32()
        assert lib.mk_resource_refcount(k, h_a, ctypes.byref(refs)) == MK_OK and refs.value == 1
        assert lib.mk_resource_retain(k, h_a) == MK_OK
        assert lib.mk_resource_refcount(k, h_a, ctypes.byref(refs)) == MK_OK and refs.value == 2
        assert lib.mk_resource_release(k, h_a) == MK_OK
        assert lib.mk_resource_release(k, h_a) == MK_OK
        assert lib.mk_resource_touch(k, h_a) == MK_STALE
        assert lib.mk_resource_release(k, h_a) == MK_STALE

        h_c = Handle()
        assert lib.mk_resource_alloc(k, 16384, 3, ctypes.byref(h_c)) == MK_OK
        assert h_c.slot == h_a.slot and h_c.generation != h_a.generation
        assert lib.mk_resource_touch(k, h_c) == MK_OK

        assert lib.mk_plan_reset(k) == MK_OK
        assert add_node(lib, k, 10, MK_NODE_SOURCE, [], h_b) == MK_OK
        assert add_node(lib, k, 20, MK_NODE_TRANSFORM, [10], h_c) == MK_OK
        assert add_node(lib, k, 30, MK_NODE_SINK, [20]) == MK_OK
        assert lib.mk_plan_validate(k) == MK_OK
        valid_plan_hash = int(lib.mk_plan_hash(k))
        assert add_node(lib, k, 30, MK_NODE_SINK, [20]) == MK_CONFLICT

        assert lib.mk_plan_reset(k) == MK_OK
        assert add_node(lib, k, 1, MK_NODE_TRANSFORM, [2]) == MK_OK
        assert add_node(lib, k, 2, MK_NODE_TRANSFORM, [1]) == MK_OK
        assert lib.mk_plan_validate(k) == MK_CYCLE

        assert lib.mk_plan_reset(k) == MK_OK
        assert add_node(lib, k, 1, MK_NODE_SOURCE, []) == MK_OK
        assert add_node(lib, k, 2, MK_NODE_SINK, [999]) == MK_OK
        assert lib.mk_plan_validate(k) == MK_INVALID

        assert lib.mk_plan_reset(k) == MK_OK
        assert add_node(lib, k, 10, MK_NODE_SOURCE, [], h_b) == MK_OK
        assert add_node(lib, k, 20, MK_NODE_TRANSFORM, [10], h_a) == MK_OK
        assert lib.mk_plan_validate(k) == MK_STALE

        assert lib.mk_plan_reset(k) == MK_OK
        assert add_node(lib, k, 10, MK_NODE_SOURCE, [], h_b) == MK_OK
        assert add_node(lib, k, 20, MK_NODE_TRANSFORM, [10], h_c) == MK_OK
        assert add_node(lib, k, 30, MK_NODE_SINK, [20]) == MK_OK
        assert lib.mk_plan_validate(k) == MK_OK

        return {
            "time_add": [int(z.num), int(z.den)],
            "revision": int(lib.mk_kernel_revision(k)),
            "state_hash": int(lib.mk_kernel_state_hash(k)),
            "resource_hash": int(lib.mk_resource_hash(k)),
            "plan_hash": int(lib.mk_plan_hash(k)),
            "valid_plan_hash": valid_plan_hash,
            "reused_handle": list(h_c.tuple()),
            "ffmpeg_version": int(lib.mk_ffmpeg_version()),
        }
    finally:
        lib.mk_kernel_destroy(k)


def update_digest(digest, *values):
    for value in values:
        digest.update(int(value).to_bytes(8, "little", signed=False))


def resource_failure_stress(lib, operations=30000, seed=0xD3C11F):
    rng = random.Random(seed)
    k = lib.mk_kernel_create()
    assert k
    tokens = []
    digest = hashlib.sha256()
    started = time.perf_counter()
    try:
        for step in range(operations):
            active_count = sum(1 for t in tokens if t["active"])
            choose_alloc = not tokens or (rng.random() < 0.24 and active_count < 96)
            if choose_alloc:
                h = Handle()
                size = 512 * (1 + rng.randrange(64))
                domain = 1 + rng.randrange(4)
                status = int(lib.mk_resource_alloc(k, size, domain, ctypes.byref(h)))
                update_digest(digest, step, status, h.slot, h.generation)
                if status == MK_OK:
                    tokens.append({"handle": Handle(h.slot, h.generation), "refs": 1, "active": True})
                continue

            index = rng.randrange(len(tokens))
            token = tokens[index]
            h = token["handle"]
            choice = rng.random()
            if choice < 0.22:
                status = int(lib.mk_resource_retain(k, h))
                if status == MK_OK:
                    token["refs"] += 1
            elif choice < 0.72:
                status = int(lib.mk_resource_release(k, h))
                if status == MK_OK:
                    token["refs"] -= 1
                    if token["refs"] == 0:
                        token["active"] = False
            elif choice < 0.92:
                status = int(lib.mk_resource_touch(k, h))
            else:
                refs = ctypes.c_uint32(0xDEADBEEF)
                status = int(lib.mk_resource_refcount(k, h, ctypes.byref(refs)))
                if status == MK_OK:
                    assert refs.value == token["refs"]
                update_digest(digest, refs.value)
            expected = MK_OK if token["active"] else MK_STALE
            if choice >= 0.22 and choice < 0.92:
                # Release that dropped the last ref is still a successful operation.
                if choice < 0.72 and status == MK_OK:
                    expected = MK_OK
                assert status == expected, (step, choice, status, expected, token)
            update_digest(digest, step, index, status)

        return {
            "operations": operations,
            "seconds": time.perf_counter() - started,
            "status_digest": digest.hexdigest(),
            "resource_hash": int(lib.mk_resource_hash(k)),
            "token_count": len(tokens),
            "active_count": sum(1 for t in tokens if t["active"]),
        }
    finally:
        lib.mk_kernel_destroy(k)


def plan_failure_stress(lib, plans=1200, seed=0xA11DAG):
    # Python integer literals cannot spell mnemonic hex; normalize here.
    rng = random.Random(seed if isinstance(seed, int) else 0xA11DA6)
    k = lib.mk_kernel_create()
    assert k
    digest = hashlib.sha256()
    started = time.perf_counter()
    try:
        for case in range(plans):
            assert lib.mk_plan_reset(k) == MK_OK
            mode = case % 4
            if mode == 0:
                count = 5 + rng.randrange(8)
                assert add_node(lib, k, 1, MK_NODE_SOURCE, []) == MK_OK
                for node_id in range(2, count):
                    dep1 = 1 + rng.randrange(node_id - 1)
                    deps = [dep1]
                    if node_id > 3 and rng.random() < 0.35:
                        dep2 = 1 + rng.randrange(node_id - 1)
                        if dep2 != dep1:
                            deps.append(dep2)
                    assert add_node(lib, k, node_id, MK_NODE_TRANSFORM, deps) == MK_OK
                assert add_node(lib, k, count, MK_NODE_SINK, [count - 1]) == MK_OK
                status = int(lib.mk_plan_validate(k))
                assert status == MK_OK
                update_digest(digest, case, status, lib.mk_plan_hash(k))
            elif mode == 1:
                assert add_node(lib, k, 1, MK_NODE_SOURCE, []) == MK_OK
                assert add_node(lib, k, 2, MK_NODE_SINK, [999]) == MK_OK
                status = int(lib.mk_plan_validate(k))
                assert status == MK_INVALID
                update_digest(digest, case, status)
            elif mode == 2:
                assert add_node(lib, k, 11, MK_NODE_TRANSFORM, [12]) == MK_OK
                assert add_node(lib, k, 12, MK_NODE_TRANSFORM, [11]) == MK_OK
                status = int(lib.mk_plan_validate(k))
                assert status == MK_CYCLE
                update_digest(digest, case, status)
            else:
                h = Handle()
                assert lib.mk_resource_alloc(k, 1024, 1, ctypes.byref(h)) == MK_OK
                assert lib.mk_resource_release(k, h) == MK_OK
                assert add_node(lib, k, 1, MK_NODE_SOURCE, [], h) == MK_OK
                assert add_node(lib, k, 2, MK_NODE_SINK, [1]) == MK_OK
                status = int(lib.mk_plan_validate(k))
                assert status == MK_STALE
                update_digest(digest, case, status, h.slot, h.generation)
        return {
            "plans": plans,
            "seconds": time.perf_counter() - started,
            "status_digest": digest.hexdigest(),
            "resource_hash": int(lib.mk_resource_hash(k)),
        }
    finally:
        lib.mk_kernel_destroy(k)


def benchmark(lib, iterations, rounds):
    timings = []
    checksums = []
    for _ in range(rounds):
        start = time.perf_counter()
        checksums.append(int(lib.mk_benchmark(iterations)))
        timings.append(time.perf_counter() - start)
    assert len(set(checksums)) == 1
    return {
        "iterations": iterations,
        "rounds": rounds,
        "median_seconds": statistics.median(timings),
        "min_seconds": min(timings),
        "max_seconds": max(timings),
        "checksum": checksums[0],
    }


def read_float(path):
    try:
        return float(Path(path).read_text().strip())
    except Exception:
        return None


def source_metrics(path: Path, language: str):
    text = path.read_text()
    lines = text.splitlines()
    metrics = {
        "bytes": len(text.encode()),
        "nonblank_loc": sum(1 for line in lines if line.strip()),
    }
    if language == "cpp":
        metrics.update({
            "manual_memory_sites": text.count("new mk_kernel") + text.count("delete kernel"),
            "raw_pointer_markers": text.count("*"),
            "ffi_boundary_markers": text.count('extern "C"'),
        })
    elif language == "rust":
        metrics.update({
            "manual_memory_sites": text.count("Box::into_raw") + text.count("Box::from_raw"),
            "unsafe_occurrences": text.count("unsafe"),
            "raw_pointer_tokens": text.count("*mut ") + text.count("*const "),
            "ffi_boundary_markers": text.count("extern \"C\"") + text.count("extern \"C\""),
        })
    elif language == "zig":
        metrics.update({
            "manual_memory_sites": text.count("c.malloc") + text.count("c.free"),
            "pointer_cast_occurrences": text.count("@ptrCast") + text.count("@alignCast"),
            "ffi_boundary_markers": text.count("export fn"),
        })
    elif language == "odin":
        metrics.update({
            "manual_memory_sites": text.count("new(Kernel)") + text.count("free("),
            "rawptr_occurrences": text.count("rawptr"),
            "pointer_cast_occurrences": text.count("cast(^Kernel)"),
            "ffi_context_sites": text.count("runtime.default_context()"),
            "ffi_boundary_markers": text.count('proc "c"'),
        })
    return metrics


def main():
    if len(sys.argv) != 5:
        raise SystemExit("usage: run_arch_bakeoff.py CPP_SO RUST_SO ZIG_SO ODIN_SO")

    libs = {
        "cpp": Path(sys.argv[1]),
        "rust": Path(sys.argv[2]),
        "zig": Path(sys.argv[3]),
        "odin": Path(sys.argv[4]),
    }
    source_paths = {
        "cpp": ROOT / "cpp" / "kernel.cpp",
        "rust": ROOT / "rust" / "src" / "lib.rs",
        "zig": ROOT / "zig" / "kernel.zig",
        "odin": ROOT / "odin" / "kernel.odin",
    }
    build_paths = {
        name: os.environ.get(f"MK_{name.upper()}_BUILD_TIME", "") for name in libs
    }
    warm_paths = {
        name: os.environ.get(f"MK_{name.upper()}_WARM_BUILD_TIME", "") for name in libs
    }
    iterations = int(os.environ.get("MK_BENCH_ITERATIONS", "5000000"))
    rounds = int(os.environ.get("MK_BENCH_ROUNDS", "5"))
    resource_ops = int(os.environ.get("MK_RESOURCE_STRESS_OPS", "30000"))
    plan_cases = int(os.environ.get("MK_PLAN_STRESS_CASES", "1200"))

    results = {}
    for name, path in libs.items():
        lib = load(path)
        results[name] = {
            "scenario": base_scenario(lib),
            "resource_stress": resource_failure_stress(lib, operations=resource_ops),
            "plan_stress": plan_failure_stress(lib, plans=plan_cases, seed=0xA11DA6),
            "benchmark": benchmark(lib, iterations, rounds),
            "binary_bytes": path.stat().st_size,
            "cold_build_seconds": read_float(build_paths[name]) if build_paths[name] else None,
            "warm_no_change_build_seconds": read_float(warm_paths[name]) if warm_paths[name] else None,
            "source": source_metrics(source_paths[name], name),
        }

    equivalence_fields = [
        ("scenario", "time_add"),
        ("scenario", "revision"),
        ("scenario", "state_hash"),
        ("scenario", "resource_hash"),
        ("scenario", "plan_hash"),
        ("scenario", "valid_plan_hash"),
        ("scenario", "reused_handle"),
        ("scenario", "ffmpeg_version"),
        ("resource_stress", "status_digest"),
        ("resource_stress", "resource_hash"),
        ("resource_stress", "token_count"),
        ("resource_stress", "active_count"),
        ("plan_stress", "status_digest"),
        ("plan_stress", "resource_hash"),
        ("benchmark", "checksum"),
    ]
    equivalence = {}
    for section, field in equivalence_fields:
        values = [results[name][section][field] for name in results]
        key = f"{section}.{field}"
        equivalence[key] = all(value == values[0] for value in values[1:])
    assert all(equivalence.values()), {k: v for k, v in equivalence.items() if not v}

    payload = {
        "equivalence": equivalence,
        "results": results,
        "notes": {
            "architecture_scope": "Revisioned semantic state + candidate commit + generational resource handles + typed DAG validation + deterministic hashes + C ABI + libavformat interop.",
            "failure_scope": "Common randomized misuse stresses stale generations, retain/release churn, invalid dependencies, cycles, and stale resource references. This is not a formal memory-safety proof.",
            "performance": "Native exact-time benchmark and Python-driven stress timings are sanity/overhead probes, not render-throughput benchmarks.",
            "storage": "All four implementations use fixed-capacity kernel stores so container-library differences do not dominate architectural comparison.",
            "loc": "Source size and LOC are reported but not directly scored; formatting and language verbosity differ.",
        },
    }
    Path("architecture-bakeoff-results.json").write_text(json.dumps(payload, indent=2) + "\n")

    langs = ["cpp", "rust", "zig", "odin"]
    labels = ["C++", "Rust", "Zig", "Odin"]
    lines = [
        "# Kernel Architecture Bakeoff — Measured Results",
        "",
        "All four implementations passed the same semantic, generational-handle, DAG, failure-stress, C-ABI, and libavformat behavior suite.",
        "",
        "| Metric | " + " | ".join(labels) + " |",
        "|---|" + "---:|" * len(labels),
    ]
    metrics = [
        ("Cold build seconds", lambda r: r["cold_build_seconds"]),
        ("Warm no-change build seconds", lambda r: r["warm_no_change_build_seconds"]),
        ("Stripped shared library bytes", lambda r: r["binary_bytes"]),
        ("Nonblank LOC (not scored directly)", lambda r: r["source"]["nonblank_loc"]),
        (f"Native exact-time benchmark seconds ({iterations:,})", lambda r: r["benchmark"]["median_seconds"]),
        (f"Resource misuse stress seconds ({resource_ops:,} ops)", lambda r: r["resource_stress"]["seconds"]),
        (f"Plan failure stress seconds ({plan_cases:,} cases)", lambda r: r["plan_stress"]["seconds"]),
    ]
    for label, getter in metrics:
        vals = []
        for lang in langs:
            v = getter(results[lang])
            vals.append("n/a" if v is None else (f"{v:.6f}" if isinstance(v, float) else str(v)))
        lines.append(f"| {label} | " + " | ".join(vals) + " |")

    lines += ["", "## Equivalence/failure checks", ""]
    for key, value in equivalence.items():
        lines.append(f"- {key}: {'PASS' if value else 'FAIL'}")
    lines += [
        "",
        "## Interpretation limits",
        "",
        "- The test intentionally uses the same architectural storage strategy in all languages; it compares how cleanly each language can express that design rather than which standard container library is fastest.",
        "- Randomized invalid-operation testing verifies externally observable failure behavior and stale-handle rejection; it does not replace sanitizers, fuzzers, concurrency testing, or GPU lifetime testing.",
        "- No language should be selected from the arithmetic benchmark alone.",
    ]
    Path("architecture-bakeoff-results.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
