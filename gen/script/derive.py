# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Candidate grid tables for scripts outside the author's canon (SCR-02, GEN-05; packets P6.3 and P6.5).

What is derived, and from what (nothing else is assumed; anything not derivable is written as
not_established with its reason and left out of the emitted table, SPC-05):

* repertoire: the CLDR 44.1 main exemplar set of the chosen locale (items are code points or strings),
  restricted to the script; without a locale, every letter and mark the pinned UCD assigns to the script.
* input encoding: ISCII where the author's Romenagri table iscii_map.csv gives the script a column
  (APCISR's own input is ISCII, and its dynamic rules in acii2csr.c are keyed to ISCII bytes); UTF-8 otherwise.
* names (the rmn field): the Romenagri key of the ISCII byte where Romenagri has one; otherwise the code
  point label (U+XXXX), so no romanisation is invented.
* placement of a mark in the 3 x 3 grid: UCD Indic_Positional_Category where the mark has one; otherwise the
  canonical combining class when it names a position (UAX #44 table 14: 202/214/216/218/220/222/224/226/228/
  230/232/233/234). Overstruck, Visual_Order_Left, fixed-position classes 10 to 199, class 1 (overlay) and
  marks with neither property are not established: the grid has no cell that holds them without new rules.
* cell values: bit flags inside the capacity APCISR's code leaves free (read in P6.1): madhya side cells
  take bits 0 to 4 only (128 marks a non-lipik cell, 32 the headline, values above 160 are reduced by 32 and
  192 means non-ISCII); urdha and nimna cells take bits 0 to 6; for ISCII input the bits the dynamic rules
  write are reserved for them. Lipik glyph numbers are 1 to 127 (bit 7 marks a non-lipik cell).
* glyph tables: APCISR maps every cell value to a byte of a 256-glyph console font (cisr2asc.h). No font
  exists for a candidate, so codes are allocated from 0x21..0x7e and 0x80..0xff (0x20 is blank), and a
  legend maps each code to the characters it stands for. Combinations of two flags in one cell get a code
  while codes remain; any other combination maps to '?' (0x3f), which the legend says.
"""
from __future__ import annotations

import csv
from pathlib import Path

from . import GENERATOR_VERSION

POSITION_BY_CCC = {202: "Bottom", 214: "Top", 216: "Top", 218: "Bottom", 220: "Bottom", 222: "Bottom",
                   224: "Left", 226: "Right", 228: "Top", 230: "Top", 232: "Top", 233: "Bottom", 234: "Top"}
# InPC value -> cells (row, column); rows u/m/n, columns 0 matrik, 1 lipik, 2 purak
CELLS_BY_INPC = {
    "Top": [("u", 1)], "Bottom": [("n", 1)], "Left": [("m", 0)], "Right": [("m", 2)],
    "Top_And_Right": [("u", 2), ("m", 2)], "Top_And_Left": [("u", 0), ("m", 0)],
    "Left_And_Right": [("m", 0), ("m", 2)], "Top_And_Bottom": [("u", 1), ("n", 1)],
    "Bottom_And_Right": [("n", 2), ("m", 2)], "Bottom_And_Left": [("n", 0), ("m", 0)],
    "Top_And_Left_And_Right": [("u", 1), ("m", 0), ("m", 2)],
    "Top_And_Bottom_And_Right": [("u", 2), ("n", 2), ("m", 2)],
    "Top_And_Bottom_And_Left": [("u", 0), ("n", 0), ("m", 0)],
}
NOT_PLACEABLE = {"Overstruck": "an overstruck mark changes the lipik glyph itself; no grid cell holds it",
                 "Visual_Order_Left": "the mark precedes its base in logical order but is drawn to its left; APCISR attaches a purna-0 symbol to the preceding varna"}
# bits the dynamic rules of acii2csr.c write for ISCII input (P6.1 reading record, rules 1 to 10)
ISCII_RULE_BITS = {"u": {1, 2, 4, 16, 32}, "n": {1, 2, 8, 64}, "m": {8, 16}}
RULE_LABELS = {"u": {1: "rule 10 (^i dome, left half)", 2: "rule 10 (^i dome, right half)", 4: "rule 3 (o-kar part moved by visarga)",
                     16: "rule 5 (bindu)", 32: "rule 4 (chandra bindu)", 128: "rule 7 (ref above)"},
               "n": {1: "rule 6 (^oo)", 2: "rule 2 (^u)", 8: "rule 1 (lower ref ^ra)", 64: "rule 9 (hal)"},
               "m": {8: "rule 10 (^i bar)", 16: "rule 3 (visarga)"}}
POOL_BITS = {"u": [1, 2, 4, 8, 16, 32, 64], "n": [1, 2, 4, 8, 16, 32, 64], "m": [1, 2, 4, 8, 16]}
CODES = [c for c in range(0x21, 0x7f)] + [c for c in range(0x80, 0x100)]
BLANK, UNALLOCATED = 0x20, 0x3F
LIPIK_MAX = 127
TABLE_SIZE = 256
ISCII_COLUMNS = {"Deva": 3, "Beng": 5, "Guru": 9, "Gujr": 11, "Orya": 13, "Taml": 15, "Telu": 17, "Knda": 19, "Mlym": 21}


def iscii_map(chintamani: Path, script: str) -> dict[str, int]:
    col = ISCII_COLUMNS.get(script)
    if col is None:
        return {}
    out = {}
    with open(chintamani / "Romenagri" / "iscii_map.csv", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    for r in rows[1:]:
        if len(r) > col and r[col].strip():
            ch = r[col].strip()
            if len(ch) == 1:
                out.setdefault(ch, int(r[0], 16))
    return out


def romenagri_keys(root: Path) -> dict[int, str]:
    """Single-byte ACII -> Romenagri key, from the accepted P1.5 specification (read only)."""
    import yaml
    p = root / "spec/reps/transliteration/romenagri_devanagari.yaml"
    if not p.exists():
        return {}
    spec = yaml.safe_load(p.read_text(encoding="utf-8"))
    out = {}
    for row in spec.get("encoding", {}).get("acii_to_romenagri", []):
        h = str(row.get("acii", ""))
        if len(h) == 2 and row.get("table_key"):
            out.setdefault(int(h, 16), row["table_key"])
    return out


def _position(ucd, cp: int):
    if cp in ucd.inpc and ucd.inpc[cp] != "NA":
        v = ucd.inpc[cp]
        if v in CELLS_BY_INPC:
            return v, CELLS_BY_INPC[v], "UCD Indic_Positional_Category"
        return v, None, NOT_PLACEABLE.get(v, f"Indic_Positional_Category {v} has no grid cell")
    ccc = ucd.ccc.get(cp, 0)
    if ccc in POSITION_BY_CCC:
        v = POSITION_BY_CCC[ccc]
        return v, CELLS_BY_INPC[v], f"UCD canonical combining class {ccc}"
    if ccc == 1:
        return "Overlay", None, "canonical combining class 1 (overlay): an overstruck mark has no grid cell"
    if 10 <= ccc <= 199:
        return f"ccc{ccc}", None, f"canonical combining class {ccc} is a fixed-position class; UCD does not say where it is drawn"
    return "NA", None, f"no Indic_Positional_Category and canonical combining class {ccc} names no position"


class _Alloc:
    def __init__(self, reserved: dict):
        self.free = {}
        for pool in ("u_lipik", "u_side", "n_lipik", "n_side", "m_side"):
            row = pool[0]
            self.free[pool] = [b for b in POOL_BITS[row] if b not in reserved.get(row, set())]

    @staticmethod
    def pool(row, col):
        if row == "m":
            return "m_side"
        return f"{row}_{'lipik' if col == 1 else 'side'}"

    def take(self, row, col):
        p = self.pool(row, col)
        return self.free[p].pop(0) if self.free[p] else None


def derive(script: str, ucd, *, items: list[str], locale: str | None, chintamani: Path, root: Path,
           registry_row: dict | None = None) -> dict:
    """Return a candidate specification (meta-model dict) for one script."""
    long = ucd.sc_long.get(script)
    iscii = iscii_map(chintamani, script)
    charset = "ISCII" if iscii else "UTF-8"
    rmn_keys = romenagri_keys(root) if iscii else {}
    reserved = ISCII_RULE_BITS if iscii else {}
    alloc = _Alloc(reserved)
    entries, excluded, legend = [], [], {"urdha": {}, "nimna": {}, "madhya": {}}
    codes = list(CODES)
    lipik_next = 1
    cell_flags = {"u": {}, "n": {}, "m": {}}   # row -> {value: text}

    def encode(s: str):
        if iscii:
            try:
                return bytes(iscii[ch] for ch in s)
            except KeyError as e:
                return None
        return s.encode("utf-8")

    def label(s: str) -> str:
        return " ".join(f"U+{ord(c):04X}" for c in s)

    def rmn_of(s: str, raw: bytes) -> str:
        if iscii and all(b in rmn_keys for b in raw):
            return "".join(rmn_keys[b] for b in raw)
        return label(s)

    bases, marks = [], []
    for it in items:
        if len(it) == 1 and ucd.is_mark(ord(it)):
            marks.append(it)
        else:
            bases.append(it)
    # bases: one lipik glyph each
    for it in bases:
        raw = encode(it)
        if raw is None:
            excluded.append({"text": it, "code_points": label(it), "reason": "no ISCII code for every character in Romenagri iscii_map.csv"})
            continue
        if lipik_next > LIPIK_MAX:
            excluded.append({"text": it, "code_points": label(it), "reason": f"capacity: APCISR's madhya-lipik cell holds glyph numbers 1 to {LIPIK_MAX} (bit 7 marks a non-lipik cell)"})
            continue
        if not codes:
            excluded.append({"text": it, "code_points": label(it), "reason": "capacity: the 256-code console font has no free code"})
            continue
        g = lipik_next
        lipik_next += 1
        code = codes.pop(0)
        legend["madhya"][str(code)] = it
        entries.append({"rmn": rmn_of(it, raw), "acii_hex": raw.hex(), "purna": 1,
                        "grid": [0, 0, 0, 0, g, 0, 0, 0, 0], "text": it, "class": "base", "glyph": {"madhya": [g, code]}})
    # marks: flags in the cells their position names
    for it in marks:
        cp = ord(it)
        raw = encode(it)
        pos, cells, why = _position(ucd, cp)
        if raw is None:
            excluded.append({"text": it, "code_points": label(it), "reason": "no ISCII code in Romenagri iscii_map.csv"})
            continue
        if cells is None:
            excluded.append({"text": it, "code_points": label(it), "position": pos, "reason": f"position not established: {why}"})
            continue
        grid = [0] * 9
        taken = []
        for row, col in cells:
            b = alloc.take(row, col)
            if b is None:
                taken = None
                break
            taken.append((row, col, b))
        if taken is None:
            excluded.append({"text": it, "code_points": label(it), "position": pos,
                             "reason": f"capacity: no free bit left in the {('urdha' if cells[0][0]=='u' else 'nimna' if cells[0][0]=='n' else 'madhya side')} cells"})
            continue
        for row, col, b in taken:
            grid[{"u": 0, "m": 3, "n": 6}[row] + col] = b
            cell_flags[row].setdefault(b, []).append(it)
        entries.append({"rmn": rmn_of(it, raw), "acii_hex": raw.hex(), "purna": 0, "grid": grid, "text": it,
                         "class": "mark", "position": pos, "position_source": why})
    if iscii:
        for row, labels in RULE_LABELS.items():
            for bit, lab in labels.items():
                cell_flags[row].setdefault(bit, []).append(lab)
    # glyph tables
    tables = {r: {} for r in ("urdha", "nimna", "madhya")}
    rowname = {"u": "urdha", "n": "nimna", "m": "madhya"}
    for row in ("u", "n", "m"):
        flags = sorted(cell_flags[row])
        singles = [(f,) for f in flags]
        pairs = [(a, b) for i, a in enumerate(flags) for b in flags[i + 1:]]
        for combo in singles + pairs:
            v = sum(combo) + (128 if row == "m" else 0)
            if not codes:
                tables[rowname[row]][v] = UNALLOCATED
                continue
            c = codes.pop(0)
            tables[rowname[row]][v] = c
            legend[rowname[row]][str(c)] = "+".join("◌" + "/".join(cell_flags[row][f]) for f in combo)
    for e in entries:
        if e["class"] == "base":
            g, c = e["glyph"]["madhya"]
            tables["madhya"][g] = c
    glyph_tables = {}
    for name in ("urdha", "nimna", "madhya"):
        m = tables[name]
        pairs = [[v, m.get(v, BLANK if v in (0, 128, 160) else UNALLOCATED)] for v in range(TABLE_SIZE)]
        glyph_tables[name] = {"size": TABLE_SIZE, "pairs": pairs}
    legend_note = {"0x20": "blank", "0x3f": "a cell value with no allocated code (an unallocated combination of flags)"}
    # lookup order: longer inputs first, so multi-character items win (as in APCISR, whose conjunct entries come first)
    order = sorted(range(len(entries)), key=lambda i: (-len(bytes.fromhex(entries[i]["acii_hex"])), i))
    entries = [entries[i] for i in order]
    title = f"Candidate 9-grid table for {long or script} ({script})" + (f", CLDR locale {locale}" if locale else "")
    return {
        "_notice": "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC0-1.0",
        "identity": {"id": f"grid_{script.lower()}_candidate", "version": "0.3.0", "family": "script_structure",
                     "title": title,
                     "equality": "Two tables are equal when their entries (input bytes, purna, nine cells) and glyph tables are equal, in order.",
                     "canonical_form": "The canonical JSON of structure.grid_table and structure.glyph_tables."},
        "domain": {"description": f"The {len(entries)} symbols of the {charset} input that the table renders; "
                                  f"{len(excluded)} repertoire items are left out with their reasons (structure.not_established).",
                   "finite": True, "enumerator": "structure.grid_table, in lookup order"},
        "structure": {
            "model": "APCISR 9-grid (3 x 3): rows urdha, madhya, nimna; columns matrik, lipik, purak (reading record P6.1)",
            "script": script, "script_name": long or {"not_established": "script code not in the pinned UCD PropertyValueAliases.txt"},
            "registry": registry_row or {},
            "repertoire_source": (f"CLDR 44.1 exemplarCharacters of locale {locale}" if locale else "UCD 15.1 Scripts.txt: every letter and mark of the script"),
            "grid_table": [{k: e[k] for k in ("rmn", "acii_hex", "purna", "grid")} for e in entries],
            "symbols": [{k: v for k, v in e.items() if k not in ("rmn", "acii_hex", "purna", "grid")} for e in entries],
            "glyph_tables": glyph_tables,
            "glyph_legend": {"codes": legend, "notes": legend_note},
            "not_established": excluded,
        },
        "encoding": {"input": charset,
                     "rule": ("Each symbol's input is its ISCII byte from the author's Romenagri iscii_map.csv" if iscii
                              else "Each symbol's input is its UTF-8 byte sequence")},
        "decoding": {"rule": "APCISR's acii2cisr renders input to three rows of console-font codes; glyph_legend maps codes back to characters.",
                     "error_behaviour": "Input not in the table takes APCISR's non-ISCII path (one byte per column, acii2csr.c lines 220-275)."},
        "semantics": {"statement": "The grid placement of each symbol as derived above; rendering semantics are APCISR's own code, unchanged.",
                      "reference_sources": ["gen/script/derive.py"],
                      "oracle": "HarfBuzz 8.3.0 with a Noto font, and ICU 74.2 grapheme clusters (P6.4)"},
        "operations": [],
        "composition": {"rule": "Symbols combine into varnas by APCISR's purna rules (acii2csr.c lines 290-440)."},
        "transformations": [],
        "constraints": [{"name": "capacity", "statement": f"lipik glyphs <= {LIPIK_MAX}; flags per cell within the bits APCISR leaves free; codes <= {len(CODES)}"}],
        "substrate": {"logical": "other", "register_widths": []},
        "interfaces": {"imports": ["UCD 15.1", "CLDR 44.1", "Romenagri iscii_map.csv" if iscii else "none from Romenagri"],
                       "exports": ["apcisr.h", "cisr2asc.h"]},
        "verification": {"properties": [
            {"name": "builds", "method": "APCISR built with these tables, natively with its own Makefile and to WebAssembly (P6.3)"},
            {"name": "clusters_and_positions", "method": "compared with HarfBuzz and ICU grapheme clusters (P6.4)"}]},
        "generation": {"apcisr": {"generator": GENERATOR_VERSION, "outputs": ["apcisr.h", "cisr2asc.h"]}},
        "evolution": {"changes": [{"version": "0.3.0", "class": "initial", "summary": "Candidate derived by the harness (GEN-05); adoption is the author's act."}]},
        "provenance": {"oracle": {"not_established": "no author's table exists for this script; this is a candidate outside the canon (GEN-05)"},
                       "extraction": f"Derived by gen/script/derive.py ({GENERATOR_VERSION}) from UCD 15.1, CLDR 44.1" + (" and Romenagri iscii_map.csv" if iscii else ""),
                       "evidence_state": "proposed"},
    }


def table_model(spec: dict, spec_sha: str, candidate: bool = True) -> dict:
    s = spec["structure"]
    return {"id": spec["identity"]["id"], "title": spec["identity"]["title"], "spec_sha256": spec_sha,
            "candidate": candidate, "charset": spec["encoding"]["input"],
            "entries": s["grid_table"], "glyph_tables": s["glyph_tables"]}
