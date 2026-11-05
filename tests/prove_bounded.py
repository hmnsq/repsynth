# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""CNF-05, P2.4: bounded proofs with Z3 at small widths. The balanced ternary pair encoding's trit
adder (the carry rule of NUM-02 and Guidelines 8.3) is proved over all codes, and the n-trit ripple
adder built from it is proved homomorphic with integer addition modulo 3^n for n up to 6."""
import sys
from z3 import BitVec, BitVecVal, Int, If, And, Or, Solver, sat, unsat, Extract, ZeroExt


def trit(code):  # pair encoding: 00 -> 0, 01 -> +1, 10 -> -1
    return If(code == 1, 1, If(code == 2, -1, 0))


def prove(n):
    a = BitVec("a", 2 * n); b = BitVec("b", 2 * n)
    s = Solver()
    valid = []
    va = 0; vb = 0; carry = 0; out = 0
    for i in range(n):
        ca, cb = Extract(2 * i + 1, 2 * i, a), Extract(2 * i + 1, 2 * i, b)
        valid += [ca != 3, cb != 3]
        ta, tb = trit(ca), trit(cb)
        va = va + ta * 3**i; vb = vb + tb * 3**i
        tot = ta + tb + carry
        st = If(tot > 1, tot - 3, If(tot < -1, tot + 3, tot))
        carry = If(tot > 1, 1, If(tot < -1, -1, 0))
        out = out + st * 3**i
    M, H = 3**n, (3**n - 1) // 2
    want = Int("want")
    s.add(And(*valid))
    # out must equal (va + vb) reduced into [-H, H]
    s.add(Or(out < -H, out > H, (out - (va + vb)) % M != 0))
    r = s.check()
    return r


if __name__ == "__main__":
    ok = True
    for n in range(1, 7):
        r = prove(n)
        print(f"ripple adder, {n} trits: counterexample search -> {r} ({'PROVED' if r == unsat else 'FAILED'})")
        ok &= r == unsat
    sys.exit(0 if ok else 1)
