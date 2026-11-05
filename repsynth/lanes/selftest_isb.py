# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tier B mutation self-test (CNF-04, P7.4, T-27; Test Plan section 8).

QEMU mutants are planted in the derived tree .cache/isb/qemu (never in the generated tree or the pinned
clone); the machine's binary is rebuilt, the unchanged vector image is booted, and the mutant is caught when
the run does not pass (a FAIL line with a non-zero exit, a fault exit or a timeout). The tree is restored by
re-applying the generated patch set (which rewrites every copied file whose bytes differ) and rebuilt.

Planted on each machine:
  wrong-opcode-field   insn.decode: the opcode fields of add and sub exchanged
  swapped-operands     op_helper.c: the sub helper calls the reference function with b, a
  wrong-carry-rule     binary: bin_add64 drops the carry from bit 31 into bit 32; ternary: the encoder
                       keeps digit -1 for a remainder of 2 but drops its carry into the next trit
  wrong-branch-rule    op_helper.c: the blt helper answers bge
Planted on the specification gates (in a copy of the tree under .cache/isb/mutroot):
  spec-drift           an instance specification's opcode edited by hand (instance_derivation)
  ref-swapped          the twm sub reference delegation with swapped operands (homomorphism)
  asm-opcode           the customasm rule of add with the opcode of sub (assemble and decode round trip)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

from repsynth.records import ROOT, utc_now, write_record, write_status

QM = [  # (id, file under target/<n>/, {n: (old, new)})
    ("wrong-opcode-field", "insn.decode", None),
    ("swapped-operands", "op_helper.c", {"bwm": ("return bwm_sub64(a, b);", "return bwm_sub64(b, a);"),
                                         "twm": ("return twm_sub32(a, b);", "return twm_sub32(b, a);")}),
    ("wrong-carry-rule", None, {"bwm": ("ref/binary_integer.c", "uint64_t bin_add64(uint64_t a, uint64_t b) { return a + b; }",
                                        "uint64_t bin_add64(uint64_t a, uint64_t b) { return (a & 0xffffffff00000000u) + "
                                        "(b & 0xffffffff00000000u) + ((a + b) & 0xffffffffu); }"),
                                "twm": ("ref/balanced_ternary.c", "    if (t == 2) t = -1;\n",
                                        "    if (t == 2) { t = -1; v -= 3; }\n")}),
    ("wrong-branch-rule", "op_helper.c", {"bwm": ("return bwm_blt64(a, b);", "return bwm_bge64(a, b);"),
                                          "twm": ("return twm_blt32(a, b);", "return twm_bge32(a, b);")}),
]


def _swap_opcodes(text: str) -> str:
    lines = text.splitlines(keepends=True)
    ia = next(i for i, l in enumerate(lines) if l.startswith("add "))
    ib = next(i for i, l in enumerate(lines) if l.startswith("sub "))
    pa, pb = lines[ia].split()[1], lines[ib].split()[1]
    lines[ia] = lines[ia].replace(pa, pb, 1)
    lines[ib] = lines[ib].replace(pb, pa, 1)
    return "".join(lines)


def _plant(n: str, mid: str, rel, change) -> Path:
    from repsynth.lanes import isb
    base = isb.QTREE / f"target/{n}"
    if mid == "wrong-opcode-field":
        f = base / "insn.decode"
        f.write_text(_swap_opcodes(f.read_text()))
        return f
    if rel is None:
        rel, old, new = change[n]
    else:
        old, new = change[n]
    f = base / rel
    t = f.read_text()
    if t.count(old) != 1:
        raise RuntimeError(f"mutant {mid} on {n}: anchor {old!r} found {t.count(old)} times in {f}")
    f.write_text(t.replace(old, new))
    return f


def _restore() -> int:
    from repsynth.lanes import isb
    c, out = isb.sh([sys.executable, "gen/isb/patch.py", "--tree", str(isb.QTREE), "gen/isb/targets/qemu_patches.json"])
    return c


def qemu_mutants(names=("bwm", "twm")) -> dict:
    from repsynth.lanes import isb
    out = {}
    for n in names:
        for mid, rel, change in QM:
            key = f"{n}:{mid}"
            try:
                f = _plant(n, mid, rel, change)
                c, log = isb.build_qemu((f"qemu-system-{n}",), log_name=f"isb_mutant_{n}_{mid}")
                if c:
                    out[key] = {"caught": False, "refusal": f"mutant build failed (exit {c}); not a test result: {log[-300:]}"}
                    continue
                r = isb.run_vectors(n, timeout=120)
                caught = not r["pass"]
                why = ("timeout" if r["timeout"] else f"exit {r['exit_code']}") + \
                      (f", {'; '.join(r['fail_lines'])}" if r["fail_lines"] else "") + \
                      (", machine check failed" if not r["machine_ok"] else "")
                out[key] = {"caught": caught, "refusal": f"vector image did not pass: {why}" if caught else
                            f"vector image passed with the mutant planted in {f.relative_to(isb.QTREE)}"}
            finally:
                _restore()
    # rebuild clean binaries and show the clean image passes again
    c, _ = isb.build_qemu(tuple(f"qemu-system-{n}" for n in names), log_name="isb_qemu_rebuild_after_mutants")
    for n in names:
        r = isb.run_vectors(n)
        out[f"{n}:clean-after-restore"] = {"caught": False, "refusal": f"clean image pass={r['pass']} exit {r['exit_code']}",
                                           "clean_pass": r["pass"] and c == 0}
    return out


def _mutroot() -> Path:
    mr = ROOT / ".cache/isb/mutroot"
    if mr.exists():
        shutil.rmtree(mr)
    (mr / "conformance").mkdir(parents=True)
    shutil.copytree(ROOT / "spec", mr / "spec")
    shutil.copytree(ROOT / "gen/isb", mr / "gen/isb", ignore=shutil.ignore_patterns("__pycache__"))
    (mr / "conformance/vectors").symlink_to(ROOT / "conformance/vectors")
    return mr


def spec_mutants() -> dict:
    py = sys.executable
    out = {}
    # spec-drift
    mr = _mutroot()
    f = mr / "spec/reps/machine/bwm.yaml"
    t = f.read_text()
    old = "- name: li\n        opcode: 32"
    assert t.count(old) == 1, "spec-drift anchor"
    f.write_text(t.replace(old, "- name: li\n        opcode: 38"))
    p = subprocess.run([py, "conformance/runners/isb/properties.py", "--root", str(mr), "bwm"], cwd=ROOT, capture_output=True, text=True)
    out["spec-drift"] = {"caught": p.returncode != 0 and "instance_derivation: FAIL" in p.stdout,
                         "refusal": next((l for l in p.stdout.splitlines() if "FAIL" in l), p.stdout[-200:])[:300]}
    # ref-swapped
    mr = _mutroot()
    f = mr / "spec/ref/machine_twm/twm.c"
    t = f.read_text()
    old = "{ return bt_sub32(a, b); }"
    assert t.count(old) == 1
    f.write_text(t.replace(old, "{ return bt_sub32(b, a); }"))
    p = subprocess.run([py, "conformance/runners/isb/properties.py", "--root", str(mr), "twm"], cwd=ROOT, capture_output=True, text=True)
    out["ref-swapped"] = {"caught": p.returncode != 0 and "homomorphism: FAIL" in p.stdout,
                          "refusal": next((l for l in p.stdout.splitlines() if "homomorphism: FAIL" in l), p.stdout[-200:])[:300]}
    # asm-opcode
    mr = _mutroot()
    f = mr / "gen/isb/targets/bwm/bwm.cpu.asm"
    t = f.read_text()
    old = "    add {rd: reg}, {ra: reg}, {rb: reg} => $le(2`6"
    assert t.count(old) == 1
    f.write_text(t.replace(old, "    add {rd: reg}, {ra: reg}, {rb: reg} => $le(3`6"))
    p = subprocess.run([py, "conformance/runners/isb/asm_roundtrip.py", "--root", str(mr), "bwm"], cwd=ROOT, capture_output=True, text=True)
    out["asm-opcode"] = {"caught": p.returncode != 0, "refusal": next((l for l in p.stdout.splitlines() if "FAIL" in l), p.stdout[-200:])[:300]}
    shutil.rmtree(ROOT / ".cache/isb/mutroot")
    return out


def run_mutants(qemu: bool = True) -> dict:
    out = {f"spec:{k}": v for k, v in spec_mutants().items()}
    if qemu:
        out.update({f"qemu:{k}": v for k, v in qemu_mutants().items()})
    return out


def selftest() -> dict:
    """Interface for `repsynth selftest`: {description: {"caught": bool, "refusal": str}}."""
    return {k: {"caught": v["caught"], "refusal": v["refusal"]} for k, v in run_mutants().items() if "clean-after" not in k}


def run_and_record() -> int:
    t0 = utc_now()
    res = run_mutants()
    planted = {k: v for k, v in res.items() if "clean-after" not in k}
    caught = sum(v["caught"] for v in planted.values())
    clean = all(v.get("clean_pass") for k, v in res.items() if "clean-after" in k)
    for k, v in res.items():
        print(f"{k}: caught={v['caught']} {v['refusal']}")
    print(f"planted {len(planted)}, caught {caught}, clean images pass after restore: {clean}")
    rc = 0 if caught == len(planted) and clean else 1
    rep = ROOT / "reports/mutation/selftest_isb.json"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps({"_notice": "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC0-1.0",
                               "planted": len(planted), "caught": caught, "clean_after_restore": clean, "mutants": res}, indent=2) + "\n")
    rec = write_record("P7.4", "selftest", "python3 -m repsynth isb selftest", rc, started_utc=t0,
                       outputs=["reports/mutation/selftest_isb.json"], results={"planted": len(planted), "caught": caught,
                                                                                "clean_after_restore": clean},
                       state="done" if rc == 0 else "failed")
    print(f"record {rec.relative_to(ROOT)}")
    return rc
