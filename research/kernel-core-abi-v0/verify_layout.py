#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path


def run(exe: str):
    p = subprocess.run([str(Path(exe).resolve())], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=20)
    if p.returncode != 0:
        raise RuntimeError(f"{exe} failed rc={p.returncode}\n{p.stdout}")
    types = {}
    fields = {}
    for line in p.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "TYPE" and len(parts) == 4:
            types[parts[1]] = {"size": int(parts[2]), "align": int(parts[3])}
        elif parts[0] == "FIELD" and len(parts) == 4:
            fields[f"{parts[1]}.{parts[2]}"] = int(parts[3])
    return {"types": types, "fields": fields, "raw": p.stdout}


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: verify_layout.py C_LAYOUT CPP_LAYOUT ODIN_LAYOUT")
    names = ["c", "cpp", "odin"]
    results = {name: run(exe) for name, exe in zip(names, sys.argv[1:])}
    baseline = results["c"]
    if not baseline["types"] or not baseline["fields"]:
        raise AssertionError("C layout probe produced no data")
    for name in ["cpp", "odin"]:
        if results[name]["types"] != baseline["types"]:
            raise AssertionError((f"type-layout mismatch {name}", baseline["types"], results[name]["types"]))
        if results[name]["fields"] != baseline["fields"]:
            raise AssertionError((f"field-offset mismatch {name}", baseline["fields"], results[name]["fields"]))

    required_sizes = {
        "mk_abi_version": 8,
        "mk_struct_header": 8,
        "mk_id128": 16,
        "mk_content_hash": 40,
        "mk_media_time": 16,
        "mk_media_rate": 16,
        "mk_time_range": 32,
        "mk_wall_time": 16,
        "mk_decimal64": 16,
        "mk_money": 24,
        "mk_bytes_view": 16,
        "mk_string_view": 16,
        "mk_resource_handle": 16,
    }
    for t, size in required_sizes.items():
        got = baseline["types"].get(t, {}).get("size")
        if got != size:
            raise AssertionError(("fixed leaf size", t, got, size))

    # All public tested structures should stay naturally aligned; no packed ABI.
    for t, info in baseline["types"].items():
        if info["align"] not in (4, 8):
            raise AssertionError(("unexpected public alignment", t, info))

    payload = {
        "layout_equivalent": True,
        "languages": names,
        "type_count": len(baseline["types"]),
        "field_offset_count": len(baseline["fields"]),
        "types": baseline["types"],
        "fields": baseline["fields"],
        "notes": {
            "raw_struct_bytes_are_not_serialization": True,
            "pointer_views_are_in_process_only": True,
            "tested_pointer_width_bits": 64,
        },
    }
    Path("core-abi-layout-results.json").write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(payload, indent=2))
    print("CORE_ABI_LAYOUT_PASS")


if __name__ == "__main__":
    main()
