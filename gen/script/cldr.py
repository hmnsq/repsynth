# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""CLDR 44.1 (npm cldr-misc-full, cldr-localenames-full and cldr-core 44.1.0, P6.2): exemplar sets,
the locale chosen for a script, and real words of the script (territory names in that locale's language).
Exemplar sets are UnicodeSet patterns, parsed by ICU (gen/script/icu.py), not by hand."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from . import icu

# The first working set (SCR-05) and the locale whose orthography each one is read in. Arabic is read in
# Urdu orthography as SCR-05 says; Han through the zh exemplar set (simplified characters).
WORKING_SET = [("Deva", "hi"), ("Taml", "ta"), ("Arab", "ur"), ("Khmr", "km"), ("Ethi", "am"),
               ("Tfng", "zgh"), ("Hebr", "he"), ("Cyrl", "ru"), ("Hani", "zh")]
COVERAGE_RANK = {"modern": 0, "moderate": 1, "basic": 2}


class CLDR:
    def __init__(self, base: Path):
        self.base = Path(base)
        self.misc = self.base / "cldr-misc-full-44.1.0/package/main"
        self.names = self.base / "cldr-localenames-full-44.1.0/package/main"
        core = self.base / "cldr-core-44.1.0/package"
        self.likely = json.loads((core / "supplemental/likelySubtags.json").read_text(encoding="utf-8"))["supplemental"]["likelySubtags"]
        cov = json.loads((core / "coverageLevels.json").read_text(encoding="utf-8"))
        self.coverage = cov.get("effectiveCoverageLevels", {})
        self.version = json.loads((core / "package.json").read_text(encoding="utf-8"))["version"]

    def locales(self) -> list[str]:
        return sorted(p.name for p in self.misc.iterdir() if (p / "characters.json").exists())

    def characters(self, loc: str) -> dict:
        d = json.loads((self.misc / loc / "characters.json").read_text(encoding="utf-8"))
        return d["main"][loc]["characters"]

    def exemplar(self, loc: str, kind: str = "exemplarCharacters") -> list[str]:
        pat = self.characters(loc).get(kind)
        return icu.unicode_set(pat) if pat else []

    def likely_script(self, loc: str) -> str | None:
        parts = loc.split("-")
        if len(parts) > 1 and len(parts[1]) == 4:
            return parts[1]
        full = self.likely.get(loc) or self.likely.get(parts[0])
        if not full:
            return None
        s = full.split("-")
        return s[1] if len(s) > 1 and len(s[1]) == 4 else None

    def locale_for(self, script: str) -> str | None:
        """A locale whose likely script is this one: the language CLDR's likely subtags give for und-<Script>
        if CLDR has its exemplars, else the best-covered such locale (modern, moderate, basic), then by name."""
        und = self.likely.get(f"und-{script}")
        avail = set(self.locales())
        if und:
            lang = und.split("-")[0]
            for cand in (f"{lang}-{script}", lang):
                if cand in avail and self.likely_script(cand) == script:
                    return cand
        cands = [l for l in avail if self.likely_script(l) == script
                 and (l.count("-") == 0 or (l.count("-") == 1 and len(l.split("-")[1]) == 4))]
        if not cands:
            return None
        return sorted(cands, key=lambda l: (COVERAGE_RANK.get(self.coverage.get(l, ""), 9), l))[0]

    def territory_names(self, loc: str) -> list[str]:
        p = self.names / loc / "territories.json"
        if not p.exists():
            return []
        d = json.loads(p.read_text(encoding="utf-8"))["main"][loc]["localeDisplayNames"]["territories"]
        return [d[k] for k in sorted(d) if "-alt-" not in k]


@lru_cache(maxsize=2)
def load(base: str) -> CLDR:
    return CLDR(Path(base))
