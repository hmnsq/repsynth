# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mutation self-tests (CNF-04): each gate is shown refusing planted defects before it is trusted.

Lanes here: spec (P1.1, T-01), software (P2.5, T-09/T-10). Other lanes register their own selftest
through LANES["selftest-<lane>"]. Mutants are planted only in copies under out/mutants/."""
from __future__ import annotations

import copy
import importlib
import json
import re
import shutil
import subprocess
from pathlib import Path

from .records import ROOT, utc_now, write_record
from .spec import check, load_spec, SpecError
from .numeric import SPECS, spec_of, vector_path

MUT = ROOT / "out" / "mutants"


def _refused(spec, path) -> tuple[bool, str]:
    errs = check(spec, path)
    return bool(errs), "; ".join(f"{e.path}: {e.message}" for e in errs)[:300]


def selftest_spec() -> dict:
    """Planted defects: a missing section, a guessed value in place of not_established, an undefined
    reference function (P1.1 acceptance)."""
    base_path = ROOT / SPECS["balanced_ternary"]["path"]
    base = load_spec(base_path)
    assert not check(base, base_path), "the unmutated specification must validate first"
    cases = {}
    m = copy.deepcopy(base); del m["evolution"]; cases["missing section (evolution)"] = m
    g = copy.deepcopy(base); g["substrate"]["limits"]["hardware_area"] = 1200; cases["guessed value where not_established stood (/substrate/limits/hardware_area)"] = g
    g2 = copy.deepcopy(base); g2["provenance"]["oracle"] = "not_established"; cases["bare not_established without reason (/provenance/oracle)"] = g2
    u = copy.deepcopy(base); u["operations"][1]["reference"]["symbol_pattern"] = "bt_addx{width}"; cases["undefined reference function (bt_addx32)"] = u
    d = copy.deepcopy(base); d["operations"].append(copy.deepcopy(d["operations"][0])); cases["duplicate operation"] = d
    out = {}
    for name, s in cases.items():
        refused, why = _refused(s, base_path)
        out[name] = {"caught": refused, "refusal": why}
        print(f"  spec mutant {'CAUGHT' if refused else 'MISSED'}: {name} -> {why}")
    return out


SOFTWARE_MUTANTS = [
    # (spec, description, regex, replacement)
    ("balanced_ternary", "table entry: codec lookup maps code 01 to 0 instead of +1",
     None, None),  # handled specially on the generated codec
    ("balanced_ternary", "off-by-one: shl drops one trit too many", r"for \(unsigned i = n; i > k; i--\)", "for (unsigned i = n; i > k + 1u; i--)"),
    ("balanced_ternary", "swapped operands: sub computes b - a", r"return encode\(decode\(a, n\) - decode\(b, n\), n\);", "return encode(decode(b, n) - decode(a, n), n);"),
    ("binary_integer", "off-by-one: 32-bit shift mask 31 becomes 32", r"return m32\(m32\(a\) << \(b & 31u\)\);", "return m32(m32(a) << (b & 32u));"),
    ("binary_integer", "swapped operands: sub64 computes b - a", r"uint64_t bin_sub64\(uint64_t a, uint64_t b\) \{ return a - b; \}", "uint64_t bin_sub64(uint64_t a, uint64_t b) { return b - a; }"),
    ("packed_decimal", "table entry: minus sign nibble D written as B", r"uint64_t w = \(neg && m != 0u\) \? 0xdu : 0xcu;", "uint64_t w = (neg && m != 0u) ? 0xbu : 0xcu;"),
    ("packed_decimal", "off-by-one: multiplication skips the top digit", r"for \(unsigned i = 1; i <= d; i\+\+\) \{\n    uint64_t dig", "for (unsigned i = 1; i < d; i++) {\n    uint64_t dig"),
]


def _mutant_tree(sid: str, idx: int) -> Path:
    src = ROOT / "spec" / "ref" / sid
    dst = MUT / f"{sid}_{idx}"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)
    return dst


def _caught_by_native(sid: str, tree: Path) -> tuple[bool, str]:
    """Build the mutant and run the native runner on every vector file of the spec."""
    from .conformance import native_runner
    spec = spec_of(sid)
    so = tree / f"lib{sid}.so"
    r = subprocess.run(["gcc", "-std=c11", "-O2", "-fPIC", "-shared", f"-I{tree}", str(tree / f"{sid}.c"), "-o", str(so)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return True, f"mutant does not compile (exit {r.returncode}): {r.stderr[:200]}"
    exe = native_runner(ROOT)
    failed = []
    for w in spec["domain"]["widths"]:
        for op in spec["operations"]:
            sym = op["reference"]["symbol_pattern"].replace("{width}", str(w["digits"]))
            r = subprocess.run([str(exe), str(so), sym, str(vector_path(sid, op["name"], w["digits"]))], capture_output=True, text=True)
            if r.returncode != 0:
                failed.append(sym)
    return bool(failed), f"failing runners: {', '.join(failed)}" if failed else "no runner failed"


def selftest_software() -> dict:
    out = {}
    for i, (sid, desc, pat, rep) in enumerate(SOFTWARE_MUTANTS):
        tree = _mutant_tree(sid, i)
        if pat is None:
            f = tree / "bt_codec.h"
            text = f.read_text()
            new = re.sub(r"static const int lut\[4\] = \{(-?\d+), (-?\d+),", r"static const int lut[4] = {\1, 0,", text, count=1)
        else:
            f = tree / f"{sid}.c"
            text = f.read_text()
            new, n = re.subn(pat, rep, text, count=1)
            if n != 1:
                out[desc] = {"caught": False, "refusal": f"mutation anchor not found: {pat}"}
                print(f"  software mutant NOT PLANTED: {desc}")
                continue
        if new == text:
            out[desc] = {"caught": False, "refusal": "mutation did not change the file"}
            continue
        f.write_text(new)
        caught, why = _caught_by_native(sid, tree)
        out[desc] = {"caught": caught, "refusal": why[:300]}
        print(f"  software mutant {'CAUGHT' if caught else 'MISSED'}: {sid}: {desc} -> {why[:160]}")
    return out


def selftest(lane: str = "all") -> int:
    from .lanes import LANES, load_lane
    t0 = utc_now()
    results = {}
    if lane in ("all", "spec"):
        results["spec"] = selftest_spec()
    if lane in ("all", "software"):
        results["software"] = selftest_software()
    for name in sorted(LANES):
        if name.startswith("selftest-") and lane in ("all", name[len("selftest-"):]):
            m = load_lane(name)
            key = name[len("selftest-"):]
            if m is None:
                results[key] = {"lane failed to load": {"caught": False, "refusal": "see LANE ERROR above"}}
                continue
            results[key] = m.selftest()
    planted = sum(len(v) for v in results.values())
    caught = sum(1 for v in results.values() for x in v.values() if x["caught"])
    rc = 0 if planted and planted == caught else 1
    rep = ROOT / "reports" / "mutation" / f"selftest_{lane}.json"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps({"planted": planted, "caught": caught, "lanes": results}, indent=2, ensure_ascii=False) + "\n")
    for ln in results:
        packet = {"spec": "P1.1", "software": "P2.5"}.get(ln, f"selftest-{ln}")
        write_record(packet, f"selftest-{ln}", f"repsynth selftest --lane {ln}", 0 if all(x["caught"] for x in results[ln].values()) else 1,
                     started_utc=t0, outputs=[rep], results=results[ln],
                     state="done" if all(x["caught"] for x in results[ln].values()) else "failed")
    print(f"selftest {lane}: planted {planted}, caught {caught}, exit {rc}")
    return rc
