# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""P2.4: property-based suites per specification on the software targets (Hypothesis)."""
import ctypes
import sys
from pathlib import Path

from hypothesis import given, settings, strategies as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from repsynth.numeric import spec_of, oracle_for  # noqa: E402

LIBDIR = Path(__import__("os").environ.get("REPSYNTH_LIBDIR", ROOT / "out" / "software"))


def lib(sid):
    l = ctypes.CDLL(str(LIBDIR / sid / f"lib{sid}.so"))
    def f(name):
        fn = getattr(l, name); fn.restype = ctypes.c_uint64; fn.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
        return fn
    return f

BT, BIN, PD = lib("balanced_ternary"), lib("binary_integer"), lib("packed_decimal")
bt32 = oracle_for("balanced_ternary", spec_of("balanced_ternary"), 32)
H32 = bt32.H
bt_vals = st.integers(min_value=-H32, max_value=H32)
i64 = st.integers(min_value=-(2**63), max_value=2**63 - 1)
pdv = st.integers(min_value=-(10**15 - 1), max_value=10**15 - 1)
M64 = (1 << 64) - 1


def s64(x):
    return x - (1 << 64) if x >> 63 else x


@settings(max_examples=2000, deadline=None)
@given(bt_vals)
def test_bt_round_trip(x):
    w = BT("bt_from_int32")(x & M64, 0)
    assert s64(BT("bt_to_int32")(w, 0)) == x


@settings(max_examples=2000, deadline=None)
@given(bt_vals, bt_vals)
def test_bt_add_homomorphism(x, y):
    f, t = BT("bt_from_int32"), BT("bt_to_int32")
    r = s64(t(BT("bt_add32")(f(x & M64, 0), f(y & M64, 0)), 0))
    assert r == ((x + y + H32) % 3**32) - H32


@settings(max_examples=2000, deadline=None)
@given(bt_vals, bt_vals)
def test_bt_mul_homomorphism(x, y):
    f, t = BT("bt_from_int32"), BT("bt_to_int32")
    r = s64(t(BT("bt_mul32")(f(x & M64, 0), f(y & M64, 0)), 0))
    assert r == ((x * y + H32) % 3**32) - H32


@settings(max_examples=2000, deadline=None)
@given(bt_vals)
def test_bt_neg_involution(x):
    f, n = BT("bt_from_int32"), BT("bt_neg32")
    w = f(x & M64, 0)
    assert n(n(w, 0), 0) == w


@settings(max_examples=2000, deadline=None)
@given(i64, i64)
def test_bin_add_sub_inverse(x, y):
    a, s = BIN("bin_add64"), BIN("bin_sub64")
    assert s(a(x & M64, y & M64), y & M64) == x & M64


@settings(max_examples=2000, deadline=None)
@given(pdv, pdv)
def test_pd_add_matches_integers(x, y):
    f, t = PD("pd_from_int15"), PD("pd_to_int15")
    r = s64(t(PD("pd_add15")(f(x & M64, 0), f(y & M64, 0)), 0))
    true = x + y
    assert r == (1 if true >= 0 else -1) * (abs(true) % 10**15)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
