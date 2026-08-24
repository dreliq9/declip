#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _head(major: int, n: int) -> bytes:
    if n < 0:
        raise ValueError(n)
    prefix = major << 5
    if n < 24:
        return bytes([prefix | n])
    if n <= 0xFF:
        return bytes([prefix | 24, n])
    if n <= 0xFFFF:
        return bytes([prefix | 25]) + n.to_bytes(2, "big")
    if n <= 0xFFFFFFFF:
        return bytes([prefix | 26]) + n.to_bytes(4, "big")
    if n <= 0xFFFFFFFFFFFFFFFF:
        return bytes([prefix | 27]) + n.to_bytes(8, "big")
    raise OverflowError(n)


def encode(value) -> bytes:
    if value is False:
        return b"\xf4"
    if value is True:
        return b"\xf5"
    if value is None:
        return b"\xf6"
    if isinstance(value, int):
        if value >= 0:
            return _head(0, value)
        return _head(1, -1 - value)
    if isinstance(value, bytes):
        return _head(2, len(value)) + value
    if isinstance(value, str):
        raw = value.encode("utf-8")
        return _head(3, len(raw)) + raw
    if isinstance(value, (list, tuple)):
        return _head(4, len(value)) + b"".join(encode(v) for v in value)
    if isinstance(value, dict):
        pairs = [(encode(k), encode(v)) for k, v in value.items()]
        key_bytes = [k for k, _ in pairs]
        if len(key_bytes) != len(set(key_bytes)):
            raise ValueError("duplicate canonical map key")
        pairs.sort(key=lambda kv: kv[0])
        return _head(5, len(pairs)) + b"".join(k + v for k, v in pairs)
    if isinstance(value, float):
        raise TypeError("floating point forbidden in canonical semantic profile v0")
    raise TypeError(type(value))


def id16(start: int) -> bytes:
    return bytes(range(start, start + 16))


def clip(clip_id: bytes, asset_id: bytes, start, source_in, duration, future: str):
    return {
        99: future,  # intentionally inserted first/out of canonical key order
        6: duration,
        5: source_in,
        4: start,
        3: asset_id,
        2: clip_id,
        1: 1,
        0: "media.editorial.clip",
    }


def fixture(reverse_insertion: bool = False):
    clips = [
        clip(id16(0x20), id16(0x40), [11499, 2500], [2, 1], [5, 1], "future-b"),
        clip(id16(0x10), id16(0x30), [0, 1], [0, 1], [5, 1], "future-a"),
    ]
    clips.sort(key=lambda c: c[2])
    items = [
        (3, clips),
        (2, id16(0x00)),
        (1, 1),
        (0, "media.state.snapshot"),
    ]
    if reverse_insertion:
        items.reverse()
    return dict(items)


def main():
    a = encode(fixture(False))
    b = encode(fixture(True))
    if a != b:
        raise AssertionError("map insertion order changed canonical bytes")

    try:
        encode(1.25)
    except TypeError:
        pass
    else:
        raise AssertionError("float unexpectedly accepted")

    digest = hashlib.sha256(a).hexdigest()
    print("PY_HEX", a.hex())
    print("PY_SHA256", digest)

    result = {
        "hex": a.hex(),
        "sha256": digest,
        "byte_length": len(a),
        "type": "media.state.snapshot",
        "schema_version": 1,
        "float_rejected": True,
        "insertion_order_independent": True,
    }
    Path("canonical-cbor-python.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
