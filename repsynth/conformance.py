# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Conformance engine (H5): vector generation (P2.1) and the differential runner (P2.3).

Runners: native C (dlopen), WebAssembly (Node.js), Python (cffi) and the independent oracle.
Every runner reads the same vector files (CNF-01, CNF-02)."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

from .numeric import SPECS, RefLib, spec_of, vector_lines, vector_path, read_vectors, oracle_for
from .records import ROOT, utc_now, write_record
from . import software


def generate_vectors(specs=None, root: Path = ROOT) -> int:
    t0 = utc_now()
    outs = []
    for sid in specs or list(SPECS):
        spec = spec_of(sid, root)
        software.build_native(sid, root) if not (root / "out/software" / sid / f"lib{sid}.so").exists() else None
        ref = RefLib(sid, spec, root)
        for w in spec["domain"]["widths"]:
            for op in spec["operations"]:
                p = vector_path(sid, op["name"], w["digits"], root)
                changed = software.write_if_changed(p, "\n".join(vector_lines(sid, spec, op, w["digits"], ref)) + "\n")
                outs.append(p)
                print(f"{'wrote ' if changed else 'unchanged'} {p.relative_to(root)}")
    write_record("P2.1", "vectors", "repsynth vectors", 0, started_utc=t0, outputs=outs, state="wired_unproven",
                 notes="Regeneration byte-identity is judged by the P2.1 acceptance step, not here.")
    return 0


def _python_module(sid: str, root: Path):
    d = root / "out" / "software" / sid / "py"
    so = next(d.glob(f"_rs_{sid}*.so"))
    s = importlib.util.spec_from_file_location(f"_rs_{sid}", so)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _run_python(mod, sym, vec: Path):
    f = getattr(mod.lib, sym)
    head, rows = read_vectors(vec)
    unary = " b " not in head["fields"]
    n = bad = 0
    for r in rows:
        a, b, want = (r[0], 0, r[1]) if unary else r
        n += 1
        if f(a, b) != want:
            bad += 1
    return n, bad


def _run_oracle(sid, spec, opname, digits, vec: Path):
    o = oracle_for(sid, spec, digits)
    head, rows = read_vectors(vec)
    unary = " b " not in head["fields"]
    n = bad = 0
    first = None
    for r in rows:
        a, b, want = (r[0], 0, r[1]) if unary else r
        n += 1
        got = o.op(opname, a, b)
        if got != want:
            bad += 1
            first = first or f"a={a:x} b={b:x} vector={want:x} oracle={got:x}"
    return n, bad, first


def native_runner(root: Path) -> Path:
    exe = root / "out" / "software" / "native_runner"
    src = root / "conformance" / "runners" / "native_runner.c"
    if not exe.exists() or exe.stat().st_mtime < src.stat().st_mtime:
        exe.parent.mkdir(parents=True, exist_ok=True)
        software.run(["gcc", "-std=c11", "-O2", "-Wall", "-Werror", src, "-ldl", "-o", exe])
    return exe


def conform(lane: str, specs=None, root: Path = ROOT) -> int:
    if lane != "software":
        from .lanes import LANES
        mod = LANES.get(f"conform-{lane}")
        if not mod:
            raise NotImplementedError(f"conformance lane {lane!r} is not registered")
        import importlib
        return importlib.import_module(mod).conform(specs, root)
    t0 = utc_now()
    exe = native_runner(root)
    results, total_bad, inputs = {}, 0, []
    for sid in specs or list(SPECS):
        spec = spec_of(sid, root)
        built = software.build_all(sid, root)
        pymod = _python_module(sid, root)
        for w in spec["domain"]["widths"]:
            d = w["digits"]
            for op in spec["operations"]:
                sym = op["reference"]["symbol_pattern"].replace("{width}", str(d))
                vec = vector_path(sid, op["name"], d, root)
                inputs.append(vec)
                cell = {}
                r = subprocess.run([str(exe), built["native"], sym, str(vec)], capture_output=True, text=True)
                cell["native"] = {"exit": r.returncode, "out": r.stdout.strip().splitlines()[-1:]}
                r = subprocess.run(["node", str(root / "conformance/runners/wasm_runner.mjs"), built["wasm"], sym, str(vec)],
                                   capture_output=True, text=True)
                cell["wasm"] = {"exit": r.returncode, "out": (r.stdout + r.stderr).strip().splitlines()[-1:]}
                n, bad = _run_python(pymod, sym, vec)
                cell["python"] = {"exit": 1 if bad else 0, "out": [f"python {sym} cases={n} disagreements={bad}"]}
                n, bad, first = _run_oracle(sid, spec, op["name"], d, vec)
                cell["oracle"] = {"exit": 1 if bad else 0, "out": [f"oracle {sid}.{op['name']} cases={n} disagreements={bad}" + (f" first {first}" if first else "")]}
                fails = [k for k, v in cell.items() if v["exit"] != 0]
                total_bad += len(fails)
                results[f"{sid}/{op['name']}.{d}"] = cell
                print(f"{'PASS' if not fails else 'FAIL'} {sid:17s} {op['name']}.{d:<3d} " +
                      " ".join(f"{k}={v['exit']}" for k, v in cell.items()))
    rc = 1 if total_bad else 0
    write_record("P2.3", "conform-software", "repsynth conform --lane software", rc, started_utc=t0, inputs=inputs,
                 results=results, tool_versions=_versions(), state="done" if rc == 0 else "failed")
    print(f"software conformance: {len(results)} cells, {total_bad} runner failures, exit {rc}")
    return rc


def _versions() -> dict:
    out = {}
    for name, cmd in {"gcc": ["gcc", "--version"], "clang": ["clang", "--version"], "node": ["node", "--version"],
                      "python": [sys.executable, "--version"]}.items():
        try:
            out[name] = subprocess.run(cmd, capture_output=True, text=True).stdout.splitlines()[0]
        except Exception as e:  # recorded, not hidden
            out[name] = f"not established: {e}"
    return out
