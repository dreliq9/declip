#!/usr/bin/env python3
import json
import re
import subprocess
import sys
from pathlib import Path

PAIR_RE = re.compile(r"([A-Za-z_]+)=([^\s]+)")


def parse_line(line):
    return {m.group(1): int(m.group(2)) for m in PAIR_RE.finditer(line)}


def region_metrics(source, start_marker, end_marker):
    start = source.index(start_marker) + len(start_marker)
    end = source.index(end_marker)
    region = source[start:end]
    lines = [line for line in region.splitlines() if line.strip()]
    return {
        "nonblank_loc": len(lines),
        "bytes": len(region.encode("utf-8")),
        "find_attr_calls": region.count("find_attr("),
        "switch_sites": region.count("switch "),
        "typed_struct_declarations": region.count(":: struct"),
    }


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: verify.py /path/to/ir-spike-exe /path/to/main.odin")
    exe = Path(sys.argv[1]).resolve()
    source_path = Path(sys.argv[2]).resolve()
    proc = subprocess.run([str(exe)], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
    if proc.returncode != 0:
        raise RuntimeError(proc.stdout)
    print(proc.stdout, end="")
    result_lines = [line for line in proc.stdout.splitlines() if line.startswith("RESULT ")]
    negative_lines = [line for line in proc.stdout.splitlines() if line.startswith("NEGATIVE ")]
    if len(result_lines) != 1 or len(negative_lines) != 1:
        raise AssertionError(proc.stdout)
    result = parse_line(result_lines[0])
    negative = parse_line(negative_lines[0])

    required_one = [
        "typed_valid", "generic_valid", "typed_full_ok", "generic_full_ok",
        "typed_fallback_ok", "generic_fallback_ok",
    ]
    for key in required_one:
        if result.get(key) != 1:
            raise AssertionError((key, result.get(key)))

    if result["typed_sem"] == 0 or result["typed_sem"] != result["generic_sem"]:
        raise AssertionError(("semantic hash mismatch", result))
    if result["typed_full_hash"] == 0 or result["typed_full_hash"] != result["generic_full_hash"]:
        raise AssertionError(("full plan mismatch", result))
    if result["typed_fallback_hash"] == 0 or result["typed_fallback_hash"] != result["generic_fallback_hash"]:
        raise AssertionError(("fallback plan mismatch", result))
    if result["typed_full_loss"] != 0 or result["generic_full_loss"] != 0:
        raise AssertionError(("full target should be exact", result))
    if result["typed_fallback_loss"] != 1 or result["generic_fallback_loss"] != 1:
        raise AssertionError(("fallback should report baked editability loss", result))
    if result["exec_nodes_full"] != 11 or result["exec_nodes_fallback"] != 11:
        raise AssertionError(("unexpected node count", result))

    for key in [
        "typed_oob_rejected", "generic_oob_rejected",
        "typed_transition_rejected", "generic_transition_rejected",
        "generic_missing_removed", "generic_missing_rejected",
        "typed_missing_attr_structurally_impossible",
    ]:
        if negative.get(key) != 1:
            raise AssertionError((key, negative.get(key)))

    source = source_path.read_text()
    typed = region_metrics(source, "// BEGIN_TYPED_EDITORIAL", "// END_TYPED_EDITORIAL")
    generic = region_metrics(source, "// BEGIN_GENERIC_EDITORIAL", "// END_GENERIC_EDITORIAL")

    payload = {
        "semantic_equivalence": True,
        "full_lowering_equivalence": True,
        "fallback_lowering_equivalence": True,
        "full_loss": "EXACT",
        "fallback_loss": "BAKED_LOSS_OF_EDITABILITY",
        "negative_cases": negative,
        "execution_nodes": result["exec_nodes_full"],
        "typed_editorial": typed,
        "generalized_editorial": generic,
        "observations": {
            "typed_missing_required_field": "structurally present; semantic invalidity still requires verification",
            "generic_missing_required_field": "representable and rejected only after attribute-schema verification",
            "both_lower_to_same_exec_ir": True,
        },
    }
    Path("ir-architecture-results.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    print("IR_ARCHITECTURE_SPIKE_PASS")


if __name__ == "__main__":
    main()
