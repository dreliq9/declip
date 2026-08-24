#!/usr/bin/env python3
import ctypes
from fractions import Fraction
from pathlib import Path
import sys

import verify


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify_extremes.py /path/to/libexact_time.so")
    lib = ctypes.CDLL(str(Path(sys.argv[1]).resolve()))
    verify.bind(lib)

    values = [
        verify.I64_MIN,
        verify.I64_MIN + 1,
        -(1 << 62),
        -1,
        0,
        1,
        (1 << 62),
        verify.I64_MAX - 1,
        verify.I64_MAX,
    ]
    scales = [
        1,
        2,
        1001,
        44100,
        1_000_000_000,
        4_000_000_007,
        1_000_000_000_039,
        verify.I64_MAX - 1000,
        verify.I64_MAX - 2,
        verify.I64_MAX,
    ]

    cases = 0
    for av in values:
        for bv in values:
            for ascale in scales:
                for bscale in scales:
                    a = verify.Time(av, ascale)
                    b = verify.Time(bv, bscale)
                    af = Fraction(av, ascale)
                    bf = Fraction(bv, bscale)
                    for subtract in (False, True):
                        want = af - bf if subtract else af + bf
                        status, out = verify.add(lib, a, b, subtract)
                        expected = verify.expected_status(want)
                        if status != expected:
                            raise AssertionError(("extreme status", a.pair(), b.pair(), subtract, status, expected, want))
                        if status == verify.OK:
                            verify.assert_time(out, want, "extreme arithmetic")
                        cases += 1
                    cmp_out = ctypes.c_int32()
                    status = lib.mk_time_compare(a, b, ctypes.byref(cmp_out))
                    if status != verify.OK:
                        raise AssertionError(("extreme compare status", a.pair(), b.pair(), status))
                    expected_cmp = -1 if af < bf else 1 if af > bf else 0
                    if cmp_out.value != expected_cmp:
                        raise AssertionError(("extreme compare", a.pair(), b.pair(), cmp_out.value, expected_cmp))
                    cases += 1

    print(f"EXTREME_DOMAIN_PASS cases={cases}")


if __name__ == "__main__":
    main()
