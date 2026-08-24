#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify.py /path/to/odin-encoder")

    subprocess.run([sys.executable, str(Path(__file__).with_name("reference.py"))], check=True)
    py = json.loads(Path("canonical-cbor-python.json").read_text())

    proc = subprocess.run([str(Path(sys.argv[1]).resolve())], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout)
    print(proc.stdout, end="")
    lines = [x for x in proc.stdout.splitlines() if x.startswith("ODIN_HEX ")]
    if len(lines) != 1:
        raise AssertionError(proc.stdout)
    odin_hex = lines[0].split(" ", 1)[1].strip()
    if odin_hex != py["hex"]:
        raise AssertionError(f"canonical byte mismatch\npython={py['hex']}\nodin={odin_hex}")

    raw = bytes.fromhex(odin_hex)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != py["sha256"]:
        raise AssertionError((digest, py["sha256"]))

    result = {
        "cross_language_bytes_equal": True,
        "sha256": digest,
        "byte_length": len(raw),
        "python_insertion_order_independent": py["insertion_order_independent"],
        "float_rejected": py["float_rejected"],
        "profile": "media-kernel-deterministic-cbor-v0",
    }
    Path("canonical-cbor-conformance.json").write_text(json.dumps(result, indent=2) + "\n")
    print("CROSS_LANGUAGE_CBOR_PASS")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
