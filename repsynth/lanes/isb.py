# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tier B lane driver (H11; packets P7.1 to P7.5, demonstrator D7).

  python3 -m repsynth isb spec        P7.1  instances, reference functions, spec check, properties
  python3 -m repsynth isb asm         P7.3  customasm definitions, round trip, test images
  python3 -m repsynth isb qemu        P7.2  QEMU target generation, anchor patches, derived build
  python3 -m repsynth isb boot        P7.4  vectors on both targets, workload counts (mutation: selftest)
  python3 -m repsynth isb selftest    P7.4  mutation self-test (CNF-04)
  python3 -m repsynth isb binutils    P7.5  (SHOULD) records its state
  python3 -m repsynth isb all

Every step writes a run record and the packet's status file. The derived QEMU tree is .cache/isb/qemu (a
copy of the pinned tree .cache/qemu-src without its .git, plus the subprojects the Tier A derived tree
fetched); the pinned clone is never written.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from repsynth.records import ROOT, sha256_file, utc_now, write_record, write_status

PY = sys.executable
GEN = ROOT / "gen/isb"
CACHE = ROOT / ".cache/isb"
QTREE = CACHE / "qemu"
QBUILD = CACHE / "qemu-build"
PINNED = ROOT / ".cache/qemu-src"
CUSTOMASM = CACHE / "customasm/bin/customasm"
CUSTOMASM_VERSION = "0.14.2"
LOGS = ROOT / ".cache/logs"
NAMES = ("bwm", "twm")
CONFIGURE = ["--target-list=bwm-softmmu,twm-softmmu", "--without-default-features", "--enable-tcg",
             "--enable-plugins", "--disable-docs", "--disable-werror"]


def sh(cmd, cwd=ROOT, log: Path | None = None, timeout=None) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    out = p.stdout + p.stderr
    if log:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(" ".join(map(str, cmd)) + "\n" + out)
    return p.returncode, out


def tool_versions() -> dict:
    v = {}
    try:
        v["customasm"] = subprocess.run([str(CUSTOMASM), "--version"], capture_output=True, text=True).stdout.split("\n")[0].strip()
    except OSError:
        v["customasm"] = "missing"
    try:
        v["qemu-source"] = "pinned tree " + subprocess.run(["git", "-C", str(PINNED), "describe", "--tags"], capture_output=True, text=True).stdout.strip() + \
            " commit " + subprocess.run(["git", "-C", str(PINNED), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        pass
    v["gcc"] = subprocess.run(["gcc", "--version"], capture_output=True, text=True).stdout.split("\n")[0]
    for n in NAMES:
        b = QBUILD / f"qemu-system-{n}"
        if b.exists():
            v[f"qemu-system-{n}"] = sha256_file(b)
    return v


def qemu_bin(n: str) -> Path:
    return QBUILD / f"qemu-system-{n}"


def image_path(n: str, img: str = "vectors") -> Path:
    return CACHE / "images" / n / f"{img}.bin"


def expected_cases(n: str) -> dict:
    sys.path.insert(0, str(GEN))
    import isa
    from repsynth.numeric import read_vectors
    m = isa.derive(n, ROOT)
    nid = m["numeric"]["identity"]["id"]
    return {o["name"]: len(read_vectors(ROOT / f"conformance/vectors/{nid}/{o['name']}.{m['digits']}.vec")[1])
            for o in m["numeric"]["operations"]}


# ---------------------------------------------------------------- P7.1
def step_spec() -> int:
    t0 = utc_now()
    res, rc = {}, 0
    for cmd in ([PY, "gen/isb/instantiate.py"], [PY, "gen/isb/gen_ref.py"],
                [PY, "-m", "repsynth", "spec", "check", "spec/reps/machine/word_machine_family.yaml",
                 "spec/reps/machine/bwm.yaml", "spec/reps/machine/twm.yaml"],
                [PY, "conformance/runners/isb/properties.py", "--json", str(ROOT / "reports/isb/properties.json")]):
        c, out = sh(cmd)
        res[" ".join(cmd[1:])] = {"exit_code": c, "tail": out[-1500:]}
        print(out.rstrip())
        rc |= c
    outs = ["spec/reps/machine/bwm.yaml", "spec/reps/machine/twm.yaml", "spec/ref/machine_bwm/bwm.c",
            "spec/ref/machine_twm/twm.c", "reports/isb/properties.json"]
    state = "done" if rc == 0 else "failed"
    rec = write_record("P7.1", "spec", "python3 -m repsynth isb spec", rc, started_utc=t0,
                       inputs=["spec/reps/machine/word_machine_family.yaml", "spec/reps/numeric/binary_integer.yaml",
                               "spec/reps/numeric/balanced_ternary.yaml", "spec/ref/machine_family/word_machine_family.h"],
                       outputs=outs, tool_versions={"gcc": tool_versions()["gcc"]}, results=res, state=state)
    print(f"record {rec.relative_to(ROOT)}")
    return rc


# ---------------------------------------------------------------- P7.3
def assemble(src: list[Path], out: Path, cwd: Path) -> tuple[int, str]:
    out.parent.mkdir(parents=True, exist_ok=True)
    return sh([str(CUSTOMASM), "-q", "--color=off"] + [os.path.relpath(s, cwd) for s in src] +
              ["-f", "binary", "-o", str(out)], cwd=cwd)


def build_images() -> dict:
    res = {}
    for n in NAMES:
        d = CACHE / "images" / n
        c, out = assemble([GEN / f"targets/{n}/{n}.cpu.asm", d / "vectors.asm"], image_path(n), d)
        res[f"{n}/vectors"] = {"exit_code": c, "out": out[-800:]}
        if n == "bwm":
            for w in ("cms03_decay", "cms03_oscillator"):
                c2, out2 = assemble([GEN / "targets/bwm/bwm.cpu.asm", GEN / f"targets/bwm/workloads/{w}.asm"],
                                    image_path(n, w), GEN / "targets/bwm/workloads")
                res[f"{n}/{w}"] = {"exit_code": c2, "out": out2[-800:]}
    return res


def step_asm() -> int:
    t0 = utc_now()
    res, rc = {}, 0
    for cmd in ([PY, "gen/isb/gen_asm.py"], [PY, "gen/isb/gen_image.py"], [PY, "gen/isb/gen_workloads.py"],
                [PY, "conformance/runners/isb/asm_roundtrip.py"]):
        c, out = sh(cmd)
        res[" ".join(cmd[1:])] = {"exit_code": c, "tail": out[-1500:]}
        print(out.rstrip())
        rc |= c
    imgs = build_images()
    res["images"] = imgs
    for k, v in imgs.items():
        print(f"assemble {k}: exit {v['exit_code']} {v['out'].strip()}")
        rc |= v["exit_code"]
    outs = [f"gen/isb/targets/{n}/{n}.cpu.asm" for n in NAMES] + \
           [str(image_path(n).relative_to(ROOT)) for n in NAMES] + \
           [str(CACHE.relative_to(ROOT) / "images" / n / "vectors.asm") for n in NAMES] + \
           [str(image_path("bwm", w).relative_to(ROOT)) for w in ("cms03_decay", "cms03_oscillator")]
    state = "done" if rc == 0 else "failed"
    rec = write_record("P7.3", "asm", "python3 -m repsynth isb asm", rc, started_utc=t0,
                       inputs=[f"spec/reps/machine/{n}.yaml" for n in NAMES], outputs=[o for o in outs if (ROOT / o).exists()],
                       tool_versions={"customasm": tool_versions()["customasm"]}, results=res, state=state)
    print(f"record {rec.relative_to(ROOT)}")
    return rc


# ---------------------------------------------------------------- P7.2
def derived_tree() -> list[str]:
    """Make .cache/isb/qemu from the pinned tree if it does not exist (never touching the pinned clone)."""
    log = []
    if not QTREE.exists():
        QTREE.mkdir(parents=True)
        subprocess.run(f"tar -C {PINNED} --exclude=./.git -cf - . | tar -C {QTREE} -xf -", shell=True, check=True)
        log.append(f"copied {PINNED} to {QTREE} without .git")
        tiera = ROOT / ".cache/qemu-derived/subprojects"
        for d in ("berkeley-softfloat-3", "berkeley-testfloat-3", "dtc", "keycodemapdb"):
            if (tiera / d).exists() and not (QTREE / "subprojects" / d).exists():
                shutil.copytree(tiera / d, QTREE / "subprojects" / d)
                log.append(f"copied subproject {d} from the Tier A derived tree")
    return log


def build_qemu(targets=("qemu-system-bwm", "qemu-system-twm"), log_name="isb_qemu_build") -> tuple[int, str]:
    if not (QBUILD / "build.ninja").exists():
        QBUILD.mkdir(parents=True, exist_ok=True)
        c, out = sh([str(QTREE / "configure")] + CONFIGURE, cwd=QBUILD, log=LOGS / f"{log_name}_configure.log")
        if c:
            return c, out
    return sh(["ninja", "-j3"] + list(targets), cwd=QBUILD, log=LOGS / f"{log_name}.log", timeout=7200)


def step_qemu() -> int:
    t0 = utc_now()
    res = {"tree": derived_tree()}
    c, out = sh([PY, "gen/isb/gen_qemu.py"])
    res["generate"] = {"exit_code": c, "tail": out[-800:]}
    c2, out2 = sh([PY, "gen/isb/patch.py", "--tree", str(QTREE), "gen/isb/targets/qemu_patches.json"])
    res["patch"] = {"exit_code": c2, "inserted": [l for l in out2.splitlines() if not l.startswith("copied")][:40]}
    print(out2.rstrip()[-2000:])
    rc = c | c2
    if rc == 0:
        c3, out3 = build_qemu()
        res["build"] = {"exit_code": c3, "tail": out3[-3000:], "log": ".cache/logs/isb_qemu_build.log"}
        print(out3[-1500:])
        rc |= c3
        for n in NAMES:
            b = qemu_bin(n)
            c4, out4 = sh([str(b), "-M", "help"]) if b.exists() else (1, "missing")
            res[f"{n}_machines"] = {"exit_code": c4, "out": out4[-400:]}
            rc |= c4
    state = "done" if rc == 0 else "failed"
    outs = ["gen/isb/targets/qemu_patches.json"] + [str(qemu_bin(n).relative_to(ROOT)) for n in NAMES if qemu_bin(n).exists()]
    rec = write_record("P7.2", "qemu", "python3 -m repsynth isb qemu", rc, started_utc=t0,
                       inputs=[f"spec/reps/machine/{n}.yaml" for n in NAMES] + ["gen/isb/gen_qemu.py", "gen/isb/patch.py"],
                       outputs=outs, tool_versions=tool_versions(), results=res, state=state,
                       notes=f"configure {' '.join(CONFIGURE)}; derived tree {QTREE.relative_to(ROOT)}")
    print(f"record {rec.relative_to(ROOT)}")
    return rc


# ---------------------------------------------------------------- P7.4
def run_vectors(n: str, timeout: int = 300) -> dict:
    sys.path.insert(0, str(ROOT / "conformance/runners/isb"))
    import run_image
    r = run_image.run(str(qemu_bin(n)), f"{n}-board", str(image_path(n)), timeout)
    r["expected"] = expected_cases(n)
    r["pass"] = run_image.judge(r, r["expected"])
    return r


def plugin_path() -> Path:
    return QBUILD / "tests/tcg/plugins/libinsn.so"


def count_workload(w: str) -> dict:
    sys.path.insert(0, str(ROOT / "conformance/runners/isb"))
    import re
    import run_image
    exp = dict(l.split(" ", 1) for l in (GEN / "targets/bwm/workloads/expected.txt").read_text().splitlines())
    out = {}
    for k in ("first", "rerun"):
        r = run_image.run(str(qemu_bin("bwm")), "bwm-board", str(image_path("bwm", w)), 120,
                          plugin=f"{plugin_path()},inline=on")
        mm = re.search(r"total insns: (\d+)", r["stderr"]) or re.search(r"insns: (\d+)", r["stderr"])
        out[k] = {"exit_code": r["exit_code"], "uart": r["uart"].strip(), "insns": int(mm.group(1)) if mm else None,
                  "plugin_stderr": r["stderr"][-300:]}
    out["output_matches"] = out["first"]["uart"] == exp[w]
    out["expected_output"] = exp[w]
    out["reproduced"] = out["first"]["insns"] == out["rerun"]["insns"] and out["first"]["insns"] is not None
    return out


def rv64_baseline() -> dict:
    p = ROOT / "reports/baseline/baseline.json"
    if not p.exists():
        return {}
    d = json.loads(p.read_text())
    return {r["workload"]: r for r in d.get("rows", []) if r.get("profile") == "RV64GC"}


def step_boot() -> int:
    t0 = utc_now()
    res, rc = {}, 0
    for n in NAMES:
        r = run_vectors(n)
        res[f"{n}_vectors"] = {k: v for k, v in r.items() if k != "uart"} | {"uart_tail": r["uart"][-600:]}
        print(f"{n}: exit {r['exit_code']} pass={r['pass']} ok={r['ok_lines']}")
        rc |= 0 if r["pass"] else 1
    base = rv64_baseline()
    counts = {}
    if plugin_path().exists():
        for w in ("cms03_decay", "cms03_oscillator"):
            c = count_workload(w)
            b = base.get(w, {})
            counts[w] = {"bwm": c, "rv64gc_insns": b.get("insns"), "rv64gc_output": b.get("output")}
            print(f"{w}: bwm insns {c['first']['insns']} (rerun {c['rerun']['insns']}), output {c['first']['uart']!r} "
                  f"matches={c['output_matches']}; RV64GC {b.get('insns')}")
    res["workload_counts"] = counts
    write_counts_report(counts)
    state = "done" if rc == 0 else "failed"
    rec = write_record("P7.4", "boot", "python3 -m repsynth isb boot", rc, started_utc=t0,
                       inputs=[str(image_path(n).relative_to(ROOT)) for n in NAMES] +
                       [str(image_path("bwm", w).relative_to(ROOT)) for w in ("cms03_decay", "cms03_oscillator")],
                       outputs=["reports/isb/workload_counts.md", "reports/isb/workload_counts.json"],
                       tool_versions=tool_versions(), results=res, state=state,
                       notes="vectors gate the packet; workload counts are reported, never gated (emulator counts, not hardware speed)")
    print(f"record {rec.relative_to(ROOT)}")
    return rc


def write_counts_report(counts: dict):
    (ROOT / "reports/isb").mkdir(parents=True, exist_ok=True)
    (ROOT / "reports/isb/workload_counts.json").write_text(json.dumps(
        {"_notice": "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC0-1.0",
         "counts": counts}, indent=2) + "\n")
    lines = ["<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->", "",
             "# Binary word machine workload counts beside RV64 (P7.4, NUM-06)", "",
             "Dynamic instruction counts in QEMU system mode on the generated bwm target, counted by the pinned "
             "tree's tests/tcg/plugins/insn.c (inline), each run twice. Reported, never gated; emulator counts are "
             "not hardware speed. The bwm programs compute the same Q2.29 states as the RV64 baseline programs but "
             "without the XOR checksum (the machine has no bitwise instructions), and include their own printing; "
             "the RV64 counts include the C runtime, the checksum and printing. They are the same computation, not the same program.", "",
             "| Workload | bwm insns | bwm rerun | bwm output | matches RV64 state | RV64GC insns | RV64GC output |",
             "|---|---:|---:|---|---|---:|---|"]
    for w, c in counts.items():
        b = c["bwm"]
        lines.append(f"| {w} | {b['first']['insns']} | {b['rerun']['insns']} | {b['first']['uart']} | "
                     f"{'yes' if b['output_matches'] else 'no'} | {c['rv64gc_insns']} | {c['rv64gc_output']} |")
    (ROOT / "reports/isb/workload_counts.md").write_text("\n".join(lines) + "\n")


def step_selftest() -> int:
    from repsynth.lanes import selftest_isb
    return selftest_isb.run_and_record()


def step_binutils() -> int:
    t0 = utc_now()
    rec = write_record("P7.5", "binutils", "python3 -m repsynth isb binutils", 0, started_utc=t0, state="not_built",
                       notes="SHOULD packet; not attempted in this sprint: the MUST packets P7.1 to P7.4 took the time. "
                             "customasm serves the test images (ISB-02).")
    write_status("P7.5", "not_built", [str(rec.relative_to(ROOT))],
                 "Generated binutils ports for bwm and twm were not attempted in this sprint; customasm assembles the test images.")
    return 0


STEPS = {"spec": step_spec, "asm": step_asm, "qemu": step_qemu, "boot": step_boot, "selftest": step_selftest,
         "binutils": step_binutils}


def run(args) -> int:
    rest = getattr(args, "rest", None) or ["all"]
    step = rest[0]
    if step == "all":
        rc = 0
        for s in ("spec", "asm", "qemu", "boot", "selftest", "binutils"):
            rc |= STEPS[s]()
        return rc
    if step not in STEPS:
        print(f"unknown step {step}; one of {', '.join(STEPS)} or all")
        return 2
    return STEPS[step]()
