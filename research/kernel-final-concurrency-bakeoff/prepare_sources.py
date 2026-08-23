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
