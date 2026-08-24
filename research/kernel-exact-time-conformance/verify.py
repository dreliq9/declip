#!/usr/bin/env python3
import ctypes
from fractions import Fraction
import json
import math
import random
import sys
from pathlib import Path

I64_MIN = -(1 << 63)
I64_MAX = (1 << 63) - 1
OK, INVALID, OVERFLOW, INEXACT = 0, 1, 2, 3


class Time(ctypes.Structure):
    _fields_ = [("value", ctypes.c_int64), ("scale", ctypes.c_int64)]

    def pair(self):
        return (int(self.value), int(self.scale))


def representable(f: Fraction) -> bool:
    return I64_MIN <= f.numerator <= I64_MAX and 1 <= f.denominator <= I64_MAX


def canonical(f: Fraction):
    return (f.numerator, f.denominator)


def bind(lib):
    ptime = ctypes.POINTER(Time)
    pi64 = ctypes.POINTER(ctypes.c_int64)
    pi32 = ctypes.POINTER(ctypes.c_int32)

    lib.mk_time_make.argtypes = [ctypes.c_int64, ctypes.c_int64, ptime]
    lib.mk_time_make.restype = ctypes.c_int
    lib.mk_time_add.argtypes = [Time, Time, ptime]
    lib.mk_time_add.restype = ctypes.c_int
    lib.mk_time_sub.argtypes = [Time, Time, ptime]
    lib.mk_time_sub.restype = ctypes.c_int
    lib.mk_time_compare.argtypes = [Time, Time, pi32]
    lib.mk_time_compare.restype = ctypes.c_int
    lib.mk_time_ticks_exact.argtypes = [Time, ctypes.c_int64, pi64]
    lib.mk_time_ticks_exact.restype = ctypes.c_int
    lib.mk_time_from_rate_index.argtypes = [ctypes.c_int64, ctypes.c_int64, ctypes.c_int64, ptime]
    lib.mk_time_from_rate_index.restype = ctypes.c_int
    lib.mk_time_range_end.argtypes = [Time, Time, ptime]
    lib.mk_time_range_end.restype = ctypes.c_int
    lib.mk_time_range_contains.argtypes = [Time, Time, Time, pi32]
    lib.mk_time_range_contains.restype = ctypes.c_int


def mk(lib, value, scale):
    out = Time()
    status = lib.mk_time_make(value, scale, ctypes.byref(out))
    return status, out


def add(lib, a, b, subtract=False):
    out = Time()
    fn = lib.mk_time_sub if subtract else lib.mk_time_add
    status = fn(a, b, ctypes.byref(out))
    return status, out


def from_rate(lib, index, num, den):
    out = Time()
    status = lib.mk_time_from_rate_index(index, num, den, ctypes.byref(out))
    return status, out


def assert_time(actual: Time, expected: Fraction, label=""):
    got = actual.pair()
    want = canonical(expected)
    if got != want:
        raise AssertionError(f"{label}: got {got}, want {want}")


def expected_status(f: Fraction):
    return OK if representable(f) else OVERFLOW


def test_construction(lib, rng):
    vectors = [
        (0, 1), (0, 48000), (1, 1), (2, 4), (-2, 4),
        (48000, 48000), (I64_MAX, 1), (I64_MIN, 1),
        (1, I64_MAX), (-1, I64_MAX),
    ]
    for _ in range(5000):
        vectors.append((rng.randint(-10**15, 10**15), rng.choice(SCALES)))
    for value, scale in vectors:
        status, out = mk(lib, value, scale)
        if status != OK:
            raise AssertionError(("construct", value, scale, status))
        assert_time(out, Fraction(value, scale), "construct")
    out = Time()
    for bad_scale in [0, -1, -48000, I64_MIN]:
        if lib.mk_time_make(1, bad_scale, ctypes.byref(out)) != INVALID:
            raise AssertionError(("invalid scale accepted", bad_scale))


def test_add_sub_compare(lib, rng):
    for _ in range(25000):
        av = rng.randint(-10**12, 10**12)
        bv = rng.randint(-10**12, 10**12)
        ascale = rng.choice(SCALES)
        bscale = rng.choice(SCALES)
        a = Time(av, ascale)
        b = Time(bv, bscale)
        af = Fraction(av, ascale)
        bf = Fraction(bv, bscale)
        for subtract in (False, True):
            want = af - bf if subtract else af + bf
            status, out = add(lib, a, b, subtract)
            exp_status = expected_status(want)
            if status != exp_status:
                raise AssertionError(("add/sub status", a.pair(), b.pair(), subtract, status, exp_status, want))
            if status == OK:
                assert_time(out, want, "add/sub")
        cmp_out = ctypes.c_int32()
        status = lib.mk_time_compare(a, b, ctypes.byref(cmp_out))
        if status != OK:
            raise AssertionError(("compare status", status))
        want_cmp = -1 if af < bf else 1 if af > bf else 0
        if cmp_out.value != want_cmp:
            raise AssertionError(("compare", af, bf, cmp_out.value, want_cmp))

    # Explicit result-overflow cases.
    status, _ = add(lib, Time(I64_MAX, 1), Time(1, 1))
    if status != OVERFLOW:
        raise AssertionError(("positive overflow", status))
    status, _ = add(lib, Time(I64_MIN, 1), Time(1, 1), subtract=True)
    if status != OVERFLOW:
        raise AssertionError(("negative overflow", status))

    # Coprime large scales make the exact denominator exceed the ABI domain.
    a = Time(1, 4_000_000_007)
    b = Time(1, 4_000_000_009)
    want = Fraction(1, a.scale) + Fraction(1, b.scale)
    if representable(want):
        raise AssertionError("test vector unexpectedly representable")
    status, _ = add(lib, a, b)
    if status != OVERFLOW:
        raise AssertionError(("denominator overflow", status, want))


def test_exact_ticks(lib, rng):
    for _ in range(12000):
        value = rng.randint(-10**9, 10**9)
        scale = rng.choice(SCALES)
        target = rng.choice(SCALES)
        t = Time(value, scale)
        f = Fraction(value, scale)
        exact = f * target
        out = ctypes.c_int64()
        status = lib.mk_time_ticks_exact(t, target, ctypes.byref(out))
        if exact.denominator != 1:
            if status != INEXACT:
                raise AssertionError(("expected inexact", f, target, status))
        elif not (I64_MIN <= exact.numerator <= I64_MAX):
            if status != OVERFLOW:
                raise AssertionError(("expected tick overflow", f, target, status))
        else:
            if status != OK or out.value != exact.numerator:
                raise AssertionError(("exact ticks", f, target, status, out.value, exact))

    # Semantic conversion never rounds implicitly.
    out = ctypes.c_int64()
    if lib.mk_time_ticks_exact(Time(1, 3), 1000, ctypes.byref(out)) != INEXACT:
        raise AssertionError("1/3 second silently rounded to milliseconds")


def test_rates_and_alignment(lib, rng):
    rates = [
        (24, 1), (25, 1), (30, 1),
        (24000, 1001), (30000, 1001), (60000, 1001),
        (44100, 1), (48000, 1), (96000, 1),
    ]
    for num, den in rates:
        for index in [I for I in (-100000, -1, 0, 1, 2, 10, 1001, 100000, 1_000_000)]:
            status, out = from_rate(lib, index, num, den)
            want = Fraction(index * den, num)
            exp_status = expected_status(want)
            if status != exp_status:
                raise AssertionError(("rate status", index, num, den, status, exp_status))
            if status == OK:
                assert_time(out, want, "rate")

    # Random rational rates.
    for _ in range(8000):
        num = rng.randint(1, 2_000_000)
        den = rng.randint(1, 10000)
        index = rng.randint(-10**10, 10**10)
        status, out = from_rate(lib, index, num, den)
        want = Fraction(index * den, num)
        exp_status = expected_status(want)
        if status != exp_status:
            raise AssertionError(("random rate status", index, num, den, status, exp_status, want))
        if status == OK:
            assert_time(out, want, "random rate")

    # Known exact video/audio alignment periods.
    alignment = [
        ((24000, 1001), 1, 48000, 2002),
        ((30000, 1001), 5, 48000, 8008),
        ((60000, 1001), 5, 48000, 4004),
        ((24000, 1001), 80, 44100, 147147),
    ]
    for (num, den), frames, sample_scale, expected_samples in alignment:
        status, t = from_rate(lib, frames, num, den)
        if status != OK:
            raise AssertionError(("alignment rate", status))
        ticks = ctypes.c_int64()
        status = lib.mk_time_ticks_exact(t, sample_scale, ctypes.byref(ticks))
        if status != OK or ticks.value != expected_samples:
            raise AssertionError(("alignment", num, den, frames, sample_scale, status, ticks.value, expected_samples))

    # Long sample-index timelines remain exact.
    seven_days = 7 * 24 * 60 * 60
    sample_index = seven_days * 48000
    status, t = from_rate(lib, sample_index, 48000, 1)
    if status != OK:
        raise AssertionError(("seven day timeline", status))
    assert_time(t, Fraction(seven_days, 1), "seven days")


def test_repeated_arithmetic(lib):
    status, frame = from_rate(lib, 1, 24000, 1001)
    if status != OK:
        raise AssertionError(status)
    acc = Time(0, 1)
    count = 20000
    for _ in range(count):
        status, acc = add(lib, acc, frame)
        if status != OK:
            raise AssertionError(("repeated add", status))
    status, direct = from_rate(lib, count, 24000, 1001)
    if status != OK:
        raise AssertionError(status)
    if acc.pair() != direct.pair():
        raise AssertionError(("drift", acc.pair(), direct.pair()))


def test_ranges(lib, rng):
    for _ in range(8000):
        sf = Fraction(rng.randint(-10**6, 10**6), rng.choice(SMALL_SCALES))
        df = Fraction(rng.randint(0, 10**6), rng.choice(SMALL_SCALES))
        tf = Fraction(rng.randint(-10**6, 10**6), rng.choice(SMALL_SCALES))
        start = Time(sf.numerator, sf.denominator)
        duration = Time(df.numerator, df.denominator)
        t = Time(tf.numerator, tf.denominator)
        end = Time()
        status = lib.mk_time_range_end(start, duration, ctypes.byref(end))
        want_end = sf + df
        exp_status = expected_status(want_end)
        if status != exp_status:
            raise AssertionError(("range end status", sf, df, status, exp_status))
        if status != OK:
            continue
        assert_time(end, want_end, "range end")
        contains = ctypes.c_int32()
        status = lib.mk_time_range_contains(start, duration, t, ctypes.byref(contains))
        if status != OK:
            raise AssertionError(("range contains status", status))
        want = df > 0 and sf <= tf < want_end
        if bool(contains.value) != want:
            raise AssertionError(("half-open range", sf, df, tf, contains.value, want))

    contains = ctypes.c_int32()
    if lib.mk_time_range_contains(Time(0, 1), Time(-1, 1), Time(0, 1), ctypes.byref(contains)) != INVALID:
        raise AssertionError("negative duration accepted")


def frame_to_drop_tc(frame_number: int, nominal_fps: int, drop_frames: int):
    # SMPTE drop-frame is a numbering convention only. Underlying media time is unchanged.
    frames_per_10_minutes = nominal_fps * 60 * 10 - drop_frames * 9
    frames_per_minute = nominal_fps * 60 - drop_frames
    frames_per_24_hours = frames_per_10_minutes * 6 * 24
    n = frame_number % frames_per_24_hours
    ten_min_blocks, remainder = divmod(n, frames_per_10_minutes)
    adjusted = n + drop_frames * 9 * ten_min_blocks
    if remainder >= drop_frames:
        adjusted += drop_frames * ((remainder - drop_frames) // frames_per_minute)
    hours, rem = divmod(adjusted, nominal_fps * 3600)
    minutes, rem = divmod(rem, nominal_fps * 60)
    seconds, frames = divmod(rem, nominal_fps)
    return hours, minutes, seconds, frames


def test_drop_frame_presentation():
    vectors = [
        (30000, 1001, 30, 2, 0, (0, 0, 0, 0)),
        (30000, 1001, 30, 2, 17982, (0, 10, 0, 0)),
        (30000, 1001, 30, 2, 107892, (1, 0, 0, 0)),
        (60000, 1001, 60, 4, 35964, (0, 10, 0, 0)),
        (60000, 1001, 60, 4, 215784, (1, 0, 0, 0)),
    ]
    for _, _, nominal, drop, frame, want in vectors:
        got = frame_to_drop_tc(frame, nominal, drop)
        if got != want:
            raise AssertionError(("drop-frame", frame, got, want))

    # At non-tenth minute boundaries, the dropped labels are never emitted.
    for nominal, drop, count in [(30, 2, 200000), (60, 4, 400000)]:
        step = 137
        for frame in range(0, count, step):
            h, m, s, f = frame_to_drop_tc(frame, nominal, drop)
            if m % 10 != 0 and s == 0 and f < drop:
                raise AssertionError(("illegal drop-frame label", nominal, frame, (h, m, s, f)))


def test_vfr_and_external_grids(lib):
    # VFR PTS remain exact values; cadence is not inferred from a single project FPS.
    pts = [Fraction(0, 1), Fraction(33366667, 10**9), Fraction(66733334, 10**9), Fraction(100100001, 10**9)]
    canonical_pts = []
    for p in pts:
        status, t = mk(lib, p.numerator, p.denominator)
        if status != OK:
            raise AssertionError(("VFR PTS", p, status))
        assert_time(t, p, "VFR")
        canonical_pts.append(t)
    for a, b in zip(canonical_pts, canonical_pts[1:]):
        cmp_out = ctypes.c_int32()
        if lib.mk_time_compare(a, b, ctypes.byref(cmp_out)) != OK or cmp_out.value >= 0:
            raise AssertionError("VFR PTS ordering failed")

    # Nanosecond external timestamps can coexist with 44.1 kHz sample times; their
    # sum may require a large denominator but remains well inside the i64-scale ABI.
    ns = Fraction(1, 10**9)
    sample = Fraction(1, 44100)
    status, out = add(lib, Time(ns.numerator, ns.denominator), Time(sample.numerator, sample.denominator))
    want = ns + sample
    if not representable(want):
        raise AssertionError("expected mixed ns/sample rational to fit")
    if status != OK:
        raise AssertionError(("mixed external/sample grid", status, want))
    assert_time(out, want, "mixed external/sample grid")


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: verify.py /path/to/libexact_time.so")
    lib = ctypes.CDLL(str(Path(sys.argv[1]).resolve()))
    bind(lib)
    rng = random.Random(0x5EED5EED)

    tests = [
        ("construction", lambda: test_construction(lib, rng)),
        ("add_sub_compare", lambda: test_add_sub_compare(lib, rng)),
        ("exact_ticks", lambda: test_exact_ticks(lib, rng)),
        ("rates_alignment", lambda: test_rates_and_alignment(lib, rng)),
        ("repeated_arithmetic", lambda: test_repeated_arithmetic(lib)),
        ("ranges", lambda: test_ranges(lib, rng)),
        ("drop_frame_presentation", test_drop_frame_presentation),
        ("vfr_external_grids", lambda: test_vfr_and_external_grids(lib)),
    ]
    results = {}
    for name, fn in tests:
        fn()
        results[name] = "PASS"
        print(f"PASS {name}")
    results["random_seed"] = "0x5EED5EED"
    results["representation"] = "normalized signed i64 numerator + positive i64 scale"
    Path("exact-time-results.json").write_text(json.dumps(results, indent=2) + "\n")
    print("EXACT_TIME_CONFORMANCE_PASS")


SMALL_SCALES = [1, 24, 25, 30, 1000, 1001, 24000, 30000, 44100, 48000, 60000, 90000, 1_000_000]
SCALES = SMALL_SCALES + [
    1_000_000_000,
    4_000_000_007,
    4_000_000_009,
    999_999_996_989,
    1_000_000_000_039,
    2_147_483_647,
    9_223_372_036_854_775_123,
]

if __name__ == "__main__":
    main()
