# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Properties of the machine specifications and their reference functions (P7.1 acceptance).

  python3 conformance/runners/isb/properties.py [--root DIR] [NAME ...]

For each instance: (1) the instance specification and reference sources equal their derivation from the
family; (2) encoding round trip: every instruction over every register choice and boundary immediates
encodes and decodes to itself, decoded both by the Python model and by the family's C field functions,
and 200000 seeded random words that decode re-encode to themselves; (3) homomorphism: every ALU function
equals the numeric specification's stored vectors (whose expected values come from the independent
Python oracle), and the machine functions equal Python integers and the numeric oracle on boundary and
seeded random cases. Exit 0 only when every property holds.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "gen" / "isb"))
sys.path.insert(0, str(ROOT))
import isa  # noqa: E402
from repsynth.numeric import read_vectors  # noqa: E402

SEED = 20261104


def build_lib(name: str, root: Path, out: Path) -> Path:
    m = isa.derive(name, root)
    nid = m["numeric"]["identity"]["id"]
    out.mkdir(parents=True, exist_ok=True)
    so = out / f"lib{name}_props.so"
    srcs = [root / isa.ref_dir(name) / f"{name}.c", root / f"spec/ref/{nid}/{nid}.c", HERE / "fields.c"]
    cmd = ["gcc", "-std=c11", "-O1", "-Wall", "-Werror", "-shared", "-fPIC", "-o", str(so),
           f"-I{root / isa.ref_dir(name)}", f"-I{root / 'spec/ref' / nid}", f"-I{root / 'spec/ref/machine_family'}"] + [str(s) for s in srcs]
    subprocess.run(cmd, check=True)
    return so


def oracle(m: dict):
    nid = m["numeric"]["identity"]["id"]
    if nid == "balanced_ternary":
        from repsynth.oracles_num.balanced_ternary import BT
        return BT(m["numeric"], m["digits"])
    from repsynth.oracles_num.binary_integer import BIN
    return BIN(m["numeric"], m["digits"])


def check_instance(name: str, root: Path, out: Path) -> dict:
    res = {}
    m = isa.derive(name, root)
    # (1) derivation
    r1 = subprocess.run([sys.executable, str(root / "gen/isb/instantiate.py"), "--check", "--root", str(root), name], capture_output=True, text=True)
    r2 = subprocess.run([sys.executable, str(root / "gen/isb/gen_ref.py"), "--check", "--root", str(root), name], capture_output=True, text=True)
    res["instance_derivation"] = {"ok": r1.returncode == 0 and r2.returncode == 0, "detail": (r1.stdout + r2.stdout).strip()}
    lib = ctypes.CDLL(str(build_lib(name, root, out)))
    u64 = ctypes.c_uint64
    for fn in ("isb_field", "isb_sfield"):
        getattr(lib, fn).restype = u64
        getattr(lib, fn).argtypes = [u64, u64, u64]
    # (2) encoding round trip
    bad, n = [], 0
    imms = {}
    for fmtn, fmt in m["formats"].items():
        if "imm" in fmt:
            hi, lo, _ = isa.field_spec(fmt, "imm")
            w = hi - lo + 1
            imms[fmtn] = sorted({0, 1, -1, 2, -2, (1 << (w - 1)) - 1, -(1 << (w - 1)), 12345 % (1 << (w - 1)), -777})
    for ins in m["instructions"]:
        fmt = m["formats"][ins["format"]]
        regs = [f for f in fmt if f in ("rd", "ra", "rb")]
        combos = [{}]
        for f in regs:
            combos = [dict(c, **{f: r}) for c in combos for r in range(16)]
        if "imm" in fmt:
            combos = [dict(c, imm=i) for c in combos[:: max(1, len(combos) // 256)] for i in imms[ins["format"]]]
        for c in combos:
            n += 1
            wd = isa.encode(m, ins["name"], **c)
            dec = isa.decode(m, wd)
            if dec != (ins["name"], c):
                bad.append(f"{ins['name']} {c}: python decode {dec}")
                continue
            for f, v in c.items():
                hi, lo, signed = isa.field_spec(fmt, f)
                cv = (lib.isb_sfield if signed else lib.isb_field)(wd, hi, lo)
                if signed and cv >> 63:
                    cv -= 1 << 64
                if cv != v:
                    bad.append(f"{ins['name']} {c}: C field {f} = {cv}")
            if lib.isb_field(wd, 31, 26) != ins["opcode"]:
                bad.append(f"{ins['name']}: C opcode field differs")
    rng = random.Random(SEED)
    legal = 0
    for _ in range(200000):
        wd = rng.getrandbits(32)
        dec = isa.decode(m, wd)
        if dec is None:
            continue
        legal += 1
        if isa.encode(m, dec[0], **dec[1]) != wd:
            bad.append(f"word {wd:08x} decodes to {dec} but re-encodes differently")
    res["encoding_round_trip"] = {"ok": not bad, "cases": n, "random_legal_words": legal, "failures": bad[:20]}
    # (3) homomorphism
    nid = m["numeric"]["identity"]["id"]
    orc = oracle(m)
    bad, cases = [], 0
    for f in m["functions"]:
        fn = getattr(lib, isa.sym(m, f["name"]))
        fn.restype = u64
        fn.argtypes = [u64, u64]
        if f["kind"] != "alu":
            continue
        vec = root / f"conformance/vectors/{nid}/{f['name']}.{m['digits']}.vec"
        head, rows = read_vectors(vec)
        for row in rows:
            a, b, r = (row[0], 0, row[1]) if f["arity"] == 1 else row
            cases += 1
            got = fn(a, b)
            if got != r:
                bad.append(f"{f['name']}({a:x}, {b:x}) = {got:x}, vector {r:x}")
    M64 = (1 << 64) - 1

    def call(fn, a, b=0):
        g = getattr(lib, isa.sym(m, fn))
        return g(a & M64, b & M64)

    if nid == "balanced_ternary":
        val = lambda w: orc.op("to_int", w)  # noqa: E731
        word = lambda x: orc.word(orc.signed(x))  # noqa: E731
        cmpv = lambda a, b: orc.op("cmp", a, b)  # noqa: E731
    else:
        val = lambda w: w & M64  # noqa: E731
        word = lambda x: x & M64  # noqa: E731
        cmpv = lambda a, b: orc.op("cmp", a, b)  # noqa: E731
    ints = [0, 1, -1, 2, -2, 4096, 0x10000000, 0x10100000, (1 << 21) - 1, -(1 << 21), (1 << 63) - 1, -(1 << 63)]
    ints += [rng.getrandbits(64) - (1 << 63) for _ in range(2000)]
    words = [word(x) for x in ints] + [rng.getrandbits(64) for _ in range(500)]
    if nid == "balanced_ternary":
        words.append(orc.invalid)
    for x in ints:
        cases += 3
        if call("imm", x) != word(x):
            bad.append(f"imm({x}) = {call('imm', x):x}, expected {word(x):x}")
        if call("word", x) != word(x):
            bad.append(f"word({x})")
        if nid == "balanced_ternary" and abs(x) <= orc.H and orc.value(call("word", x)) != x:
            bad.append(f"value(word({x})) differs")
    for w in words:
        for off in (0, 8, -8, 131071):
            cases += 1
            if call("ea", w, off) != (val(w) + off) & M64:
                bad.append(f"ea({w:x}, {off})")
        cases += 1
        if call("val", w) != val(w):
            bad.append(f"val({w:x})")
    for a in words[:200]:
        for b in words[:60] + [a]:
            cases += 4
            lt = cmpv(a, b) == M64
            exp = {"beq": int(a == b), "bne": int(a != b), "blt": int(lt), "bge": int(not lt)}
            for k, v in exp.items():
                if call(k, a, b) != v:
                    bad.append(f"{k}({a:x}, {b:x}) = {call(k, a, b)}, expected {v}")
    res["homomorphism"] = {"ok": not bad, "cases": cases, "failures": bad[:20]}
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--json")
    ap.add_argument("names", nargs="*")
    a = ap.parse_args(argv)
    root = Path(a.root)
    out = ROOT / ".cache/isb/props" / root.name
    allres, ok = {}, True
    for n in a.names or list(isa.instances(root)):
        r = check_instance(n, root, out)
        allres[n] = r
        for k, v in r.items():
            ok &= v["ok"]
            print(f"{n} {k}: {'PASS' if v['ok'] else 'FAIL'} " + json.dumps({x: y for x, y in v.items() if x != 'ok'})[:400])
    if a.json:
        Path(a.json).write_text(json.dumps(allres, indent=2) + "\n")
    print("ALL PROPERTIES HOLD" if ok else "PROPERTY FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
