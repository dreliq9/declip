#!/usr/bin/env python3
import json
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

RESULT_RE = re.compile(r"\b([A-Za-z_]+)=([^\s]+)")


def run_case(exe: Path, seed: int, workers: int, producers: int, ops: int, qcap: int, loss: int):
    started = time.perf_counter()
    proc = subprocess.run(
        [str(exe.resolve()), str(seed), str(workers), str(producers), str(ops), str(qcap), str(loss)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=45,
    )
    elapsed = time.perf_counter() - started
    lines = [line for line in proc.stdout.splitlines() if line.startswith("RESULT ")]
    if proc.returncode != 0 or len(lines) != 1:
        raise RuntimeError(f"{exe.name} failed rc={proc.returncode}\n{proc.stdout}")
    row = {m.group(1): m.group(2) for m in RESULT_RE.finditer(lines[0])}
    ints = ["seed", "workers", "producers", "ops", "loss", "submitted", "completed", "cancelled", "lost", "backpressure", "max_queue", "retain", "release", "stale_accepts", "leaked", "violations"]
    for key in ints:
        row[key] = int(row[key])
    row["reported_seconds"] = float(row["seconds"])
    row["seconds"] = elapsed
    if row["violations"] != 0 or row["stale_accepts"] != 0 or row["leaked"] != 0:
        raise AssertionError(row)
    if row["completed"] + row["cancelled"] + row["lost"] != row["submitted"]:
        raise AssertionError(("terminal accounting", row))
    if row["max_queue"] > qcap:
        raise AssertionError(("queue bound", row))
    if loss == 0 and row["submitted"] != producers * ops:
        raise AssertionError(("normal submit loss", row))
    if loss == 1 and row["lost"] == 0:
        raise AssertionError(("device loss did not exercise loss path", row))
    return row


def main():
    if len(sys.argv) != 5:
        raise SystemExit("usage: run_gate.py CPP RUST ZIG ODIN")
    executables = dict(zip(["cpp", "rust", "zig", "odin"], map(Path, sys.argv[1:])))
    seeds = [1, 424242, 987654321]
    workers_set = [1, 2, 4, 8]
    producers = 4
    ops = 250
    qcap = 16
    all_rows = []
    by_lang = {}
    for lang, exe in executables.items():
        rows = []
        for seed in seeds:
            for workers in workers_set:
                for loss in [0, 1]:
                    row = run_case(exe, seed, workers, producers, ops, qcap, loss)
                    rows.append(row)
                    all_rows.append(row)
        normal = [r for r in rows if r["loss"] == 0]
        loss_rows = [r for r in rows if r["loss"] == 1]
        if sum(r["backpressure"] for r in normal) == 0:
            raise AssertionError(f"{lang}: bounded queue never produced backpressure")
        by_lang[lang] = {
            "cases": len(rows),
            "median_seconds": statistics.median(r["seconds"] for r in rows),
            "median_normal_seconds": statistics.median(r["seconds"] for r in normal),
            "median_loss_seconds": statistics.median(r["seconds"] for r in loss_rows),
            "total_submitted": sum(r["submitted"] for r in rows),
            "total_completed": sum(r["completed"] for r in rows),
            "total_cancelled": sum(r["cancelled"] for r in rows),
            "total_lost": sum(r["lost"] for r in rows),
            "total_backpressure_waits": sum(r["backpressure"] for r in rows),
            "max_queue_observed": max(r["max_queue"] for r in rows),
            "violations": sum(r["violations"] for r in rows),
            "stale_accepts": sum(r["stale_accepts"] for r in rows),
            "leaked_resources": sum(r["leaked"] for r in rows),
        }
    payload = {
        "matrix": {"seeds": seeds, "workers": workers_set, "producers": producers, "ops_per_producer": ops, "queue_capacity": qcap, "device_loss_modes": [0, 1]},
        "languages": by_lang,
        "case_count": len(all_rows),
    }
    Path("final-concurrency-results.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
