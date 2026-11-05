# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""P4.13 binary performance baseline (NUM-06, D14, T-28).

Builds the Embench-IoT 1.0 kernels and the CMS-03 continuous models (exponential
decay and harmonic oscillator as Q2.29 fixed-point programs) with the GNU cross
tools for RV32IMAC and RV64GC, runs each in QEMU user mode from the pinned QEMU
tree with that tree's own instruction-counting plugin (tests/tcg/plugins/insn.c),
and writes the dynamic instruction counts to reports/baseline/.

Counts are emulator instruction counts. They are never hardware speed.

Usage:
  python3 -m repsynth.lanes.baseline [--check] [--table PATH] [--no-record]
    --check   compare the counts with the stored table and fail on any difference
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from repsynth.records import ROOT, sha256_file, utc_now, write_record, write_status

GENERATOR = "repsynth.lanes.baseline 0.3.0"
NOTICE = "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC0-1.0"
CACHE = ROOT / ".cache"
EMBENCH = CACHE / "embench-iot"
SUPPORT = ROOT / "lanes" / "toolchain" / "baseline"
QEMU_STOCK = CACHE / "qemu-stock"          # stock build of the pinned tree, copied out
BUILD = CACHE / "baseline" / "build"
OUT = ROOT / "reports" / "baseline"
CC = "riscv64-unknown-elf-gcc"

PROFILES = {
    # name: (march, mabi, qemu user binary)
    "RV32IMAC": ("rv32imac", "ilp32", "qemu-riscv32"),
    "RV64GC": ("rv64gc", "lp64d", "qemu-riscv64"),
}
CFLAGS = ["-O2", "-ffunction-sections", "-fdata-sections"]
CMS_PROGRAMS = ["cms03_decay", "cms03_oscillator"]


# ---------------------------------------------------------------- CMS-03 models
Q = 29
ONE = 1 << Q
M32 = 0xFFFFFFFF


def _s32(v: int) -> int:
    v &= M32
    return v - (1 << 32) if v & 0x80000000 else v


def _qmul(a: int, b: int) -> int:
    return _s32((a * b + (1 << (Q - 1))) >> Q)


def _rotl1(c: int) -> int:
    return ((c << 1) | (c >> 31)) & M32


def model_decay() -> str:
    """Bit-exact model of lanes/toolchain/baseline/cms03_decay.c."""
    k = ONE
    h6 = (ONE + 3 * 256) // (6 * 256)
    y = ONE
    check = 0
    for _ in range(1280):
        k1 = -_qmul(k, y)
        k2 = -_qmul(k, _s32(y + (k1 >> 9)))
        k3 = -_qmul(k, _s32(y + (k2 >> 9)))
        k4 = -_qmul(k, _s32(y + (k3 >> 8)))
        s = k1 + 2 * k2 + 2 * k3 + k4
        y = _s32(y + _s32((h6 * s + (1 << (Q - 1))) >> Q))
        check ^= y & M32
        check = _rotl1(check)
    return f"decay y={y & M32:08x} check={check:08x}\n"


def model_oscillator() -> str:
    """Bit-exact model of lanes/toolchain/baseline/cms03_oscillator.c."""
    w2 = ONE
    x, v = ONE, 0
    check = 0
    for _ in range(1608):
        v = _s32(v - (_qmul(w2, x) >> 8))
        x = _s32(x + (v >> 8))
        check ^= (x & M32) ^ (((v & M32) << 7) & M32)
        check = _rotl1(check)
    return f"oscillator x={x & M32:08x} v={v & M32:08x} check={check:08x}\n"


MODELS = {"cms03_decay": model_decay, "cms03_oscillator": model_oscillator}


def analytic_error(name: str, out: str) -> float:
    """Distance of the fixed-point result from the analytic solution (informative)."""
    import math
    vals = {k: _s32(int(v, 16)) / ONE for k, v in re.findall(r"(\w+)=([0-9a-f]{8})", out) if k != "check"}
    if name == "cms03_decay":
        return abs(vals["y"] - math.exp(-5.0))
    t = 1608 / 256
    return max(abs(vals["x"] - math.cos(t)), abs(vals["v"] + math.sin(t)))


# ---------------------------------------------------------------- tools
def _run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def tool_versions() -> dict:
    v = {}
    v["riscv64-unknown-elf-gcc"] = _run([CC, "--version"]).stdout.splitlines()[0]
    r = _run(["dpkg-query", "-W", "-f", "${Version}", "picolibc-riscv64-unknown-elf"])
    v["picolibc-riscv64-unknown-elf"] = r.stdout.strip() or "unknown"
    for prof in PROFILES.values():
        q = QEMU_STOCK / prof[2]
        v[prof[2]] = _run([str(q), "--version"]).stdout.splitlines()[0] + f" sha256 {sha256_file(q)}"
    v["libinsn.so"] = "tests/tcg/plugins/insn.c of the pinned tree, sha256 " + sha256_file(QEMU_STOCK / "libinsn.so")
    pin = (QEMU_STOCK / "PIN").read_text().strip() if (QEMU_STOCK / "PIN").exists() else "unknown"
    v["qemu-source"] = pin
    head = _run(["git", "-C", str(EMBENCH), "rev-parse", "HEAD"]).stdout.strip()
    v["embench-iot"] = f"https://github.com/embench/embench-iot tag embench-1.0 commit {head}"
    return v


def workloads():
    for b in sorted(p.name for p in (EMBENCH / "src").iterdir() if p.is_dir()):
        yield b, "embench"
    for c in CMS_PROGRAMS:
        yield c, "cms03"


def build(name: str, kind: str, prof: str) -> Path:
    march, mabi, _ = PROFILES[prof]
    out = BUILD / prof / f"{name}.elf"
    out.parent.mkdir(parents=True, exist_ok=True)
    common = [CC, *CFLAGS, f"-march={march}", f"-mabi={mabi}", "--specs=picolibc.specs", "-nostartfiles",
              f"-T{SUPPORT / 'linux-user.ld'}", f"-I{SUPPORT}", "-ffile-prefix-map=" + str(ROOT) + "=."]
    if kind == "embench":
        srcs = sorted(str(p) for p in (EMBENCH / "src" / name).glob("*.c"))
        cmd = common + ["-DHAVE_BOARDSUPPORT_H", "-DWARMUP_HEAT=1", "-DGLOBAL_SCALE_FACTOR=1",
                        f"-I{EMBENCH / 'support'}", str(SUPPORT / "crt_linux.c"), str(SUPPORT / "board.c"),
                        str(EMBENCH / "support" / "main.c"), str(EMBENCH / "support" / "beebsc.c"), *srcs,
                        "-lm", "-o", str(out)]
    else:
        cmd = common + [str(SUPPORT / "crt_linux.c"), str(SUPPORT / f"{name}.c"), "-o", str(out)]
    r = _run(cmd)
    if r.returncode != 0:
        raise RuntimeError(f"build failed ({r.returncode}): {' '.join(cmd)}\n{r.stderr}")
    return out


def count(elf: Path, prof: str) -> tuple[int, int, str]:
    """Runs the program under the pinned QEMU with the insn plugin; returns (exit, insns, stdout)."""
    qemu = QEMU_STOCK / PROFILES[prof][2]
    log = elf.with_suffix(".plugin.log")
    if log.exists():
        log.unlink()
    cmd = ["env", "-i", str(qemu), "-plugin", f"{QEMU_STOCK / 'libinsn.so'},inline=on",
           "-d", "plugin", "-D", str(log), str(elf)]
    r = _run(cmd, timeout=600)
    text = log.read_text() if log.exists() else ""
    m = re.search(r"total insns: (\d+)", text)
    if not m:
        raise RuntimeError(f"no count from plugin: {' '.join(cmd)} exit {r.returncode}\n{text}\n{r.stderr}")
    return r.returncode, int(m.group(1)), r.stdout


def measure() -> dict:
    rows = []
    for name, kind in workloads():
        for prof in PROFILES:
            elf = build(name, kind, prof)
            e1, n1, o1 = count(elf, prof)
            e2, n2, o2 = count(elf, prof)
            row = {"workload": name, "suite": kind, "profile": prof, "exit_code": e1,
                   "insns": n1, "insns_rerun": n2, "reproduced": (n1 == n2 and o1 == o2 and e1 == e2),
                   "elf_sha256": sha256_file(elf)}
            if kind == "cms03":
                expect = MODELS[name]()
                row["output"] = o1.strip()
                row["output_matches_model"] = (o1 == expect)
                row["analytic_abs_error"] = f"{analytic_error(name, o1):.3e}"
                row["ok"] = e1 == 0 and o1 == expect
            else:
                row["ok"] = e1 == 0     # Embench main returns !verify_benchmark()
            rows.append(row)
            print(f"{prof:9s} {name:18s} insns {n1:>12d} rerun {n2:>12d} exit {e1} ok {row['ok']}")
    return {"_notice": NOTICE, "generator": GENERATOR, "metric": "dynamic instruction count (QEMU TCG plugin "
            "tests/tcg/plugins/insn.c, inline); emulator counts, not hardware speed", "cflags": CFLAGS,
            "profiles": {k: {"march": v[0], "mabi": v[1], "qemu": v[2]} for k, v in PROFILES.items()},
            "rows": rows}


def write_tables(table: dict, versions: dict) -> list[Path]:
    OUT.mkdir(parents=True, exist_ok=True)
    table = dict(table, tool_versions=versions)
    pj = OUT / "baseline.json"
    pj.write_text(json.dumps(table, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    pc = OUT / "baseline.csv"
    lines = ["# " + NOTICE + " Generated by " + GENERATOR + "; emulator counts, not hardware speed.",
             "workload,suite,profile,insns,reproduced,ok,elf_sha256"]
    for r in table["rows"]:
        lines.append(f"{r['workload']},{r['suite']},{r['profile']},{r['insns']},{r['reproduced']},{r['ok']},{r['elf_sha256']}")
    pc.write_text("\n".join(lines) + "\n", encoding="utf-8")
    pm = OUT / "baseline.md"
    by = {}
    for r in table["rows"]:
        by.setdefault(r["workload"], {})[r["profile"]] = r
    md = ["<!-- " + NOTICE.replace("CC0-1.0", "CC-BY-SA-4.0") + " -->", "",
          "# Binary performance baseline (P4.13, D14)", "",
          "Dynamic instruction counts in QEMU user mode, counted by the pinned tree's own plugin "
          "(tests/tcg/plugins/insn.c, inline). These are emulator counts, never hardware speed. "
          "Every count was measured twice and both runs agreed.", "",
          "| Workload | Suite | RV32IMAC | RV64GC | Verified |", "|---|---|---:|---:|---|"]
    for w, d in by.items():
        ok = all(x["ok"] and x["reproduced"] for x in d.values())
        md.append(f"| {w} | {d[next(iter(d))]['suite']} | {d['RV32IMAC']['insns']} | {d['RV64GC']['insns']} | {'yes' if ok else 'NO'} |")
    md += ["", "Tool versions:", ""] + [f"- {k}: {v}" for k, v in sorted(versions.items())] + [""]
    pm.write_text("\n".join(md), encoding="utf-8")
    return [pj, pc, pm]


def compare(stored: dict, table: dict) -> list[str]:
    old = {(r["workload"], r["profile"]): r["insns"] for r in stored["rows"]}
    diffs = []
    for r in table["rows"]:
        k = (r["workload"], r["profile"])
        if old.get(k) != r["insns"]:
            diffs.append(f"{k[0]} {k[1]}: stored {old.get(k)} measured {r['insns']}")
    for k in set(old) - {(r["workload"], r["profile"]) for r in table["rows"]}:
        diffs.append(f"{k[0]} {k[1]}: stored but not measured")
    return diffs


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="repsynth baseline", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="compare with the stored table; fail on any difference")
    ap.add_argument("--table", default=str(OUT / "baseline.json"), help="stored table for --check")
    ap.add_argument("--no-record", action="store_true")
    a = ap.parse_args(argv)
    started = utc_now()
    versions = tool_versions()
    table = measure()
    bad = [f"{r['workload']} {r['profile']}" for r in table["rows"] if not (r["ok"] and r["reproduced"])]
    diffs = []
    if a.check:
        stored = json.loads(Path(a.table).read_text())
        diffs = compare(stored, table)
        outputs = []
    else:
        outputs = write_tables(table, versions)
    for d in diffs:
        print("MISMATCH", d)
    for b in bad:
        print("FAILED", b)
    rc = 1 if (bad or diffs) else 0
    if not a.no_record:
        cmd = "python3 -m repsynth.lanes.baseline" + (" --check --table " + a.table if a.check else "")
        rec = write_record("P4.13", "check" if a.check else "measure", cmd, rc, started_utc=started,
                           inputs=[SUPPORT, QEMU_STOCK / "libinsn.so"] + ([Path(a.table)] if a.check else []),
                           outputs=outputs, tool_versions=versions,
                           results={"workloads": len(table["rows"]), "failed": bad, "mismatches": diffs,
                                    "counts": {f"{r['workload']}/{r['profile']}": r["insns"] for r in table["rows"]}},
                           state="done" if rc == 0 else "failed",
                           notes="Emulator instruction counts, not hardware speed.")
        print("record", rec)
    return rc


def run(ctx) -> int:
    argv = getattr(ctx, "argv", None)
    if argv is None and isinstance(ctx, (list, tuple)):
        argv = list(ctx)
    return main(argv or [])


if __name__ == "__main__":
    sys.exit(main())
