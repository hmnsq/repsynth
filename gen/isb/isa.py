# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The word machine family model shared by every Tier B generator (ISB-01, P7.1).

Reads the family specification and the numeric specifications through the spine's loader, derives an
instance (its instruction table and semantic functions) from the family's parameters, and encodes and
decodes instruction words. Nothing here knows binary or ternary: an instance's arithmetic is whatever its
numeric specification's operations are.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from repsynth.spec import load_spec, spec_sha256  # noqa: E402

GENERATOR_VERSION = "0.3.0"
FAMILY_PATH = "spec/reps/machine/word_machine_family.yaml"
NOTICE = "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI."
NUMERIC_PATHS = {"binary_integer": "spec/reps/numeric/binary_integer.yaml",
                 "balanced_ternary": "spec/reps/numeric/balanced_ternary.yaml"}
# Machine semantic functions every instance has, beside its ALU operations: (name, arity, meaning).
MACHINE_FUNCTIONS = [
    ("imm", 1, "the word of the sign-extended immediate a (li)"),
    ("ea", 2, "the address val(a) + b modulo 2^64 (loads, stores, jalr)"),
    ("val", 1, "the two's complement host integer of word a (sb, sw)"),
    ("word", 1, "the word of the host integer a (lb, jal and jalr links)"),
    ("beq", 2, "1 when the host bits of a and b are identical, else 0"),
    ("bne", 2, "1 when the host bits of a and b differ, else 0"),
    ("blt", 2, "1 when cmp(a, b) is -1, else 0"),
    ("bge", 2, "1 when cmp(a, b) is not -1, else 0"),
]
REG_BITS = 4


def family(root: Path = ROOT) -> dict:
    return load_spec(root / FAMILY_PATH)


def numeric(sid: str, root: Path = ROOT) -> dict:
    return load_spec(root / NUMERIC_PATHS[sid])


def instances(root: Path = ROOT) -> dict:
    return family(root)["generation"]["isb"]["instances"]


def instance_path(name: str) -> str:
    return f"spec/reps/machine/{name}.yaml"


def ref_dir(name: str) -> str:
    return f"spec/ref/machine_{name}"


def numeric_prefix(num: dict) -> str:
    """bin_ / bt_: taken from the numeric specification's own symbol patterns."""
    pats = {o["reference"]["symbol_pattern"].split("_")[0] for o in num["operations"]}
    if len(pats) != 1:
        raise ValueError(f"numeric specification {num['identity']['id']} has mixed symbol prefixes {pats}")
    return pats.pop()


def derive(name: str, root: Path = ROOT) -> dict:
    """The instance model: parameters, formats, full instruction table, semantic functions."""
    fam = family(root)
    par = fam["generation"]["isb"]["instances"][name]
    num = numeric(par["numeric"], root)
    widths = {w["digits"]: w["register_bits"] for w in num["domain"]["widths"]}
    if widths.get(par["digits"]) != par["register_bits"]:
        raise ValueError(f"{name}: {par['numeric']} has no width of {par['digits']} digits in a "
                         f"{par['register_bits']}-bit register")
    enc = fam["encoding"]["encodings"][fam["encoding"]["active"]]
    rule = enc["opcode_rule"]
    insns = []
    for i, op in enumerate(num["operations"]):
        insns.append({"name": op["name"], "opcode": rule["alu_base"] + i, "format": "R" if op["arity"] == 2 else "U",
                      "syntax": f"{op['name']} rd, ra, rb" if op["arity"] == 2 else f"{op['name']} rd, ra",
                      "semantics": f"rd = {op['name']}(ra, rb)" if op["arity"] == 2 else f"rd = {op['name']}(ra)",
                      "uses": [op["name"]], "alu": True})
    for ins in enc["instructions"]:
        d = dict(ins)
        d["alu"] = False
        insns.append(d)
    ops = [o for o in insns]
    codes = [o["opcode"] for o in ops]
    if len(set(codes)) != len(codes) or any(c in rule["illegal"] or not 0 <= c < 64 for c in codes):
        raise ValueError(f"{name}: opcode collision or out of range: {codes}")
    funcs = [{"name": o["name"], "arity": o["arity"], "meaning": o["meaning"], "kind": "alu"} for o in num["operations"]]
    funcs += [{"name": n, "arity": a, "meaning": m, "kind": "machine"} for n, a, m in MACHINE_FUNCTIONS]
    return {"name": name, "params": par, "numeric": num, "numeric_prefix": numeric_prefix(num),
            "digits": par["digits"], "register_bits": par["register_bits"], "formats": enc["formats"],
            "word_bits": enc["word_bits"], "instructions": insns, "functions": funcs,
            "family_sha256": spec_sha256(fam), "numeric_sha256": spec_sha256(num),
            "fault_exit_code": fam["interfaces"]["fault_exit_code"], "memory_map": fam["interfaces"]["memory_map"]}


def sym(m: dict, fn: str) -> str:
    return f"{m['name']}_{fn}{m['digits']}"


def num_sym(m: dict, op: str) -> str:
    return f"{m['numeric_prefix']}_{op}{m['digits']}"


# ---------------------------------------------------------------- encoding
def field_spec(fmt: dict, f: str):
    v = fmt[f]
    return v[0], v[1], (len(v) > 2 and v[2] == "signed")


def encode(m: dict, name: str, **fields) -> int:
    ins = next(i for i in m["instructions"] if i["name"] == name)
    fmt = m["formats"][ins["format"]]
    w = 0
    for f, spec in fmt.items():
        hi, lo, signed = field_spec(fmt, f)
        width = hi - lo + 1
        if f == "op":
            v = ins["opcode"]
        elif f == "zero":
            v = 0
        else:
            v = fields[f]
        if signed:
            if not -(1 << (width - 1)) <= v < (1 << (width - 1)):
                raise ValueError(f"{name}: {f}={v} does not fit {width} signed bits")
            v &= (1 << width) - 1
        elif not 0 <= v < (1 << width):
            raise ValueError(f"{name}: {f}={v} does not fit {width} bits")
        w |= v << lo
    return w


def decode(m: dict, word: int):
    """(name, {field: value}) or None for an illegal word."""
    op = (word >> 26) & 0x3F
    for ins in m["instructions"]:
        if ins["opcode"] != op:
            continue
        fmt = m["formats"][ins["format"]]
        out = {}
        for f in fmt:
            hi, lo, signed = field_spec(fmt, f)
            width = hi - lo + 1
            v = (word >> lo) & ((1 << width) - 1)
            if signed and v >> (width - 1):
                v -= 1 << width
            if f == "zero" and v != 0:
                return None
            if f not in ("op", "zero"):
                out[f] = v
        return ins["name"], out
    return None


def sha_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()
