#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parent

replacements = {
    ROOT / "cpp" / "main.cpp": [
        (
            "cv_work.wait(lock, [&]{ return shutdown || !queue.empty() || (producers_done && terminal == result.submitted); });",
            "cv_work.wait(lock, [&]{ return shutdown || !queue.empty() || producers_done; });",
        ),
        (
            "if (queue.empty()) {\n                    if (producers_done && terminal == result.submitted) return;\n                    continue;\n                }",
            "if (queue.empty()) {\n                    if (producers_done) return;\n                    continue;\n                }",
        ),
    ],
    ROOT / "rust" / "src" / "main.rs": [
        (
            "while !s.shutdown && s.queue.is_empty() && !(s.producers_done && s.terminal == s.result.submitted) {",
            "while !s.shutdown && s.queue.is_empty() && !s.producers_done {",
        ),
        (
            "if s.producers_done && s.terminal == s.result.submitted { return; }",
            "if s.producers_done { return; }",
        ),
    ],
    ROOT / "odin" / "main.odin": [
        (
            "for !k.shutdown && k.queue_count == 0 && !(k.producers_done && k.terminal == k.result.submitted) {",
            "for !k.shutdown && k.queue_count == 0 && !k.producers_done {",
        ),
        (
            "done := k.producers_done && k.terminal == k.result.submitted",
            "done := k.producers_done",
        ),
    ],
    ROOT / "zig" / "main.zig": [
        (
            "while (!k.shutdown and k.queue_count == 0 and !(k.producers_done and k.terminal == k.result.submitted)) {",
            "while (!k.shutdown and k.queue_count == 0 and !k.producers_done) {",
        ),
        (
            "const done = k.producers_done and k.terminal == k.result.submitted;",
            "const done = k.producers_done;",
        ),
        (
            "for (handles) |h| if (validLocked(&k, h) and !releaseLocked(&k, h)) k.result.violations += 1;",
            "for (handles) |h| {\n        if (validLocked(&k, h) and !releaseLocked(&k, h)) k.result.violations += 1;\n    }",
        ),
        (
            "for (&k.resources) |*r| if (r.alive or r.refs != 0) { k.result.leaked_resources += 1; };",
            "for (&k.resources) |*r| {\n        if (r.alive or r.refs != 0) k.result.leaked_resources += 1;\n    }",
        ),
        (
            "for (handles) |h| if (validLocked(&k, h)) { k.result.stale_accepts += 1; };",
            "for (handles) |h| {\n        if (validLocked(&k, h)) k.result.stale_accepts += 1;\n    }",
        ),
        (
            "export fn main(argc: c_int, argv: [*]const [*:0]const u8) c_int {",
            "pub export fn main(argc: c_int, argv: [*]const [*:0]const u8) c_int {",
        ),
        (
            "    const start = std.time.nanoTimestamp();\n    const r = runCase(seed, workers, producers, ops, qcap, loss) catch return 3;\n    const elapsed_ns = std.time.nanoTimestamp() - start;\n    const seconds = @as(f64, @floatFromInt(elapsed_ns)) / 1_000_000_000.0;",
            "    const r = runCase(seed, workers, producers, ops, qcap, loss) catch return 3;\n    const seconds: f64 = 0.0;",
        ),
    ],
}

for path, pairs in replacements.items():
    text = path.read_text()
    for old, new in pairs:
        if old not in text:
            raise SystemExit(f"expected source fragment missing in {path}: {old}")
        text = text.replace(old, new, 1)
    path.write_text(text)
    print(f"prepared {path.relative_to(ROOT)}")
