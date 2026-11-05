# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tier A lane driver (milestone M4): allocation ledger, generators, patched QEMU, tests.

  python3 -m repsynth.lanes.tiera <step> [options]

Steps are listed by `--help`; each writes a run record (PRV-01).
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from repsynth.records import ROOT, sha256_file, utc_now, write_record

CACHE = ROOT / ".cache"
TMP = CACHE / "tmp" / "tiera"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sh(cmd, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def tail(text: str, n: int = 12) -> str:
    return "\n".join(text.strip().splitlines()[-n:])


# ---------------------------------------------------------------- P4.1
def _dir_hash(d: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    for p in sorted(d.rglob("*.yaml")):
        h.update(str(p.relative_to(d)).encode() + b"\0" + p.read_bytes())
    return h.hexdigest()


def step_ledger(args) -> int:
    """Allocate, then prove: regeneration unchanged; standard collision refused; vendor collision
    reported; a moved allocation refused."""
    import yaml
    started = utc_now()
    alloc = load_module(ROOT / "ledger" / "allocate.py", "allocate")
    TMP.mkdir(parents=True, exist_ok=True)
    results, ok = {}, True

    rc = alloc.main([])
    before = _dir_hash(alloc.LEDGER) + sha256_file(alloc.EXTFILE)
    prev = TMP / "ledger_previous"
    shutil.rmtree(prev, ignore_errors=True)
    shutil.copytree(alloc.LEDGER, prev)
    rc2 = alloc.main(["--previous", str(prev)])
    after = _dir_hash(alloc.LEDGER) + sha256_file(alloc.EXTFILE)
    results["allocate_exit"] = rc
    results["regenerate_exit"] = rc2
    results["regeneration_unchanged"] = before == after
    ok &= rc == 0 and rc2 == 0 and before == after
    rep = json.loads(alloc.REPORT.read_text())
    results["entries"] = rep["entries"]
    results["vendor_overlaps_reported"] = len(rep["reported_vendor"])
    results["vendor_summary"] = rep["vendor_summary"]
    results["vendor_collision_reported"] = len(rep["reported_vendor"]) > 0

    # planted: a standard collision (aye.bt.add placed on the OP/ADD encoding)
    planted = TMP / "ledger_planted_standard"
    shutil.rmtree(planted, ignore_errors=True)
    shutil.copytree(alloc.LEDGER, planted)
    f = planted / "balanced_ternary" / "add.yaml"
    e = yaml.safe_load(f.read_text())
    e["opcode"], e["funct3"], e["funct7"] = 0x33, 0, 0
    m, k = alloc.encode(0x33, 0, 0, e["rs2"] == "zero")
    e["match"], e["mask"] = f"0x{m:08x}", f"0x{k:08x}"
    f.write_text(yaml.safe_dump(e, sort_keys=False))
    rc3 = alloc.main(["--ledger", str(planted), "--report", str(TMP / "planted_standard.json"), "--check-only"])
    results["planted_standard_collision_exit"] = rc3
    results["planted_standard_collision_refusal"] = json.loads((TMP / "planted_standard.json").read_text())["refused"]
    ok &= rc3 == 2

    # planted: a moved allocation relative to the previous ledger
    moved_prev = TMP / "ledger_planted_previous"
    shutil.rmtree(moved_prev, ignore_errors=True)
    shutil.copytree(prev, moved_prev)
    f = moved_prev / "balanced_ternary" / "mul.yaml"
    e = yaml.safe_load(f.read_text())
    e["funct7"] = 63
    f.write_text(yaml.safe_dump(e, sort_keys=False))
    rc4 = alloc.main(["--previous", str(moved_prev), "--report", str(TMP / "planted_moved.json")])
    results["planted_moved_exit"] = rc4
    results["planted_moved_refusal"] = json.loads((TMP / "planted_moved.json").read_text())["moved"]
    ok &= rc4 == 3
    alloc.main(["--check-only"])      # leaves the real report in place
    rec = write_record("P4.1", "ledger", "python3 -m repsynth.lanes.tiera ledger", 0 if ok else 1,
                       started_utc=started, inputs=[ROOT / "ledger" / "allocate.py", *alloc.SPECS],
                       outputs=[alloc.LEDGER, alloc.EXTFILE, alloc.REPORT], tool_versions=alloc.db_versions(),
                       results=results, state="done" if ok else "failed",
                       notes="Vendor overlaps are reported, not refused (ISA-04).")
    print(json.dumps(results, indent=1)[:3000])
    print("record", rec)
    return 0 if ok else 1


# ---------------------------------------------------------------- P4.2 / P4.3
QEMU_BUILD = CACHE / "qemu-build"
QEMU_DERIVED = CACHE / "qemu-derived"
QEMU_PATCHED = CACHE / "qemu-patched"          # patched binaries copied out of the build
PLATFORM = ROOT / "lanes" / "toolchain" / "platform" / "linux"
LDSCRIPT = ROOT / "lanes" / "toolchain" / "baseline" / "linux-user.ld"
BIN = CACHE / "tiera" / "bin"
PROFILES = {"rv64": ("rv64gc", "lp64d", "qemu-riscv64", "rv64", 64), "rv32": ("rv32imac", "ilp32", "qemu-riscv32", "rv32", 32)}
CC = "riscv64-unknown-elf-gcc"


def tier_specs():
    from repsynth.lanes import graph_tiera as g
    return [(sid, g.extension(sid)) for sid in g.tier_a_specs()]


def build_test(sid: str, ext: str, prof: str, out: Path | None = None, insn_dir: Path | None = None,
               extra=()) -> Path:
    march, mabi, _, _, _ = PROFILES[prof]
    out = out or BIN / f"test_{ext}.{prof}"
    out.parent.mkdir(parents=True, exist_ok=True)
    insn_dir = insn_dir or ROOT / "gen" / "insn" / "out" / sid
    cmd = [CC, "-O2", f"-march={march}", f"-mabi={mabi}", "-ffreestanding", "-nostdlib", "-static",
           f"-T{LDSCRIPT}", f"-I{PLATFORM}", f"-I{insn_dir}", *extra, str(PLATFORM / "crt_args.c"),
           str(insn_dir / f"test_{ext}.c"), "-o", str(out), "-lgcc"]
    r = sh(cmd)
    if r.returncode:
        raise RuntimeError(f"build failed: {' '.join(cmd)}\n{r.stderr}")
    return out


def vec_files(sid: str, bits: int) -> list[Path]:
    from repsynth.lanes import graph_tiera as g
    spec = g.spec_of(sid)
    digits = {w["register_bits"]: w["digits"] for w in spec["domain"]["widths"]}[bits]
    ops = [o for _, o in g.candidate_ops(spec)]
    return [ROOT / "conformance" / "vectors" / sid / f"{op}.{digits}.vec" for op in ops]


def qemu_user(prof: str, props: dict, qemu_dir: Path = None) -> list[str]:
    qemu_dir = qemu_dir or QEMU_PATCHED
    _, _, q, cpu, _ = PROFILES[prof]
    cpu_arg = cpu + "".join(f",{k}={'on' if v else 'off'}" for k, v in props.items())
    return [str(qemu_dir / q), "-cpu", cpu_arg]


def run_vectors(sid, ext, prop, prof, binary, on=True, qemu_dir=None):
    files = vec_files(sid, PROFILES[prof][4])
    cmd = qemu_user(prof, {prop: on}, qemu_dir) + [str(binary)] + [str(f) for f in files]
    r = sh(cmd, timeout=900)
    return r, cmd


def step_user(args) -> int:
    """P4.3: vectors pass with the property on in qemu-riscv64 and qemu-riscv32; with it off every
    instruction raises SIGILL."""
    started = utc_now()
    results, ok = {}, True
    tv = {CC: sh([CC, "--version"]).stdout.splitlines()[0]}
    for prof in PROFILES:
        q = QEMU_PATCHED / PROFILES[prof][2]
        tv[q.name] = sh([str(q), "--version"]).stdout.splitlines()[0] + " (patched) sha256 " + sha256_file(q)
    outputs = []
    from repsynth.lanes import graph_tiera as g
    for sid, extd in tier_specs():
        ext, prop = extd["extension"], extd["cpu_property"]
        ops = [o for _, o in g.candidate_ops(g.spec_of(sid))]   # names
        for prof in PROFILES:
            b = build_test(sid, ext, prof)
            outputs.append(b)
            r, cmd = run_vectors(sid, ext, prop, prof, b, on=True)
            lines = [l for l in r.stdout.splitlines() if l.startswith(("PASS", "FAIL", "MISMATCH", "RESULT"))]
            key = f"{ext}/{prof}/on"
            results[key] = {"command": " ".join(cmd), "exit": r.returncode, "summary": lines[-12:]}
            print(key, "exit", r.returncode, lines[-1] if lines else r.stderr[-300:])
            ok &= r.returncode == 0 and "RESULT PASS" in r.stdout
            sig = {}
            for op in ops:
                c_on = qemu_user(prof, {prop: True}) + [str(b), "--one", op]
                c_off = qemu_user(prof, {prop: False}) + [str(b), "--one", op]
                ron, roff = sh(c_on, timeout=60), sh(c_off, timeout=60)
                sig[op] = {"on_exit": ron.returncode, "off_exit": roff.returncode,
                           "off_signal": "SIGILL" if roff.returncode in (-4, 132) else None}
                ok &= ron.returncode == 0 and roff.returncode in (-4, 132)
            results[f"{ext}/{prof}/off"] = {"command_pattern": " ".join(qemu_user(prof, {prop: False})) +
                                            f" {b} --one OP", "per_op": sig}
            print(f"{ext}/{prof}/off", {k: v["off_signal"] for k, v in sig.items()})
    rec = write_record("P4.3", "user", "python3 -m repsynth.lanes.tiera user", 0 if ok else 1, started_utc=started,
                       inputs=[ROOT / "gen" / "insn" / "out", ROOT / "conformance" / "vectors" / "balanced_ternary",
                               ROOT / "conformance" / "vectors" / "packed_decimal"],
                       outputs=outputs, tool_versions=tv, results=results, state="done" if ok else "failed",
                       notes="Exit -4 is death by SIGILL as Python reports it.")
    print("record", rec)
    return 0 if ok else 1


def step_qemu(args) -> int:
    """P4.2: generate, apply the exact-anchor patches to the derived tree, build QEMU with plugins,
    copy the patched binaries out; then show the patcher refusing a moved anchor."""
    from repsynth.lanes import graph_tiera as g
    started = utc_now()
    results, ok = {}, True
    written = g.generate_all(ROOT, kinds=("ledger", "qemu"))
    results["generated_written"] = written
    patchsets = [ROOT / "gen" / "qemu" / "out" / sid / "patches.json" for sid, _ in tier_specs()]
    pq = [sys.executable, str(ROOT / "gen" / "qemu" / "patch_qemu.py"), "--tree", str(QEMU_DERIVED)]
    r = sh(pq + [str(p) for p in patchsets])
    results["patch_exit"] = r.returncode
    results["patch_log_tail"] = tail(r.stdout, 6)
    ok &= r.returncode == 0
    r2 = sh(pq + [str(p) for p in patchsets])
    results["reapply_changes_nothing"] = r2.returncode == 0 and all(l.startswith("present") for l in r2.stdout.splitlines())
    ok &= results["reapply_changes_nothing"]
    log = CACHE / "logs" / "qemu_patched_make.log"
    t0 = utc_now()
    rb = subprocess.run(["/usr/bin/time", "-v", "make", "-j3"], cwd=QEMU_BUILD, capture_output=True, text=True,
                        env=dict(os.environ, CCACHE_DIR=str(CACHE / "ccache")))
    log.write_text(rb.stdout + rb.stderr)
    m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", rb.stderr)
    e = re.search(r"Elapsed \(wall clock\) time.*: (\S+)", rb.stderr)
    results["build"] = {"exit": rb.returncode, "started_utc": t0, "elapsed": e.group(1) if e else None,
                        "peak_rss_kb": int(m.group(1)) if m else None, "log": str(log.relative_to(ROOT)),
                        "parallelism": "-j3 (4 processors, 15 GB; contract limit)"}
    ok &= rb.returncode == 0
    if rb.returncode == 0:
        QEMU_PATCHED.mkdir(parents=True, exist_ok=True)
        for b in ("qemu-riscv64", "qemu-riscv32", "qemu-system-riscv64", "qemu-system-riscv32"):
            shutil.copy2(QEMU_BUILD / b, QEMU_PATCHED / b)
        shutil.copy2(QEMU_BUILD / "tests" / "tcg" / "plugins" / "libinsn.so", QEMU_PATCHED / "libinsn.so")
        (QEMU_PATCHED / "PIN").write_text((CACHE / "qemu-stock" / "PIN").read_text().strip() +
                                          "; patched with " + ", ".join(str(p.relative_to(ROOT)) for p in patchsets) + "\n")
        results["binaries"] = {b.name: sha256_file(b) for b in sorted(QEMU_PATCHED.iterdir()) if b.is_file()}
    # moved anchor: a scratch copy of the files the patches touch, from the pristine clone, with one anchor edited
    scratch = TMP / "anchor_moved_tree"
    shutil.rmtree(scratch, ignore_errors=True)
    src = CACHE / "qemu-src"
    for ps in patchsets:
        for a in json.loads(ps.read_text())["anchors"]:
            d = scratch / a["file"]
            d.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src / a["file"], d)
    tr = scratch / "target" / "riscv" / "translate.c"
    tr.write_text(tr.read_text().replace('#include "insn_trans/trans_xventanacondops.c.inc"\n',
                                         '#include "insn_trans/trans_xventana_condops.c.inc"\n'))
    before = {p: sha256_file(p) for p in scratch.rglob("*") if p.is_file()}
    r3 = sh(pq[:3] + [str(scratch)] + [str(p) for p in patchsets])
    after = {p: sha256_file(p) for p in scratch.rglob("*") if p.is_file()}
    results["moved_anchor"] = {"exit": r3.returncode, "stderr": r3.stderr.strip(), "tree_unchanged": before == after}
    print("moved anchor:", r3.returncode, r3.stderr.strip())
    ok &= r3.returncode == 4 and "trans_xventanacondops" in r3.stderr and before == after
    tv = {"qemu": (CACHE / "qemu-stock" / "PIN").read_text().strip(), "gcc": sh(["gcc", "--version"]).stdout.splitlines()[0],
          "ninja": sh(["ninja", "--version"]).stdout.strip()}
    rec = write_record("P4.2", "qemu", "python3 -m repsynth.lanes.tiera qemu", 0 if ok else 1, started_utc=started,
                       inputs=patchsets + [ROOT / "gen" / "qemu"], outputs=[QEMU_PATCHED] if QEMU_PATCHED.exists() else [],
                       tool_versions=tv, results=results, state="done" if ok else "failed",
                       notes="Built natively (ops/run.sh --native); the repsynth-qemu container is written but its "
                             "build was not run here unless a separate record says so.")
    print(json.dumps({k: v for k, v in results.items() if k != "binaries"}, indent=1)[:2500])
    print("record", rec)
    return 0 if ok else 1


# ---------------------------------------------------------------- P4.4
PROMOTION_THRESHOLD = 2.0   # working value: base/extension dynamic instruction ratio for promotion (ISA-03)
BENCH_K = 4                  # passes over the vector operands in the measured run


def bench_source(sid: str, ext: str, op: dict, mode: str, ref_prefix: str, digits: int) -> str:
    """mode 'ext': the instruction through its intrinsic; 'ref': the reference function on the base ISA."""
    name, unary = op["name"], op["arity"] == 1
    if mode == "ext":
        call = f"{ext}_{name}(A[i])" if unary else f"{ext}_{name}(A[i], B[i])"
        inc = f'#include "{ext}.h"\n'
    else:
        call = f"(unsigned long){ref_prefix}_{name}{digits}(A[i], B[i])"
        inc = f"#include <stdint.h>\nuint64_t {ref_prefix}_{name}{digits}(uint64_t a, uint64_t b);\n"
    return f"""/* © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
 * SPDX-License-Identifier: GPL-3.0-or-later
 * P4.4 measurement harness ({mode}): {sid}.{name} over the operands of a vector file, K passes. */
#include "repsynth_platform.h"
{inc}
#define MAXC 8192
static unsigned long A[MAXC], B[MAXC], R[MAXC];
static char buf[1 << 20];

static unsigned long long hex(const char **p)
{{
    unsigned long long x = 0;
    while (**p == ' ' || **p == '-' || **p == '>')
        (*p)++;
    for (;;) {{
        char c = **p;
        int d = (c >= '0' && c <= '9') ? c - '0' : (c >= 'a' && c <= 'f') ? c - 'a' + 10 : -1;
        if (d < 0)
            return x;
        x = (x << 4) | (unsigned long long)d;
        (*p)++;
    }}
}}

int main(int argc, char **argv)
{{
    int fd = plat_open(argv[1]), n = 0, k = argv[2][0] - '0', bad = 0;
    long len = 0, r;
    while ((r = plat_read(fd, buf + len, (int)(sizeof buf - 1 - len))) > 0)
        len += r;
    buf[len] = 0;
    for (const char *p = buf; *p && n < MAXC;) {{
        if (*p == '#') {{
            while (*p && *p != '\\n')
                p++;
        }} else if (*p != '\\n') {{
            A[n] = (unsigned long)hex(&p);
            B[n] = {"0" if unary else "(unsigned long)hex(&p)"};
            R[n] = (unsigned long)hex(&p);
            n++;
            while (*p && *p != '\\n')
                p++;
        }}
        if (*p)
            p++;
    }}
    unsigned long acc = 0;
    for (int pass = 0; pass < k; pass++)
        for (int i = 0; i < n; i++) {{
            unsigned long v = {call};
            acc ^= v;
            if (pass == 0 && v != R[i])
                bad++;
        }}
    plat_write(bad ? "BAD\\n" : "OK\\n", bad ? 4 : 3);
    return bad != 0;
}}
"""


def count_run(cmd: list[str], log: Path) -> tuple[int, int, str]:
    if log.exists():
        log.unlink()
    r = sh(cmd[:1] + ["-plugin", f"{QEMU_PATCHED / 'libinsn.so'},inline=on", "-d", "plugin", "-D", str(log)] + cmd[1:],
           timeout=900)
    m = re.search(r"total insns: (\d+)", log.read_text() if log.exists() else "")
    if not m:
        raise RuntimeError(f"no count: {cmd} {r.stderr}")
    return r.returncode, int(m.group(1)), r.stdout


def measure_op(sid, ext, prop, op, prof, mode, ref_prefix, wdir) -> dict:
    from repsynth.lanes import graph_tiera as g
    march, mabi, _, _, bits = PROFILES[prof]
    spec = g.spec_of(sid)
    digits = {w["register_bits"]: w["digits"] for w in spec["domain"]["widths"]}[bits]
    src = wdir / f"bench_{sid}_{op['name']}_{mode}_{prof}.c"
    src.write_text(bench_source(sid, ext, op, mode, ref_prefix, digits))
    exe = src.with_suffix(".elf")
    cmd = [CC, "-O2", f"-march={march}", f"-mabi={mabi}", "-ffreestanding", "-nostdlib", "-static", f"-T{LDSCRIPT}",
           f"-I{PLATFORM}", f"-I{ROOT / 'gen' / 'insn' / 'out' / sid}", str(PLATFORM / "crt_args.c"), str(src)]
    if mode == "ref":
        cmd.append(str(ROOT / "spec" / "ref" / sid / f"{sid}.c"))
    r = sh(cmd + ["-o", str(exe), "-lgcc"])
    if r.returncode:
        raise RuntimeError(r.stderr)
    vec = ROOT / "conformance" / "vectors" / sid / f"{op['name']}.{digits}.vec"
    base = qemu_user(prof, {prop: True})
    res = {}
    for k in (0, BENCH_K):
        e, n, out = count_run(base + [str(exe), str(vec), str(k)], wdir / f"{exe.stem}.k{k}.log")
        res[k] = (e, n, out.strip())
    e1, n1, o1 = count_run(base + [str(exe), str(vec), str(BENCH_K)], wdir / f"{exe.stem}.rerun.log")
    cases = sum(1 for l in vec.read_text().splitlines() if l and not l.startswith("#"))
    per = (res[BENCH_K][1] - res[0][1]) / (BENCH_K * cases)
    return {"exit": res[BENCH_K][0], "output": res[BENCH_K][2], "k0": res[0][1], "k": res[BENCH_K][1],
            "rerun_equal": n1 == res[BENCH_K][1], "cases": cases, "insns_per_op": round(per, 3),
            "elf_sha256": sha256_file(exe)}


def step_benefit(args) -> int:
    """P4.4: dynamic instruction counts, base ISA running the reference function against the extension,
    beside the binary baseline; promotion only with recorded benefit."""
    from repsynth.lanes import graph_tiera as g
    started = utc_now()
    wdir = CACHE / "tiera" / "benefit"
    wdir.mkdir(parents=True, exist_ok=True)
    prefixes = {"balanced_ternary": "bt", "packed_decimal": "pd", "binary_integer": "bin"}
    bin_spec = g.spec_of("binary_integer")
    bin_ops = {o["name"]: o for o in bin_spec["operations"]}
    rows, ok = [], True
    for sid, extd in tier_specs():
        ext, prop = extd["extension"], extd["cpu_property"]
        spec = g.spec_of(sid)
        for i, _ in g.candidate_ops(spec):
            op = spec["operations"][i]
            for prof in PROFILES:
                ref = measure_op(sid, ext, prop, op, prof, "ref", prefixes[sid], wdir)
                ins = measure_op(sid, ext, prop, op, prof, "ext", prefixes[sid], wdir)
                binr = (measure_op("binary_integer", ext, prop, bin_ops[op["name"]], prof, "ref", "bin", wdir)
                        if op["name"] in bin_ops else None)
                ratio = ref["insns_per_op"] / ins["insns_per_op"] if ins["insns_per_op"] > 0 else None
                good = all(x["exit"] == 0 and x["output"] == "OK" and x["rerun_equal"] for x in (ref, ins) + ((binr,) if binr else ()))
                ok &= good
                rows.append({"spec": sid, "op": op["name"], "profile": prof, "base_isa_ref": ref, "extension": ins,
                             "binary_baseline_ref": binr, "ratio_base_over_extension": round(ratio, 2) if ratio else None,
                             "verified": good})
                print(f"{sid:17s} {op['name']:9s} {prof} ref {ref['insns_per_op']:9.2f} ext {ins['insns_per_op']:6.2f} "
                      f"bin {binr['insns_per_op'] if binr else '-'} ratio {ratio:.1f} ok {good}")
    # promotion: every profile measured, and the ratio at or above the threshold on each
    promo = {}
    for r in rows:
        key = f"{r['spec']}.{r['op']}"
        p = promo.setdefault(key, {"ratios": {}, "measured": True})
        p["ratios"][r["profile"]] = r["ratio_base_over_extension"]
        p["measured"] &= r["verified"]
    for key, p in promo.items():
        p["promoted"] = p["measured"] and all(v is not None and v >= PROMOTION_THRESHOLD for v in p["ratios"].values())
    out = ROOT / "reports" / "promotion"
    out.mkdir(parents=True, exist_ok=True)
    doc = {"_notice": "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC0-1.0",
           "generator": "repsynth.lanes.tiera benefit 0.3.0",
           "metric": "dynamic instructions per operation, QEMU insn plugin, (count at K passes - count at 0 passes) / "
                     "(K x cases); emulator counts, never hardware speed",
           "threshold": f"promote when base/extension >= {PROMOTION_THRESHOLD} on RV64 and RV32 (working value, ISA-03); "
                        "hardware resources join the rule from M5",
           "K": BENCH_K, "rows": rows, "promotion": promo}
    (out / "promotion.json").write_text(json.dumps(doc, indent=2) + "\n")
    md = ["<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->", "",
          "# Tier A benefit and promotion (P4.4)", "",
          "Dynamic instructions per operation in QEMU user mode (patched v10.2.4, insn plugin). Emulator counts, "
          "not hardware speed. The binary column is the binary_integer reference function on the base ISA "
          "(the performance baseline, NUM-06); balanced ternary and packed decimal are shown beside it.", "",
          "Each figure is the dynamic instruction count of one loop iteration (operand loads, the operation, "
          "accumulate and compare), so the extension column includes that fixed loop body.", "",
          f"Promotion rule (working value): base/extension ratio >= {PROMOTION_THRESHOLD} on both profiles, every count "
          "verified against the vectors and reproduced on rerun.", "",
          "| Operation | Profile | Binary baseline (ref, base ISA) | Base ISA, reference function | Extension | Ratio |",
          "|---|---|---:|---:|---:|---:|"]
    for r in rows:
        b = r["binary_baseline_ref"]["insns_per_op"] if r["binary_baseline_ref"] else "n/a"
        md.append(f"| {r['spec']}.{r['op']} | {r['profile']} | {b} | {r['base_isa_ref']['insns_per_op']} | "
                  f"{r['extension']['insns_per_op']} | {r['ratio_base_over_extension']} |")
    md += ["", "| Candidate | Promoted |", "|---|---|"] + [f"| {k} | {'yes' if v['promoted'] else 'no'} |" for k, v in promo.items()]
    (out / "promotion.md").write_text("\n".join(md) + "\n")
    rec = write_record("P4.4", "benefit", "python3 -m repsynth.lanes.tiera benefit", 0 if ok else 1, started_utc=started,
                       inputs=[ROOT / "gen" / "insn" / "out", QEMU_PATCHED / "libinsn.so"],
                       outputs=[out / "promotion.json", out / "promotion.md"],
                       tool_versions={CC: sh([CC, "--version"]).stdout.splitlines()[0],
                                      "qemu": (QEMU_PATCHED / "PIN").read_text().strip()},
                       results={"promoted": sorted(k for k, v in promo.items() if v["promoted"]),
                                "kept": sorted(k for k, v in promo.items() if not v["promoted"])},
                       state="done" if ok else "failed")
    print("record", rec)
    return 0 if ok else 1


# ---------------------------------------------------------------- P4.12
def _vectors_pass(sid, ext, prop, prof, binary, qemu_dir=None) -> tuple[bool, str]:
    r, cmd = run_vectors(sid, ext, prop, prof, binary, on=True, qemu_dir=qemu_dir)
    lines = [l for l in r.stdout.splitlines() if l.startswith(("FAIL", "MISMATCH", "RESULT"))]
    passed = r.returncode == 0 and "RESULT PASS" in r.stdout
    return passed, f"exit {r.returncode}; " + " | ".join(lines[:4]) + (f" | {r.stderr.strip()[-200:]}" if r.stderr.strip() else "")


def _make_qemu() -> int:
    rb = subprocess.run(["make", "-j3"], cwd=QEMU_BUILD, capture_output=True, text=True,
                        env=dict(os.environ, CCACHE_DIR=str(CACHE / "ccache")))
    (CACHE / "logs" / "qemu_mutant_make.log").write_text(rb.stdout[-20000:] + rb.stderr[-20000:])
    return rb.returncode


def step_mutate(args) -> int:
    """P4.12: planted defects (a wrong funct3, swapped intrinsic operands, a wrong helper); each must be
    caught by the vector run in QEMU user mode, and the unmutated build must pass before and after."""
    started = utc_now()
    sid, ext, prop = "balanced_ternary", "xayebt", "x-xayebt"
    mdir = CACHE / "tiera" / "mutants"
    shutil.rmtree(mdir, ignore_errors=True)
    mdir.mkdir(parents=True)
    insn = ROOT / "gen" / "insn" / "out" / sid
    results, planted, caught = {}, 0, 0
    clean = build_test(sid, ext, "rv64", out=mdir / "clean.rv64")
    ok0, d0 = _vectors_pass(sid, ext, prop, "rv64", clean)
    results["clean_before"] = {"passed": ok0, "detail": d0}

    def mutant_insn(name, op, old, new):
        d = mdir / name / "insn"
        shutil.copytree(insn, d)
        f = d / "ops" / f"{op}.h"
        t = f.read_text()
        if t.count(old) != 1:
            raise RuntimeError(f"mutant {name}: {old!r} not found once in {f}")
        f.write_text(t.replace(old, new))
        return d

    # 1. wrong funct3 in the .insn macro and intrinsic of add (7 -> 6)
    d = mutant_insn("wrong_funct3", "add", '__asm__(".insn r 0x0b, 7, 1,', '__asm__(".insn r 0x0b, 6, 1,')
    # 2. swapped operands in the intrinsic of sub
    d2 = mutant_insn("swapped_operands", "sub", ': "r"(a), "r"(b));', ': "r"(b), "r"(a));')
    for name, dd in (("wrong_funct3", d), ("swapped_operands", d2)):
        for prof in PROFILES:
            b = build_test(sid, ext, prof, out=mdir / name / f"test.{prof}", insn_dir=dd)
            passed, detail = _vectors_pass(sid, ext, prop, prof, b)
            planted += 1
            caught += not passed
            results[f"{name}/{prof}"] = {"caught": not passed, "detail": detail}
            print(name, prof, "caught" if not passed else "NOT CAUGHT", detail[:160])
    # 3. wrong helper: the QEMU helper of add calls the reference function of sub
    hf = QEMU_DERIVED / "target" / "riscv" / "xaye" / sid / "ops" / "add.helper.c.inc"
    orig = hf.read_text()
    try:
        hf.write_text(orig.replace("bt_add32(", "bt_sub32(").replace("bt_add16(", "bt_sub16("))
        rc = _make_qemu()
        mq = mdir / "wrong_helper" / "qemu"
        mq.mkdir(parents=True)
        for q in ("qemu-riscv64", "qemu-riscv32"):
            shutil.copy2(QEMU_BUILD / q, mq / q)
        results["wrong_helper/build_exit"] = rc
        for prof in PROFILES:
            b = build_test(sid, ext, prof, out=mdir / "wrong_helper" / f"test.{prof}")
            passed, detail = _vectors_pass(sid, ext, prop, prof, b, qemu_dir=mq)
            planted += 1
            caught += (not passed) and rc == 0
            results[f"wrong_helper/{prof}"] = {"caught": not passed, "detail": detail}
            print("wrong_helper", prof, "caught" if not passed else "NOT CAUGHT", detail[:160])
    finally:
        hf.write_text(orig)
        rc2 = _make_qemu()
        results["restored_build_exit"] = rc2
    for prof in PROFILES:
        b = build_test(sid, ext, prof, out=mdir / f"clean_after.{prof}")
        okp, dp = _vectors_pass(sid, ext, prop, prof, b, qemu_dir=QEMU_BUILD)
        results[f"clean_after/{prof}"] = {"passed": okp, "detail": dp}
        ok0 &= okp
    ok = ok0 and planted == caught and planted == 6
    rep = ROOT / "reports" / "mutation" / "tiera.json"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps({"_notice": "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. "
                                          "SPDX-License-Identifier: CC0-1.0",
                               "lane": "Tier A (P4.12, T-21)", "planted": planted, "caught": caught,
                               "results": results}, indent=2) + "\n")
    rec = write_record("P4.12", "mutate", "python3 -m repsynth.lanes.tiera mutate", 0 if ok else 1, started_utc=started,
                       inputs=[insn, QEMU_PATCHED], outputs=[rep], results={"planted": planted, "caught": caught, **results},
                       state="done" if ok else "failed")
    print(f"planted {planted} caught {caught}; record {rec}")
    return 0 if ok else 1


# ---------------------------------------------------------------- P4.6 xv6-riscv
XV6_SRC = CACHE / "xv6-riscv"
XV6 = CACHE / "xv6-derived"


class Console:
    """Drives a QEMU serial console on stdin/stdout."""

    def __init__(self, cmd, cwd=None):
        import threading
        self.p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT)
        self.buf = b""
        self.lock = threading.Lock()
        self.t = threading.Thread(target=self._pump, daemon=True)
        self.t.start()

    def _pump(self):
        while True:
            b = self.p.stdout.read1(4096)
            if not b:
                return
            with self.lock:
                self.buf += b

    def text(self) -> str:
        with self.lock:
            return self.buf.decode("utf-8", "replace")

    def wait_for(self, pattern: str, timeout: float, start: int = 0) -> bool:
        import time
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            if re.search(pattern, self.text()[start:]):
                return True
            if self.p.poll() is not None:
                return bool(re.search(pattern, self.text()[start:]))
            time.sleep(0.2)
        return False

    def send(self, line: str):
        self.p.stdin.write(line.encode() + b"\n")
        self.p.stdin.flush()

    def close(self):
        if self.p.poll() is None:
            self.p.kill()
        self.p.wait()


def xv6_vec_names(sid):
    short = {"balanced_ternary": "bt", "packed_decimal": "pd"}[sid]
    return [(f, f"{short}{i}.v") for i, f in enumerate(vec_files(sid, 64))]


def step_xv6(args) -> int:
    """P4.6: derived xv6-riscv build with the test programs; their output inside xv6 equals the vectors
    with the property on; with it off the instruction traps (scause 2, illegal instruction)."""
    started = utc_now()
    results, ok = {}, True
    g_written = __import__("repsynth.lanes.graph_tiera", fromlist=["x"]).generate_all(ROOT, kinds=("ledger", "insn"))
    shutil.copytree(XV6_SRC, XV6, dirs_exist_ok=True, ignore=shutil.ignore_patterns(".git"))
    r = sh([sys.executable, str(ROOT / "gen" / "qemu" / "patch_qemu.py"), "--tree", str(XV6),
            str(ROOT / "lanes" / "os" / "xv6" / "patches.json")])
    results["patch"] = {"exit": r.returncode, "log": tail(r.stdout + r.stderr, 4)}
    ok &= r.returncode == 0
    mk = sh(["make", "-j3", "kernel/kernel", "fs.img"], cwd=XV6)
    results["make"] = {"exit": mk.returncode, "tail": tail(mk.stdout + mk.stderr, 6)}
    ok &= mk.returncode == 0
    vecs = []
    for sid, _ in tier_specs():
        for f, short in xv6_vec_names(sid):
            shutil.copy2(f, XV6 / short)
            vecs.append((sid, short))
    progs = sorted(str(p.relative_to(XV6)) for p in (XV6 / "user").glob("_*"))
    mf = sh(["mkfs/mkfs", "fs.img", "README", *progs, *[v for _, v in vecs]], cwd=XV6)
    results["mkfs"] = {"exit": mf.returncode, "tail": tail(mf.stdout + mf.stderr, 3)}
    ok &= mf.returncode == 0
    base = [str(QEMU_PATCHED / "qemu-system-riscv64"), "-machine", "virt", "-bios", "none", "-kernel", "kernel/kernel",
            "-m", "128M", "-smp", "1", "-nographic", "-global", "virtio-mmio.force-legacy=false",
            "-drive", "file=fs.img,if=none,format=raw,id=x0", "-device", "virtio-blk-device,drive=x0,bus=virtio-mmio-bus.0"]
    for on in (True, False):
        props = ",".join(f"{e['cpu_property']}={'on' if on else 'off'}" for _, e in tier_specs())
        con = Console(base + ["-cpu", f"rv64,{props}"], cwd=XV6)
        try:
            booted = con.wait_for(r"\$ $", 60)
            res = {"booted": booted, "cpu": f"rv64,{props}"}
            for sid, extd in tier_specs():
                ext = extd["extension"]
                names = [v for s2, v in vecs if s2 == sid]
                if on:
                    mark = len(con.text())
                    con.send(f"{ext} " + " ".join(names))
                    done = con.wait_for(r"RESULT (PASS|FAIL)", 900, mark)
                    out = con.text()[mark:]
                    lines = [l.strip() for l in out.splitlines() if l.strip().startswith(("PASS", "FAIL", "MISMATCH", "RESULT"))]
                    res[ext] = {"command": f"{ext} " + " ".join(names), "lines": lines,
                                "passed": done and "RESULT PASS" in out}
                    ok &= res[ext]["passed"]
                    print("xv6 on", ext, lines[-1] if lines else out[-300:])
                else:
                    traps = {}
                    from repsynth.lanes import graph_tiera as g
                    for _, opname in g.candidate_ops(g.spec_of(sid)):
                        mark = len(con.text())
                        con.send(f"{ext} --one {opname}")
                        con.wait_for(r"(usertrap|EXECUTED)[^\n]*\n(.|\n)*\$ $", 30, mark)
                        out = con.text()[mark:]
                        m = re.search(r"usertrap\(\): unexpected scause (0x[0-9a-f]+)", out)
                        traps[opname] = m.group(1) if m else ("EXECUTED" if "EXECUTED" in out else out[-120:])
                        ok &= bool(m) and int(m.group(1), 16) == 2
                    res[ext] = {"traps": traps}
                    print("xv6 off", ext, traps)
            ok &= booted
            results["on" if on else "off"] = res
        finally:
            con.close()
        (CACHE / "logs" / f"xv6_console_{'on' if on else 'off'}.log").write_text(con.text())
    rec = write_record("P4.6", "xv6", "python3 -m repsynth.lanes.tiera xv6", 0 if ok else 1, started_utc=started,
                       inputs=[ROOT / "lanes" / "os" / "xv6", ROOT / "gen" / "insn" / "out"],
                       outputs=[XV6 / "kernel" / "kernel", XV6 / "fs.img"],
                       tool_versions={"xv6-riscv": "https://github.com/mit-pdos/xv6-riscv commit "
                                                   + sh(["git", "-C", str(XV6_SRC), "rev-parse", "HEAD"]).stdout.strip()
                                                   + " (no hmnsq fork reachable: git ls-remote https://github.com/hmnsq/xv6-riscv failed)",
                                      "qemu": (QEMU_PATCHED / "PIN").read_text().strip(),
                                      CC: sh([CC, "--version"]).stdout.splitlines()[0]},
                       results=results, state="done" if ok else "failed",
                       notes="scause 0x2 is the illegal-instruction exception, taken by the xv6 kernel (ISA-06 system mode).")
    print("record", rec)
    return 0 if ok else 1


# ---------------------------------------------------------------- P4.5 binutils
BU_SRC = CACHE / "binutils-src" / "binutils-2.47"
BU = CACHE / "binutils-derived"
BU_BUILD = CACHE / "binutils-build"


def _gas_check(log_name: str) -> tuple[int, str, str]:
    r = sh(["make", "check", "RUNTESTFLAGS=riscv.exp"], cwd=BU_BUILD / "gas", timeout=1800)
    (CACHE / "logs" / log_name).write_text(r.stdout[-50000:] + r.stderr[-20000:])
    summ = (BU_BUILD / "gas" / "testsuite" / "gas.sum").read_text()
    return r.returncode, summ, "\n".join(l for l in summ.splitlines() if l.startswith(("# of", "FAIL", "ERROR", "UNRESOLVED")))


def step_binutils(args) -> int:
    """P4.5: opcode entries, extension registration and gas tests in the pinned binutils 2.47; gas
    assembles every mnemonic, objdump disassembles it, and the gas tests pass."""
    from repsynth.lanes import graph_tiera as g
    started = utc_now()
    results, ok = {}, True
    g.generate_all(ROOT, kinds=("ledger", "gas"))
    pfiles = [ROOT / "gen" / "binutils" / "out" / sid / "patches.json" for sid, _ in tier_specs()]
    r = sh([sys.executable, str(ROOT / "gen" / "qemu" / "patch_qemu.py"), "--tree", str(BU)] + [str(p) for p in pfiles])
    results["patch"] = {"exit": r.returncode, "tail": tail(r.stdout + r.stderr, 4)}
    ok &= r.returncode == 0
    mk = sh(["/usr/bin/time", "-v", "make", "-j3", "all-gas", "all-binutils"], cwd=BU_BUILD,
            env=dict(os.environ, CCACHE_DIR=str(CACHE / "ccache")))
    m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", mk.stderr)
    results["make"] = {"exit": mk.returncode, "peak_rss_kb": int(m.group(1)) if m else None}
    ok &= mk.returncode == 0
    gas, objdump = BU_BUILD / "gas" / "as-new", BU_BUILD / "binutils" / "objdump"
    # every mnemonic on RV32 and RV64: assemble and disassemble
    rt = {}
    for sid, extd in tier_specs():
        ext = extd["extension"]
        src = ROOT / "gen" / "binutils" / "out" / sid / "gas" / f"{ext}.s"
        for xl in ("rv32i", "rv64i"):
            obj = TMP / f"{ext}_{xl}.o"
            TMP.mkdir(parents=True, exist_ok=True)
            a = sh([str(gas), f"-march={xl}_{ext}1p0", str(src), "-o", str(obj)])
            d = sh([str(objdump), "-d", str(obj)])
            mnems = [g.load_entry(sid, o)["mnemonic"] for _, o in g.candidate_ops(g.spec_of(sid))]
            seen = {mn: len(re.findall(rf"\s{re.escape(mn)}\s", d.stdout)) for mn in mnems}
            good = a.returncode == 0 and d.returncode == 0 and all(v == 3 for v in seen.values())
            rt[f"{ext}/{xl}"] = {"as_exit": a.returncode, "objdump_exit": d.returncode, "disassembled": seen, "ok": good}
            ok &= good
            # without the extension in -march, gas must refuse the mnemonics
            a2 = sh([str(gas), f"-march={xl}", str(src), "-o", str(TMP / "noext.o")])
            rt[f"{ext}/{xl}/without_extension"] = {"as_exit": a2.returncode, "first_error": (a2.stderr.splitlines() or [""])[1:2]}
            ok &= a2.returncode != 0
    results["round_trip"] = rt
    rc, summ, brief = _gas_check("gas_check.log")
    passes = [l for l in summ.splitlines() if "xaye" in l]
    results["gas_check"] = {"exit": rc, "summary": brief, "tier_a_tests": passes}
    ok &= rc == 0 and all(l.startswith("PASS") for l in passes) and len(passes) == len(pfiles)
    # planted defect: a dump test whose expected word is wrong must fail
    d0 = BU / "gas" / "testsuite" / "gas" / "riscv" / f"x-{tier_specs()[0][1]['extension']}.d"
    mut = d0.with_name("x-mutant-wrong-word.d")
    t = d0.read_text()
    first = re.search(r"\]\+0:\[ \t\]\+([0-9a-f]{8})", t)
    w = first.group(1)
    mut.write_text(t.replace(f"]+0:[ \t]+{w}", f"]+0:[ \t]+{int(w, 16) ^ (1 << 12):08x}", 1))
    try:
        rcm, summ_m, brief_m = _gas_check("gas_check_mutant.log")
        mline = [l for l in summ_m.splitlines() if "x-mutant-wrong-word" in l]
        results["planted_wrong_word"] = {"exit": rcm, "line": mline}
        ok &= rcm != 0 and bool(mline) and mline[0].startswith("FAIL")
    finally:
        mut.unlink()
    tv = {"binutils": "2.47 release tarball binutils_2.47.orig.tar.xz (archive.ubuntu.com), sha256 "
                      "154ab23b60070e8f27013c22977f1129425d67d1e8acd6e13010e617811e4cff; bminor/binutils-gdb and "
                      "hmnsq/binutils-gdb not reachable from here",
          "dejagnu": sh(["runtest", "--version"]).stdout.splitlines()[0] if sh(["runtest", "--version"]).stdout else "",
          "gcc": sh(["gcc", "--version"]).stdout.splitlines()[0]}
    rec = write_record("P4.5", "binutils", "python3 -m repsynth.lanes.tiera binutils", 0 if ok else 1, started_utc=started,
                       inputs=pfiles, outputs=[gas, objdump], tool_versions=tv, results=results,
                       state="done" if ok else "failed",
                       notes="Built natively; the repsynth-gnu container definition is written but was not built here.")
    print(json.dumps(results, indent=1)[:3000])
    print("record", rec)
    return 0 if ok else 1


# ---------------------------------------------------------------- P4.7 Linux
LINUX_SRC = CACHE / "linux-src"
LINUX_BUILD = CACHE / "linux-build"
OPENSBI = QEMU_DERIVED / "pc-bios" / "opensbi-riscv64-generic-fw_dynamic.bin"


def step_linux(args) -> int:
    """P4.7: minimal kernel (tinyconfig plus lanes/os/linux/repsynth-tiny.config) and a static initramfs whose
    /init is the test binary; booted under the patched qemu-system-riscv64 with the OpenSBI bundled with QEMU."""
    started = utc_now()
    results, ok = {}, True
    image = LINUX_BUILD / "arch" / "riscv" / "boot" / "Image"
    ok &= image.exists()
    wd = CACHE / "tiera" / "linux"
    shutil.rmtree(wd, ignore_errors=True)
    wd.mkdir(parents=True)
    lst = ["dir /dev 0755 0 0", "nod /dev/console 0600 0 0 c 5 1", "dir /v 0755 0 0"]
    tests = {}
    for sid, extd in tier_specs():
        ext = extd["extension"]
        b = build_test(sid, ext, "rv64", out=wd / f"test_{ext}", extra=("-DREPSYNTH_LINUX_INIT",))
        lst.append(f"file /test_{ext} {b} 0755 0 0")
        names = []
        for f, short in xv6_vec_names(sid):
            lst.append(f"file /v/{short} {f} 0644 0 0")
            names.append(f"/v/{short}")
        tests[ext] = (extd["cpu_property"], names)
    (wd / "initramfs.list").write_text("\n".join(lst) + "\n")
    cpio = wd / "initramfs.cpio"
    r = sh(["sh", "-c", f"{LINUX_BUILD / 'usr' / 'gen_init_cpio'} {wd / 'initramfs.list'} > {cpio}"])
    results["initramfs"] = {"exit": r.returncode, "sha256": sha256_file(cpio) if cpio.exists() else None}
    ok &= r.returncode == 0
    props_all = [e["cpu_property"] for _, e in tier_specs()]
    for on in (True, False):
        props = ",".join(f"{p}={'on' if on else 'off'}" for p in props_all)
        for ext, (prop, names) in tests.items():
            argv = " ".join(names) if on else "--one add"
            cmd = [str(QEMU_PATCHED / "qemu-system-riscv64"), "-M", "virt", "-cpu", f"rv64,{props}", "-m", "256M",
                   "-smp", "1", "-nographic", "-no-reboot", "-bios", str(OPENSBI), "-kernel", str(image),
                   "-initrd", str(cpio), "-append", f"console=ttyS0 panic=-1 rdinit=/test_{ext} -- {argv}"]
            try:
                rr = subprocess.run(cmd, capture_output=True, text=True, timeout=900, stdin=subprocess.DEVNULL)
                out, code = rr.stdout + rr.stderr, rr.returncode
            except subprocess.TimeoutExpired as e:
                out, code = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), "timeout"
            key = f"{ext}/{'on' if on else 'off'}"
            (CACHE / "logs" / f"linux_console_{ext}_{'on' if on else 'off'}.log").write_text(out)
            sbi = re.search(r"OpenSBI (v[\d.]+)", out)
            kv = re.search(r"Linux version (\S+)", out)
            lines = [l.strip() for l in out.splitlines() if l.strip().startswith(("PASS", "FAIL", "MISMATCH", "RESULT", "INIT EXIT", "EXECUTED"))]
            if on:
                good = "RESULT PASS" in out and "INIT EXIT 0" in out
            else:
                good = "EXECUTED" not in out and bool(re.search(r"(SIGILL|Attempted to kill init! exitcode=0x00000004)", out))
            panic = re.search(r"Kernel panic[^\n]*", out)
            results[key] = {"command": " ".join(cmd), "qemu_exit": code, "opensbi": sbi.group(1) if sbi else None,
                            "kernel": kv.group(1) if kv else None, "lines": lines[-12:],
                            "panic": panic.group(0) if panic else None, "ok": good}
            print(key, code, good, lines[-1] if lines else (panic.group(0) if panic else out[-200:]))
            ok &= good
    tv = {"linux": "https://github.com/hmnsq/linux tag v6.12 commit "
                   + sh(["git", "-C", str(LINUX_SRC), "rev-parse", "HEAD"]).stdout.strip() + " (paras fork)",
          "firmware": f"OpenSBI bundled with the pinned QEMU v10.2.4 (pc-bios/opensbi-riscv64-generic-fw_dynamic.bin, "
                      f"sha256 {sha256_file(OPENSBI)}); no Parashakti firmware available here",
          "riscv64-linux-gnu-gcc": sh(["riscv64-linux-gnu-gcc", "--version"]).stdout.splitlines()[0],
          "qemu": (QEMU_PATCHED / "PIN").read_text().strip()}
    rec = write_record("P4.7", "linux", "python3 -m repsynth.lanes.tiera linux", 0 if ok else 1, started_utc=started,
                       inputs=[ROOT / "lanes" / "os" / "linux" / "repsynth-tiny.config", LINUX_BUILD / ".config"],
                       outputs=[image, cpio], tool_versions=tv, results=results, state="done" if ok else "failed",
                       notes="With the property off, /init dies of SIGILL and the kernel reports init killed with "
                             "exit code 4 (the trap path of ISA-06).")
    print("record", rec)
    return 0 if ok else 1


STEPS = {"linux": step_linux, "binutils": step_binutils, "xv6": step_xv6, "ledger": step_ledger, "user": step_user, "qemu": step_qemu, "benefit": step_benefit, "mutate": step_mutate}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="repsynth tiera")
    ap.add_argument("step", choices=sorted(STEPS))
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    return STEPS[a.step](a)


def run(ctx) -> int:
    argv = getattr(ctx, "argv", None)
    if argv is None and isinstance(ctx, (list, tuple)):
        argv = list(ctx)
    return main(argv or [])


if __name__ == "__main__":
    sys.exit(main())
