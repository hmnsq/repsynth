# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Arbitrary-precision oracle for binary_integer (NUM-04)."""


class BIN:
    def __init__(self, spec, w):
        self.w = w
        self.mask = (1 << w) - 1

    def s(self, a):
        a &= self.mask
        return a - (1 << self.w) if a >> (self.w - 1) else a

    def op(self, name, a, b=0):
        x, y, m = self.s(a), self.s(b), self.mask
        if name == "neg": return (-x) & m
        if name == "add": return (x + y) & m
        if name == "sub": return (x - y) & m
        if name == "mul": return (x * y) & m
        if name == "cmp": return ((x > y) - (x < y)) & m
        if name == "shl": return (x << (b % self.w)) & m
        if name == "shr": return (x >> (b % self.w)) & m
        raise NotImplementedError(name)
