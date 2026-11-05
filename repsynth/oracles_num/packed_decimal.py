# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Oracle for packed_decimal (NUM-04): Python's decimal module for arithmetic, integers for conversion."""
import decimal


class PD:
    def __init__(self, spec, d):
        self.d = d
        self.reg_bits = 64 if d == 15 else 32
        self.wmask = (1 << (4 * (d + 1))) - 1
        self.ctx = decimal.Context(prec=60, traps=[decimal.Overflow, decimal.InvalidOperation])

    def value(self, w):
        w &= self.wmask
        s = w & 0xF
        if s not in (0xC, 0xD):
            return None
        digits = [(w >> (4 * i)) & 0xF for i in range(1, self.d + 1)]
        if any(x > 9 for x in digits):
            return None
        mag = decimal.Decimal("".join(str(x) for x in reversed(digits)))
        return -mag if s == 0xD else mag

    def word(self, v):
        v = decimal.Decimal(v)
        neg = v < 0
        mag = abs(int(v)) % 10 ** self.d  # int() is exact; abs() on a Decimal would round to the default 28 digits
        w = 0xD if (neg and mag) else 0xC
        for i, ch in enumerate(reversed(str(mag).zfill(self.d))):
            w |= int(ch) << (4 * (i + 1))
        return w

    def reg(self, v):
        return int(v) & ((1 << self.reg_bits) - 1)

    def op(self, name, a, b=0):
        c = self.ctx
        if name == "from_int":
            a &= (1 << self.reg_bits) - 1
            x = a - (1 << self.reg_bits) if a >> (self.reg_bits - 1) else a
            return self.word(x)
        x = self.value(a)
        if name == "to_int":
            return self.reg(-(1 << (self.reg_bits - 1))) if x is None else self.reg(x)
        if name == "neg":
            return self.wmask if x is None else self.word(c.minus(x))
        y = self.value(b)
        if name == "cmp":
            return 2 if x is None or y is None else self.reg((x > y) - (x < y))
        if x is None or y is None:
            return self.wmask
        if name == "add": return self.word(c.add(x, y))
        if name == "sub": return self.word(c.subtract(x, y))
        if name == "mul": return self.word(c.multiply(x, y))
        raise NotImplementedError(name)
