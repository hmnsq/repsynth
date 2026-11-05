# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Readers for the pinned Unicode Character Database files (unicode-data 15.1.0, P6.2).

Only the published UCD file formats are read (UAX #44 section 4.2: fields separated by ';', ranges as
XXXX..YYYY, comments after '#'); nothing is recomputed from memory."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path


def _ranges(path: Path):
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        fields = [f.strip() for f in line.split(";")]
        a, _, b = fields[0].partition("..")
        lo = int(a, 16)
        hi = int(b, 16) if b else lo
        yield lo, hi, fields[1:]


class UCD:
    def __init__(self, ucd_dir: Path):
        self.dir = Path(ucd_dir)
        self.name, self.gc, self.ccc = {}, {}, {}
        first = None
        for line in (self.dir / "UnicodeData.txt").read_text(encoding="utf-8").splitlines():
            f = line.split(";")
            cp = int(f[0], 16)
            if f[1].endswith(", First>"):
                first = cp
                continue
            if f[1].endswith(", Last>"):
                for c in range(first, cp + 1):
                    self.name[c] = f[1][1:-7].upper() + f"-{c:04X}"
                    self.gc[c], self.ccc[c] = f[2], int(f[3])
                continue
            self.name[cp], self.gc[cp], self.ccc[cp] = f[1], f[2], int(f[3])
        self.script = {}
        for lo, hi, (sc,) in _ranges(self.dir / "Scripts.txt"):
            for c in range(lo, hi + 1):
                self.script[c] = sc
        self.inpc, self.insc = {}, {}
        for lo, hi, (v,) in _ranges(self.dir / "IndicPositionalCategory.txt"):
            for c in range(lo, hi + 1):
                self.inpc[c] = v
        for lo, hi, (v,) in _ranges(self.dir / "IndicSyllabicCategory.txt"):
            for c in range(lo, hi + 1):
                self.insc[c] = v
        self.incb = {}
        for lo, hi, f in _ranges(self.dir / "DerivedCoreProperties.txt"):
            if f[0] == "InCB":
                for c in range(lo, hi + 1):
                    self.incb[c] = f[1]
        self.sc_long, self.sc_short = {}, {}
        for line in (self.dir / "PropertyValueAliases.txt").read_text(encoding="utf-8").splitlines():
            f = [x.strip() for x in line.split("#", 1)[0].split(";")]
            if len(f) >= 3 and f[0] == "sc":
                self.sc_long[f[1]] = f[2]
                self.sc_short[f[2]] = f[1]
        self.version = self._version()

    def _version(self) -> str:
        head = (self.dir / "DerivedAge.txt").read_text(encoding="utf-8").splitlines()[0]
        # "# DerivedAge-15.1.0.txt"
        return head.split("-", 1)[1].rsplit(".txt", 1)[0] if "-" in head else head

    def code_points(self, script_long: str) -> list[int]:
        return sorted(c for c, s in self.script.items() if s == script_long)

    def is_mark(self, c: int) -> bool:
        return self.gc.get(c, "Cn").startswith("M")

    def is_letter(self, c: int) -> bool:
        return self.gc.get(c, "Cn").startswith("L")


@lru_cache(maxsize=4)
def load(ucd_dir: str) -> UCD:
    return UCD(Path(ucd_dir))
