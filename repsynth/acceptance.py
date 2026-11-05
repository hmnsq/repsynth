# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Acceptance commands of the spine's packets (Build Plan accepted_when), each writing a run record
and the packet's status file. Usage: python3 -m repsynth.acceptance <packet>"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

from .records import ROOT, utc_now, write_record, write_status

PY = sys.executable


def _sh(cmd, cwd=ROOT, timeout=3600):
    print("+", " ".join(cmd), flush=True)
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    out = (r.stdout + r.stderr)
    print(out[-4000:])
    return r.returncode, out


def _finish(packet, step, cmd, rc, t0, summary_ok, summary_fail, outputs=(), results=None, blocked=()):
    state = "done" if rc == 0 else "failed"
    rec = write_record(packet, step, cmd, rc, started_utc=t0, outputs=outputs, results=results or {}, state=state)
    write_status(packet, state, [rec.relative_to(ROOT)], summary_ok if rc == 0 else summary_fail, blocked)
    return rc


def p1_1():
    t0 = utc_now()
    rc1, o1 = _sh([PY, "-m", "repsynth", "spec", "check", "spec/reps/numeric/balanced_ternary.yaml",
                   "spec/reps/numeric/binary_integer.yaml", "spec/reps/numeric/packed_decimal.yaml"])
    rc2, o2 = _sh([PY, "-m", "repsynth", "selftest", "--lane", "spec"])
    rc = rc1 or rc2
    return _finish("P1.1", "acceptance", "repsynth spec check spec/reps/numeric/*.yaml; repsynth selftest --lane spec", rc, t0,
                   "The three numeric specifications validate; five planted defects (missing section, guessed value, bare not_established, undefined reference function, duplicate operation) are each refused with the path named.",
                   "Validation or a planted-defect refusal failed; see the record.",
                   outputs=[ROOT / "reports/mutation/selftest_spec.json"], results={"check": o1[-1500:], "selftest": o2[-1500:]})


def p1_2():
    t0 = utc_now()
    rc, o = _sh([PY, "-m", "pytest", "-q", "tests/test_canonical.py"])
    return _finish("P1.2", "acceptance", "pytest tests/test_canonical.py", rc, t0,
                   "Hypothesis property tests (500 examples) show slice hashes unchanged by key order and whitespace and changed by any change of value.",
                   "Property tests failed.", results={"pytest": o[-1500:]})


def _verify(sid, packet, summary):
    from .numeric import verify_reference
    from . import software
    t0 = utc_now()
    software.build_native(sid)
    res = verify_reference(sid)
    bad = sum(v["disagreements"] for v in res.values())
    cases = sum(v["cases"] for v in res.values())
    rep = ROOT / "reports" / "numeric" / f"{sid}_reference_vs_oracle.json"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps(res, indent=2) + "\n")
    return bad, cases, rep, t0


def p1_3():
    bad, cases, rep, t0 = _verify("balanced_ternary", "P1.3", "")
    return _finish("P1.3", "acceptance", "repsynth.numeric.verify_reference('balanced_ternary')", 1 if bad else 0, t0,
                   f"Every reference function agrees with the arbitrary-precision oracle on {cases} cases: exhaustive over the low 12 trits (unary) and low 6 trits (binary) with invalid codes, boundary cases and 100000 seeded random cases per operation at full width, both widths.",
                   f"{bad} disagreements; see the report.", outputs=[rep], results={"cases": cases, "disagreements": bad})


def p1_4():
    b1, c1, r1, t0 = _verify("packed_decimal", "P1.4", "")
    b2, c2, r2, _ = _verify("binary_integer", "P1.4", "")
    bad = b1 + b2
    return _finish("P1.4", "acceptance", "repsynth.numeric.verify_reference('packed_decimal'); ...('binary_integer')", 1 if bad else 0, t0,
                   f"Packed decimal agrees with Python's decimal module on {c1} cases (every signed 3-digit operand pair, boundary and 100000 seeded random per operation); the binary baseline agrees with Python integers on {c2} cases.",
                   f"{bad} disagreements.", outputs=[r1, r2], results={"cases": c1 + c2, "disagreements": bad})


def p2_1():
    t0 = utc_now()
    vec = ROOT / "conformance" / "vectors"
    def digest():
        h = hashlib.sha256()
        for p in sorted(vec.rglob("*.vec")):
            h.update(p.relative_to(vec).as_posix().encode() + b"\0" + p.read_bytes())
        return h.hexdigest()
    before = digest()
    shutil.rmtree(vec)
    rc, o = _sh([PY, "-m", "repsynth", "vectors"])
    after = digest()
    headers_ok = all(any(l.startswith("# slice_sha256:") for l in p.read_text().splitlines()[:10]) and
                     any(l.startswith("# version:") for l in p.read_text().splitlines()[:10]) for p in vec.rglob("*.vec"))
    ok = rc == 0 and before == after and headers_ok
    return _finish("P2.1", "acceptance", "rm -r conformance/vectors; repsynth vectors; compare digests", 0 if ok else 1, t0,
                   f"Vector files were deleted and regenerated byte-identically (tree digest {after[:16]}); every file carries the specification identifier, version and slice hash.",
                   f"Regeneration differed or headers missing (before {before[:16]}, after {after[:16]}).",
                   results={"before": before, "after": after, "headers_ok": headers_ok})


def p2_3():
    t0 = utc_now()
    rc, o = _sh([PY, "-m", "repsynth", "conform", "--lane", "software"])
    return _finish("P2.3", "acceptance", "repsynth conform --lane software", rc, t0,
                   "repsynth conform --lane software exits 0: native C, WebAssembly (Node.js), Python (cffi) and the oracle agree on every vector of 46 cells. Legacy runners join when P2.2's legacy builds exist.",
                   "Conformance failed.", results={"tail": o[-2000:]})


def p2_4():
    t0 = utc_now()
    rc1, o1 = _sh([PY, "-m", "pytest", "-q", "tests/test_properties.py"])
    rc2, o2 = _sh([PY, "tests/prove_bounded.py"])
    caught = {}
    for pair in ("balanced_ternary_0", "binary_integer_4", "packed_decimal_5"):
        sid = pair.rsplit("_", 1)[0]
        d = ROOT / "out" / "mutants" / f"libdir_{sid}"
        if d.exists():
            shutil.rmtree(d)
        for s in ("balanced_ternary", "binary_integer", "packed_decimal"):
            (d / s).mkdir(parents=True)
            shutil.copy(ROOT / "out/software" / s / f"lib{s}.so", d / s)
        shutil.copy(ROOT / "out/mutants" / pair / f"lib{sid}.so", d / sid)
        r = subprocess.run([PY, "-m", "pytest", "-q", "tests/test_properties.py"], cwd=ROOT, capture_output=True, text=True,
                           env={**__import__("os").environ, "REPSYNTH_LIBDIR": str(d)})
        caught[pair] = r.returncode != 0
        print(f"mutant {pair}: property suite exit {r.returncode} -> {'CAUGHT' if r.returncode else 'MISSED'}")
    ok = rc1 == 0 and rc2 == 0 and all(caught.values())
    return _finish("P2.4", "acceptance", "pytest tests/test_properties.py; python3 tests/prove_bounded.py; suites against planted mutants", 0 if ok else 1, t0,
                   "Hypothesis suites pass for all three specifications; a defect planted in each specification's software is found by its suite; Z3 proves the pair-encoded ripple adder homomorphic with integer addition modulo 3^n for n = 1 to 6 (a model of the trit rule, not of the C source).",
                   "A suite failed, the proof failed, or a mutant was missed.", results={"mutants_caught": caught})


def p2_5():
    t0 = utc_now()
    rc, o = _sh([PY, "-m", "repsynth", "selftest", "--lane", "software"])
    return _finish("P2.5", "acceptance", "repsynth selftest --lane software", rc, t0,
                   "Seven planted defects (codec table entry, sign-nibble table entry, two off-by-ones, an off-by-one in decimal multiply, two swapped-operand defects) are each caught by the conformance runners.",
                   "A planted defect was missed.", outputs=[ROOT / "reports/mutation/selftest_software.json"])


def p3_tests(packet):
    t0 = utc_now()
    rc, o = _sh([PY, "-m", "pytest", "-q", "tests/test_graph.py"])
    msg = {"P3.1": "A generator reading an undeclared path fails, naming specification#path; generators refuse not_established values, naming them.",
           "P3.2": "Slices are written on change only and Ninja restats outputs: changing one operation's slice regenerates exactly that operation's two vector files, judged by output hashes.",
           "P3.3": "graph/edges.txt holds typed edges; every artefact has an implements or validates edge, and graph/edges.dot regenerates identically from the list."}[packet]
    return _finish(packet, "acceptance", "pytest tests/test_graph.py", rc, t0, msg, "Graph tests failed.", results={"tail": o[-1500:]})


def p3_5():
    """D2 over software artefacts for the changes that exist; (a) and (b) are blocked until P1.7 and P1.6."""
    t0 = utc_now()
    work = ROOT / ".cache" / "tmp" / "d2"
    if work.exists():
        shutil.rmtree(work)
    work.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", str(ROOT), str(work)], check=True)
    subprocess.run([PY, "-m", "repsynth", "gen"], cwd=work, capture_output=True)
    res = {}
    for c in ("c", "d"):
        rc, o = _sh([PY, "-m", "repsynth", "impact", c, "--confirm"], cwd=work)
        res[c] = rc
    for p in (work / "reports" / "impact").glob("*.json"):
        dst = ROOT / "reports" / "impact" / p.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(p, dst)
    blocked = []
    for c, why in (("a", "P1.7 (AyeHandSum not located)"), ("b", "P1.6 and P6.3 (APCISR grid specification and derived build)")):
        try:
            from .impact_cases import resolve_change
            resolve_change(c, ROOT)
        except NotImplementedError:
            blocked.append(why)
    ok_cd = all(v == 0 for v in res.values())
    state = "wired_unproven" if ok_cd and blocked else ("done" if ok_cd else "failed")
    rec = write_record("P3.5", "acceptance", "repsynth impact c|d --confirm (in a clone)", 0 if ok_cd else 1, started_utc=t0,
                       outputs=list((ROOT / "reports" / "impact").glob("*.json")), results=res, state=state)
    write_status("P3.5", state, [rec.relative_to(ROOT)],
                 ("Changes (c) new operation and (d) trit encoding regenerate exactly their expected sets (predicted = observed = expected) and the baseline is restored; "
                  "changes (a) and (b) are not run yet.") if ok_cd else "A DEP-05 change did not regenerate exactly its expected set.", blocked)
    # P3.4 rides on the same runs: predicted equals observed for every case run
    write_status("P3.4", "done" if ok_cd else "failed", [rec.relative_to(ROOT)],
                 "repsynth impact predicts artefacts and conformance cells before the build; post-build confirmation shows predicted equal to observed for cases (c) and (d)." if ok_cd else "Prediction differed from observation.")
    return 0 if ok_cd else 1


PACKETS = {"P1.1": p1_1, "P1.2": p1_2, "P1.3": p1_3, "P1.4": p1_4, "P2.1": p2_1, "P2.3": p2_3, "P2.4": p2_4,
           "P2.5": p2_5, "P3.1": lambda: p3_tests("P3.1"), "P3.2": lambda: p3_tests("P3.2"), "P3.3": lambda: p3_tests("P3.3"),
           "P3.5": p3_5}

if __name__ == "__main__":
    rc = 0
    for p in sys.argv[1:]:
        print(f"=== acceptance {p}")
        rc |= PACKETS[p]()
    raise SystemExit(rc)
