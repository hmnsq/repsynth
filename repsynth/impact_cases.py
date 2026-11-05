# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The four changes of DEP-05 (demonstrator D2), applied to the working tree and always restored.

(a) one AyeHandSum encoding rule: needs the AyeHandSum specification (P1.7);
(b) one APCISR grid rule in a derived build: needs the Devanagari grid specification (P1.6);
(c) one new operation in a specification: balanced_ternary gains abs;
(d) the trit encoding of balanced_ternary: pair to planes.
Expected sets are stated by artefact kind, independently of the engine's prediction."""
from __future__ import annotations

import contextlib
from dataclasses import dataclass, field
from pathlib import Path

BT_SPEC = "spec/reps/numeric/balanced_ternary.yaml"
BT_C = "spec/ref/balanced_ternary/balanced_ternary.c"
BT_H = "spec/ref/balanced_ternary/balanced_ternary.h"

ABS_OP = '  - {name: abs, arity: 1, meaning: "|a|, wrapping modulo 3^n", reference: {symbol_pattern: "bt_abs{width}"}, candidate: true}\n'
ABS_C = ("\nstatic uint64_t absv(uint64_t a, unsigned n) {\n  a &= word_mask(n);\n  if (!valid_word(a, n)) return invalid(n);\n"
         "  int64_t v = decode(a, n);\n  return encode(v < 0 ? -v : v, n);\n}\n"
         "uint64_t bt_abs32(uint64_t a, uint64_t b) { (void)b; return absv(a, 32u); }\n"
         "uint64_t bt_abs16(uint64_t a, uint64_t b) { (void)b; return absv(a, 16u); }\n")
ABS_H = "uint64_t bt_abs32(uint64_t a, uint64_t b);\nuint64_t bt_abs16(uint64_t a, uint64_t b);\n"


@dataclass
class Case:
    name: str
    spec_id: str
    edits: list = field(default_factory=list)   # (path, old, new) or (path, None, appended)
    changed_files: set = field(default_factory=set)
    expected_kinds: dict = field(default_factory=dict)

    @contextlib.contextmanager
    def applied(self, root: Path):
        saved = {}
        try:
            for path, old, new in self.edits:
                p = root / path
                text = p.read_text(encoding="utf-8")
                saved.setdefault(path, text)
                if old is None:
                    text = text + new
                else:
                    if text.count(old) != 1:
                        raise RuntimeError(f"change anchor not found exactly once in {path}: {old!r}")
                    text = text.replace(old, new)
                p.write_text(text, encoding="utf-8")
            yield self
        finally:
            for path, text in saved.items():
                (root / path).write_text(text, encoding="utf-8")

    def expected(self, nodes, root: Path) -> set:
        out = set()
        for n in nodes:
            rule = self.expected_kinds.get(n.kind)
            if rule and rule(n):
                out |= set(n.outputs)
        return out


def resolve_change(change: str, root: Path) -> Case:
    if change in ("c", "new-operation"):
        c = Case("dep05c_new_operation", "balanced_ternary")
        # Operations are addressed by index (JSON Pointer), so the evolution rule appends new ones.
        c.edits = [(BT_SPEC, "composition:\n", ABS_OP + "composition:\n"),
                   (BT_C, "\n/* Public entry points", ABS_C + "\n/* Public entry points"),
                   (BT_H, "const char *bt_encoding_name(void);", ABS_H + "const char *bt_encoding_name(void);")]
        c.changed_files = {BT_C, BT_H}
        is_bt = lambda n: n.spec == "balanced_ternary"
        c.expected_kinds = {
            "software": lambda n: is_bt(n) and not n.id.startswith("codec:"),
            "vectors": lambda n: n.id.startswith("vectors:balanced_ternary:abs:"),
            "tier_a": lambda n: is_bt(n) and getattr(n, "op", None) in (None, "abs"),
        }
        return c
    if change in ("d", "trit-encoding"):
        c = Case("dep05d_trit_encoding", "balanced_ternary")
        c.edits = [(BT_SPEC, "  active: pair\n", "  active: planes\n")]
        is_bt = lambda n: n.spec == "balanced_ternary"
        c.expected_kinds = {
            "software": lambda n: is_bt(n) and not n.id.startswith("glue:"),
            "vectors": is_bt,
            "tier_a": is_bt,
            "hardware": is_bt,
        }
        return c
    if change in ("a", "ayehandsum-rule"):
        return _lane_case("repsynth.lanes.ayehandsum_change_a", root,
                          "DEP-05(a) needs the AyeHandSum generators and their graph nodes (P1.7, P2.2)")
    if change in ("b", "apcisr-grid-rule"):
        return _lane_case("repsynth.lanes.script_change_b", root,
                          "DEP-05(b) needs the Devanagari grid specification and the APCISR derived build (P1.6, P6.3)")
    raise KeyError(f"unknown change {change!r}; use a, b, c or d")


def _lane_case(module: str, root: Path, why: str) -> Case:
    """Changes (a) and (b) are defined by the lanes that own those artefacts."""
    import importlib
    try:
        m = importlib.import_module(module)
    except ModuleNotFoundError:
        raise NotImplementedError(why)
    for name in ("case", "change_b", "change_a", "make_case"):
        if hasattr(m, name):
            return getattr(m, name)(root)
    raise NotImplementedError(f"{module} defines no case(root) function")
