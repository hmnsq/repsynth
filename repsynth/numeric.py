# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Numeric lane (H10): reference libraries, oracles, enumerators and vectors (P1.3, P1.4, P2.1)."""
from __future__ import annotations

import ctypes
import itertools
import random
from pathlib import Path

from .records import ROOT
from .spec import load_spec, spec_sha256
from .oracles_num.balanced_ternary import BT
from .oracles_num.binary_integer import BIN
from .oracles_num.packed_decimal import PD
from . import __version__

SPECS = {
    "balanced_ternary": {"path": "spec/reps/numeric/balanced_ternary.yaml", "oracle": BT},
    "binary_integer": {"path": "spec/reps/numeric/binary_integer.yaml", "oracle": BIN},
    "packed_decimal": {"path": "spec/reps/numeric/packed_decimal.yaml", "oracle": PD},
}
VECTOR_FORMAT = 1


def spec_of(sid: str, root: Path = ROOT) -> dict:
    return load_spec(root / SPECS[sid]["path"])


def native_lib_path(sid: str, root: Path = ROOT) -> Path:
    return root / "out" / "software" / sid / f"lib{sid}.so"


class RefLib:
    """The C reference functions, loaded from the native build (ctypes)."""

    def __init__(self, sid: str, spec: dict, root: Path = ROOT):
        self.lib = ctypes.CDLL(str(native_lib_path(sid, root)))
        self.spec = spec

    def fn(self, op: dict, digits: int):
        name = op["reference"]["symbol_pattern"].replace("{width}", str(digits))
        f = getattr(self.lib, name)
        f.restype = ctypes.c_uint64
        f.argtypes = [ctypes.c_uint64, ctypes.c_uint64]
        return f


# ---------------------------------------------------------------- operand enumeration (CNF-03)


def _bt_words(o: BT, k: int):
    """Every value whose trits above k are zero, as words (the low-k-trit domain)."""
    h = (3 ** k - 1) // 2
    for v in range(-h, h + 1):
        yield o.word(v)


def exhaustive_operands(sid: str, spec: dict, oracle, arity: int):
    ex = spec["verification"]["exhaustive"]
    if sid == "balanced_ternary":
        k = ex["unary_low_digits"] if arity == 1 else ex["binary_low_digits"]
        dom = list(_bt_words(oracle, min(k, oracle.n)))
        # include invalid codes in the low trits: one invalid code at trit 0 and at trit k-1
        bad = [oracle.word_mask & 0x3, oracle.word_mask]  # trit 0 invalid in pair; all-ones word
        dom_ext = dom + bad
    elif sid == "binary_integer":
        k = ex["unary_low_digits"] if arity == 1 else ex["binary_low_digits"]
        m = (1 << oracle.w) - 1
        dom_ext = [x for v in range(1 << (k - 1)) for x in (v, (-v - 1) & m)]
    elif sid == "packed_decimal":
        dom_ext = [oracle.word(v) for v in range(-999, 1000)] + [0xD, oracle.wmask, 0xA, 0xAC]
    else:
        raise KeyError(sid)
    if arity == 1:
        return ((a, 0) for a in dom_ext)
    return itertools.product(dom_ext, dom_ext)


def boundary_operands(sid: str, oracle, arity: int):
    if sid == "balanced_ternary":
        H = oracle.H
        vals = [oracle.word(v) for v in (0, 1, -1, 2, -2, H, -H, H - 1, -H + 1, H // 3, -(H // 3), 3 ** (oracle.n - 1))]
        vals += [oracle.invalid, 0x3, 0x3 << (2 * (oracle.n - 1))]
    elif sid == "binary_integer":
        w = oracle.w
        vals = [0, 1, (1 << w) - 1, 1 << (w - 1), (1 << (w - 1)) - 1, 2, (1 << w) - 2, w - 1, w, w + 1]
    else:
        vals = [oracle.word(v) for v in (0, 1, -1, 10 ** oracle.d - 1, -(10 ** oracle.d - 1), 10 ** (oracle.d - 1), 5, -5)]
        vals += [0xD, oracle.wmask, 0xA]
    if arity == 1:
        return [(a, 0) for a in vals]
    return [(a, b) for a in vals for b in vals]


def random_operands(sid: str, oracle, arity: int, seed: int, count: int, opname: str):
    rng = random.Random(f"{seed}:{sid}:{opname}:{getattr(oracle, 'n', getattr(oracle, 'w', getattr(oracle, 'd', 0)))}")
    def one():
        if sid == "balanced_ternary":
            return oracle.word(rng.randint(-oracle.H, oracle.H))
        if sid == "binary_integer":
            return rng.getrandbits(oracle.w)
        return oracle.word(rng.randint(-(10 ** oracle.d - 1), 10 ** oracle.d - 1))
    out = []
    for _ in range(count):
        a = one()
        b = one() if arity == 2 else 0
        if opname in ("shl", "shr"):
            b = rng.randint(0, (64 if getattr(oracle, 'reg_bits', getattr(oracle, 'w', 64)) == 64 else 32) - 1)
        out.append((a, b))
    return out


def oracle_for(sid: str, spec: dict, digits: int):
    return SPECS[sid]["oracle"](spec, digits)


def reg_bits_of(spec: dict, digits: int) -> int:
    for w in spec["domain"]["widths"]:
        if w["digits"] == digits:
            return w["register_bits"]
    raise KeyError(digits)


# ---------------------------------------------------------------- vectors (P2.1, CNF-01)


def vector_lines(sid: str, spec: dict, op: dict, digits: int, ref) -> list[str]:
    o = oracle_for(sid, spec, digits)
    rb = reg_bits_of(spec, digits)
    hexw = rb // 4
    f = ref.fn(op, digits)
    cases = boundary_operands(sid, o, op["arity"])
    rnd = spec["verification"]["random"]
    cases += random_operands(sid, o, op["arity"], rnd["seed"], rnd["stored_cases"], op["name"])
    if op["name"] in ("shl", "shr"):
        cases += [(a, k) for (a, _) in boundary_operands(sid, o, 1) for k in range(0, rb + 2)]
    seen, rows = set(), []
    for a, b in cases:
        if (a, b) in seen:
            continue
        seen.add((a, b))
        r = f(a, b)
        if op["arity"] == 1:
            rows.append(f"{a:0{hexw}x} {r:0{hexw}x}")
        else:
            rows.append(f"{a:0{hexw}x} {b:0{hexw}x} {r:0{hexw}x}")
    fields = "a -> r" if op["arity"] == 1 else "a b -> r"
    head = [
        f"# repsynth-vectors {VECTOR_FORMAT}",
        f"# spec: {sid}",
        f"# version: {spec['identity']['version']}",
        f"# slice_sha256: {vector_slice_hash(spec, op)}",
        f"# op: {op['name']}",
        f"# width: {digits} ({rb}-bit register)",
        f"# fields: {fields}",
        f"# generator: repsynth.vectors {__version__}",
        f"# cases: {len(rows)}",
    ]
    return head + rows


def vector_reads(spec: dict, op: dict) -> list[str]:
    """Declared reads of one vector file (DEP-01): its operation, the widths, the case settings."""
    i = [o["name"] for o in spec["operations"]].index(op["name"])
    return ["/identity/id", "/identity/version", f"/operations/{i}", "/domain/widths",
            "/verification/random", "/encoding"]


def vector_slice_hash(spec: dict, op: dict) -> str:
    from .spec import slice_hash
    import hashlib
    h = hashlib.sha256()
    for p in vector_reads(spec, op):
        h.update(p.encode() + b"=" + slice_hash(spec, p).encode() + b"\n")
    return h.hexdigest()


def vector_path(sid: str, opname: str, digits: int, root: Path = ROOT) -> Path:
    return root / "conformance" / "vectors" / sid / f"{opname}.{digits}.vec"


def read_vectors(path: Path):
    head, rows = {}, []
    for line in path.read_text().splitlines():
        if line.startswith("#"):
            if ":" in line:
                k, v = line[1:].split(":", 1)
                head[k.strip()] = v.strip()
            continue
        parts = line.split()
        if "->" in head.get("fields", ""):
            pass
        rows.append([int(p, 16) for p in parts])
    return head, rows


# ---------------------------------------------------------------- P1.3 / P1.4: reference against oracle


def verify_reference(sid: str, root: Path = ROOT, log=print) -> dict:
    """Exhaustive (restricted digits), boundary and seeded random checks of every reference function
    against the independent oracle. Returns per op and width: cases and disagreements."""
    spec = spec_of(sid, root)
    ref = RefLib(sid, spec, root)
    rnd = spec["verification"]["random"]
    result = {}
    for w in spec["domain"]["widths"]:
        d = w["digits"]
        o = oracle_for(sid, spec, d)
        for op in spec["operations"]:
            f = ref.fn(op, d)
            n = bad = 0
            first = None
            sets = [("exhaustive", exhaustive_operands(sid, spec, o, op["arity"])),
                    ("boundary", boundary_operands(sid, o, op["arity"])),
                    ("random", random_operands(sid, o, op["arity"], rnd["seed"], rnd["working_value"], op["name"]))]
            for label, cases in sets:
                for a, b in cases:
                    n += 1
                    got, want = f(a, b), o.op(op["name"], a, b)
                    if got != want:
                        bad += 1
                        if first is None:
                            first = f"{label}: a={a:x} b={b:x} reference={got:x} oracle={want:x}"
            key = f"{op['name']}.{d}"
            result[key] = {"cases": n, "disagreements": bad, "first": first}
            log(f"  {sid} {key:16s} cases={n:8d} disagreements={bad}" + (f"  FIRST {first}" if first else ""))
    return result
