#!/usr/bin/env python3
import ctypes
import json
import os
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MK_OK = 0
MK_INVALID = 1
MK_CONFLICT = 3
MK_BUFFER_TOO_SMALL = 4

class Time(ctypes.Structure):
    _fields_ = [("num", ctypes.c_int64), ("den", ctypes.c_int64)]


def load(path: Path):
    lib = ctypes.CDLL(str(path))
    lib.mk_time_normalize.argtypes = [Time, ctypes.POINTER(Time)]
    lib.mk_time_normalize.restype = ctypes.c_int
    lib.mk_time_add.argtypes = [Time, Time, ctypes.POINTER(Time)]
    lib.mk_time_add.restype = ctypes.c_int
    lib.mk_time_compare.argtypes = [Time, Time]
    lib.mk_time_compare.restype = ctypes.c_int
    lib.mk_project_create.restype = ctypes.c_void_p
    lib.mk_project_destroy.argtypes = [ctypes.c_void_p]
    lib.mk_project_revision.argtypes = [ctypes.c_void_p]
    lib.mk_project_revision.restype = ctypes.c_uint64
    lib.mk_project_add_asset.argtypes = [ctypes.c_void_p, ctypes.c_char_p, Time]
    lib.mk_project_add_asset.restype = ctypes.c_int
    lib.mk_project_append_clip.argtypes = [ctypes.c_void_p, ctypes.c_char_p, Time, Time, Time]
    lib.mk_project_append_clip.restype = ctypes.c_int
    lib.mk_project_propose_trim.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.c_size_t, Time, ctypes.POINTER(ctypes.c_uint64)]
    lib.mk_project_propose_trim.restype = ctypes.c_int
    lib.mk_project_commit.argtypes = [ctypes.c_void_p, ctypes.c_uint64, ctypes.POINTER(ctypes.c_uint64)]
    lib.mk_project_commit.restype = ctypes.c_int
    lib.mk_project_lower_ffmpeg.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    lib.mk_project_lower_ffmpeg.restype = ctypes.c_int
    lib.mk_ffmpeg_version.restype = ctypes.c_uint32
    lib.mk_benchmark.argtypes = [ctypes.c_uint64]
    lib.mk_benchmark.restype = ctypes.c_uint64
    return lib


def scenario(lib):
    n = Time()
    assert lib.mk_time_normalize(Time(2, 4), ctypes.byref(n)) == MK_OK
    assert (n.num, n.den) == (1, 2)
    z = Time()
    assert lib.mk_time_add(Time(1001, 30000), Time(1, 48000), ctypes.byref(z)) == MK_OK
    assert lib.mk_time_compare(z, Time(0, 1)) > 0

    p = lib.mk_project_create()
    assert p
    try:
        assert lib.mk_project_add_asset(p, b"a.mp4", Time(10, 1)) == MK_OK
        assert lib.mk_project_add_asset(p, b"b.mp4", Time(8, 1)) == MK_OK
        assert lib.mk_project_add_asset(p, b"a.mp4", Time(10, 1)) == MK_CONFLICT
        assert lib.mk_project_append_clip(p, b"a.mp4", Time(0, 1), Time(6, 1), Time(0, 1)) == MK_OK
        assert lib.mk_project_append_clip(p, b"b.mp4", Time(0, 1), Time(5, 1), Time(1, 2)) == MK_OK
        assert lib.mk_project_append_clip(p, b"b.mp4", Time(7, 1), Time(5, 1), Time(0, 1)) == MK_INVALID

        proposal = ctypes.c_uint64()
        assert lib.mk_project_propose_trim(p, 0, 0, Time(5, 1), ctypes.byref(proposal)) == MK_OK
        assert lib.mk_project_revision(p) == 0, "candidate proposal mutated committed state"
        revision = ctypes.c_uint64()
        assert lib.mk_project_commit(p, proposal.value, ctypes.byref(revision)) == MK_OK
        assert revision.value == 1 and lib.mk_project_revision(p) == 1

        stale = ctypes.c_uint64()
        assert lib.mk_project_propose_trim(p, 0, 0, Time(4, 1), ctypes.byref(stale)) == MK_CONFLICT

        needed = ctypes.c_size_t()
        assert lib.mk_project_lower_ffmpeg(p, None, 0, ctypes.byref(needed)) == MK_BUFFER_TOO_SMALL
        buf = ctypes.create_string_buffer(needed.value)
        assert lib.mk_project_lower_ffmpeg(p, buf, len(buf), ctypes.byref(needed)) == MK_OK
        lowering = buf.value.decode("utf-8")
        return {
            "lowering": lowering,
            "ffmpeg_version": int(lib.mk_ffmpeg_version()),
            "time_add": [z.num, z.den],
            "revision": int(lib.mk_project_revision(p)),
        }
    finally:
        lib.mk_project_destroy(p)


def benchmark(lib, iterations: int, rounds: int):
    timings = []
    checksums = []
    for _ in range(rounds):
        start = time.perf_counter()
        checksum = int(lib.mk_benchmark(iterations))
        timings.append(time.perf_counter() - start)
        checksums.append(checksum)
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


def line_count(path):
    return sum(1 for line in Path(path).read_text().splitlines() if line.strip())


def text_metrics(path, language):
    text = Path(path).read_text()
    metrics = {"nonblank_loc": line_count(path)}
    if language == "rust":
        metrics["unsafe_occurrences"] = text.count("unsafe")
        metrics["raw_pointer_tokens"] = text.count("*mut ") + text.count("*const ")
    elif language == "cpp":
        metrics["new_delete_occurrences"] = text.count("new ") + text.count("delete ")
        metrics["raw_pointer_markers"] = text.count("*")
    elif language == "zig":
        metrics["manual_memory_occurrences"] = text.count("malloc") + text.count("free(")
        metrics["pointer_cast_occurrences"] = text.count("@ptrCast") + text.count("@alignCast")
    return metrics


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: run_bakeoff.py CPP_SO RUST_SO ZIG_SO")
    libs = {"cpp": Path(sys.argv[1]), "rust": Path(sys.argv[2]), "zig": Path(sys.argv[3])}
    iterations = int(os.environ.get("MK_BENCH_ITERATIONS", "10000000"))
    rounds = int(os.environ.get("MK_BENCH_ROUNDS", "7"))
    source_paths = {
        "cpp": ROOT / "cpp" / "kernel.cpp",
        "rust": ROOT / "rust" / "src" / "lib.rs",
        "zig": ROOT / "zig" / "kernel.zig",
    }
    build_time_paths = {
        "cpp": os.environ.get("MK_CPP_BUILD_TIME", ""),
        "rust": os.environ.get("MK_RUST_BUILD_TIME", ""),
        "zig": os.environ.get("MK_ZIG_BUILD_TIME", ""),
    }

    results = {}
    for name, path in libs.items():
        lib = load(path)
        results[name] = {
            "scenario": scenario(lib),
            "benchmark": benchmark(lib, iterations, rounds),
            "binary_bytes": path.stat().st_size,
            "build_seconds": read_float(build_time_paths[name]) if build_time_paths[name] else None,
            "source": text_metrics(source_paths[name], name),
        }

    lowerings = {v["scenario"]["lowering"] for v in results.values()}
    checksums = {v["benchmark"]["checksum"] for v in results.values()}
    time_adds = {tuple(v["scenario"]["time_add"]) for v in results.values()}
    ffmpeg_versions = {v["scenario"]["ffmpeg_version"] for v in results.values()}
    equivalence = {
        "identical_lowering": len(lowerings) == 1,
        "identical_benchmark_checksum": len(checksums) == 1,
        "identical_exact_time_result": len(time_adds) == 1,
        "identical_ffmpeg_library": len(ffmpeg_versions) == 1,
    }
    assert all(equivalence.values()), equivalence

    payload = {
        "equivalence": equivalence,
        "results": results,
        "notes": {
            "performance": "Synthetic arithmetic benchmark is a runtime sanity check, not a selection criterion.",
            "zig_storage": "The Zig spike uses explicitly bounded project arrays to avoid hiding allocator/stdlib behavior; this is a bakeoff implementation choice, not the proposed production state model.",
            "abi": "All three implementations expose and pass the same C ABI through Python ctypes and call the same system libavformat.",
        },
    }
    Path("bakeoff-results.json").write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        "# Kernel Language Bakeoff — Measured Results",
        "",
        "All three implementations passed the same exact-time, candidate-delta, revision-conflict, semantic-validation, FFmpeg-lowering, C-ABI, and libavformat interop scenario.",
        "",
        "| Metric | C++ | Rust | Zig |",
        "|---|---:|---:|---:|",
    ]
    for label, getter in [
        ("Build seconds", lambda r: r["build_seconds"]),
        ("Stripped shared library bytes", lambda r: r["binary_bytes"]),
        ("Nonblank implementation LOC", lambda r: r["source"]["nonblank_loc"]),
        (f"Median native benchmark seconds ({iterations:,} iterations)", lambda r: r["benchmark"]["median_seconds"]),
    ]:
        vals = []
        for lang in ("cpp", "rust", "zig"):
            v = getter(results[lang])
            vals.append("n/a" if v is None else (f"{v:.6f}" if isinstance(v, float) else str(v)))
        lines.append(f"| {label} | {vals[0]} | {vals[1]} | {vals[2]} |")
    lines += [
        "",
        "## Equivalence checks",
        "",
    ]
    for key, value in equivalence.items():
        lines.append(f"- {key}: {'PASS' if value else 'FAIL'}")
    lines += [
        "",
        "## Important interpretation limits",
        "",
        "- Performance numbers only establish that none of the candidates has a disqualifying native-runtime problem in this slice.",
        "- The state model is intentionally tiny; the selection must weight ownership safety, semantic expressiveness, ecosystem interop, build maturity, and ABI design more heavily than microbenchmark rank.",
        "- Zig's spike uses bounded arrays, making its memory-management style unusually explicit. A production Zig implementation would need an allocator/arena policy and would likely grow more manual ownership code.",
    ]
    Path("bakeoff-results.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(payload, indent=2))

if __name__ == "__main__":
    main()
