# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Arbitrary-precision oracle for balanced_ternary (NUM-04). Reads the encoding table from the spec."""
from __future__ import annotations


class BT:
    def __init__(self, spec: dict, n: int):
        self.n = n
        self.reg_bits = 64 if n == 32 else 32
        enc = spec["encoding"]["encodings"][spec["encoding"]["active"]]
        self.layout = enc["layout"]
        self.code_of = {int(k): int(v, 2) for k, v in enc["codes"].items()}
        self.val_of = {c: t for t, c in self.code_of.items()}
        self.M = 3 ** n
        self.H = (self.M - 1) // 2
        self.word_mask = (1 << (2 * n)) - 1
        self.invalid = self.word_mask

    def code(self, w, i):
        if self.layout == "interleaved":
            return (w >> (2 * i)) & 3
        return (((w >> (self.n + i)) & 1) << 1) | ((w >> i) & 1)

    def trits(self, w):
        out = []
        for i in range(self.n):
            c = self.code(w, i)
            if c not in self.val_of:
                return None
            out.append(self.val_of[c])
        return out

    def value(self, w):
        t = self.trits(w & self.word_mask)
        return None if t is None else sum(d * 3 ** i for i, d in enumerate(t))

    def word(self, v):
        v = ((v + self.H) % self.M) - self.H
        w = 0
        for i in range(self.n):
            d = ((v + 1) % 3) - 1
            c = self.code_of[d]
            if self.layout == "interleaved":
                w |= c << (2 * i)
            else:
                w |= (c & 1) << i | ((c >> 1) & 1) << (self.n + i)
            v = (v - d) // 3
        assert v == 0
        return w

    def signed(self, a):
        a &= (1 << self.reg_bits) - 1
        return a - (1 << self.reg_bits) if a >> (self.reg_bits - 1) else a

    def reg(self, v):
        return v & ((1 << self.reg_bits) - 1)

    def op(self, name, a, b=0):
        n = self.n
        if name == "from_int":
            return self.word(self.signed(a))
        x = self.value(a)
        if name == "to_int":
            return self.reg(-(1 << (self.reg_bits - 1))) if x is None else self.reg(x)
        if name == "neg":
            return self.invalid if x is None else self.word(-x)
        if name in ("shl", "shr"):
            if x is None:
                return self.invalid
            k = b % self.reg_bits
            if k >= n:
                return self.word(0)
            if name == "shl":
                return self.word(x * 3 ** k)
            # dropping k low trits: the value with the low k trits removed, divided by 3^k
            low = sum(d * 3 ** i for i, d in enumerate(self.trits(a & self.word_mask)[:k]))
            return self.word((x - low) // 3 ** k)
        y = self.value(b)
        if name == "cmp":
            if x is None or y is None:
                return 2
            return self.reg((x > y) - (x < y))
        if x is None or y is None:
            return self.invalid
        if name == "add":
            return self.word(x + y)
        if name == "sub":
            return self.word(x - y)
        if name == "mul":
            return self.word(x * y)
        raise NotImplementedError(name)
