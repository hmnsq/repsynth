# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hardware lane (H8; packets P5.1 to P5.11). Drives existing tools only: Verilator, GHDL, cocotb, Yosys,
nextpnr-ice40, icestorm, the GNU RISC-V cross tools and QEMU.

  repsynth hdl gen       P5.1  generate the units through the graph nodes
  repsynth hdl lint      P5.1  verilator --lint-only -Wall and ghdl -a --std=08 on every unit
  repsynth hdl sim       P5.3  cocotb on Verilator (SystemVerilog) and GHDL (VHDL), every vector
  repsynth hdl mutate    P5.8  planted defects in copies; each must be caught
  repsynth hdl synth     P5.4  Yosys synth_ice40 and nextpnr-ice40 per unit
  repsynth hdl hls       P5.2  open HLS route attempt and the decision record
  repsynth hdl cosim     P5.5  CV-X-IF wrapper on a Verilated open core, against QEMU
  repsynth hdl baseline  P5.11 binary workloads on the Verilated core
  repsynth hdl handoff   P5.7  jugaad28 descriptors and the zamin boundary statement
  repsynth hdl all       every step above, in order

cocotb: the host carries cocotb 2.1.0, whose Verilator makefile requires Verilator 5.036 or later; the
host's Verilator is 5.020. The lane therefore runs cocotb 1.9.2 from a virtual environment under
.cache/hdl/cocotb19 (created by `repsynth hdl setup`), whose minimum is Verilator 4.106. The shared test
is written for both versions."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from repsynth.records import ROOT, sha256_file, utc_now, write_record, write_status
from repsynth.lanes import graph_hdl

CACHE = ROOT / ".cache" / "hdl"
VENV = CACHE / "cocotb19"
COCOTB_PIN = "cocotb==1.9.2"
RUNNER = ROOT / "conformance" / "runners" / "hdl"
UNITS = ROOT / graph_hdl.UNITS
REPORTS = ROOT / "reports" / "hardware"
JOBS = "3"


# ---------------------------------------------------------------- helpers

def sh(cmd, cwd=None, env=None, log: Path | None = None, timeout=None):
    """Run a command, keep its output, never hide a failure."""
    cmd = [str(c) for c in cmd]
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
    if log is not None:
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(f"$ {' '.join(cmd)}\n# exit {r.returncode}\n{r.stdout}\n--- stderr ---\n{r.stderr}")
    return r


def first_line(cmd) -> str:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
        out = (r.stdout or r.stderr).strip().splitlines()
        return out[0] if out else f"exit {r.returncode}"
    except FileNotFoundError:
        return "absent"


def tool_versions() -> dict:
    v = {
        "verilator": first_line(["verilator", "--version"]),
        "ghdl": first_line(["ghdl", "--version"]),
        "yosys": first_line(["yosys", "-V"]),
        "nextpnr-ice40": first_line(["nextpnr-ice40", "--version"]),
        "icepack": "fpga-icestorm " + _dpkg("fpga-icestorm"),
        "python": sys.version.split()[0],
        "cocotb(host)": first_line(["cocotb-config", "--version"]),
    }
    if (VENV / "bin" / "cocotb-config").exists():
        v["cocotb(lane)"] = first_line([VENV / "bin" / "cocotb-config", "--version"])
    return v


def _dpkg(pkg: str) -> str:
    r = subprocess.run(["dpkg-query", "-W", "-f=${Version}", pkg], capture_output=True, text=True)
    return r.stdout.strip() or "unknown"


def units(root: Path = ROOT) -> list[dict]:
    """Every generated unit with its source files and vectors, from the cocotb manifests."""
    out = []
    for sid, ops in graph_hdl.promoted(root)[0].items():
        for op in ops:
            man = json.loads((root / graph_hdl.MANIFESTS / sid / f"{op}.json").read_text())
            for u in man["units"]:
                out.append({**u, "spec": sid, "op": op,
                            "sv": root / graph_hdl.UNITS / sid / "sv" / f"{u['unit']}.sv",
                            "vhdl": root / graph_hdl.UNITS / sid / "vhdl" / f"{u['unit']}.vhd",
                            "vectors_path": root / u["vectors"]})
    return out


def rel(p: Path) -> str:
    p = Path(p)
    return str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)


# ---------------------------------------------------------------- setup and P5.1

def setup() -> int:
    """Create the cocotb 1.9.2 environment under .cache (git-ignored); nothing is installed on the host."""
    t0 = utc_now()
    if not (VENV / "bin" / "cocotb-config").exists():
        r = sh([sys.executable, "-m", "venv", "--system-site-packages", VENV])
        if r.returncode:
            print(r.stderr)
            return r.returncode
        r = sh([VENV / "bin" / "pip", "install", "-q", COCOTB_PIN])
        if r.returncode:
            print(r.stdout, r.stderr)
            return r.returncode
    v = first_line([VENV / "bin" / "cocotb-config", "--version"])
    mk = Path(sh([VENV / "bin" / "cocotb-config", "--makefiles"]).stdout.strip())
    vmin = re.search(r"VLT_MIN := (\S+)", (mk / "simulators" / "Makefile.verilator").read_text()).group(1)
    host_mk = Path(sh(["cocotb-config", "--makefiles"]).stdout.strip())
    host_min = re.search(r"VLT_MIN := (\S+)", (host_mk / "simulators" / "Makefile.verilator").read_text()).group(1)
    print(f"cocotb (lane) {v}, minimum Verilator {vmin}; cocotb (host) {first_line(['cocotb-config', '--version'])}, minimum Verilator {host_min}; "
          f"{first_line(['verilator', '--version'])}")
    write_record("P5.3", "setup", "repsynth hdl setup", 0, started_utc=t0, tool_versions=tool_versions(),
                 results={"cocotb_lane": v, "lane_verilator_minimum": vmin, "host_verilator_minimum": host_min},
                 state="done", notes="cocotb 1.9.2 in .cache/hdl/cocotb19 because the host cocotb 2.1.0 refuses Verilator 5.020")
    return 0


def gen() -> int:
    t0 = utc_now()
    res = graph_hdl.generate_all(ROOT)
    outs = sorted({o for r in res.values() for o in r["outputs"]})
    written = sorted({o for r in res.values() for o in r["written"]})
    print(f"hardware nodes: {len(res)}; outputs: {len(outs)}; written now: {len(written)}")
    write_record("P5.1", "gen", "repsynth hdl gen", 0, started_utc=t0,
                 inputs=[ROOT / graph_hdl.GEN_FILE, ROOT / graph_hdl.LANE_FILE] + [ROOT / s for s in ("spec/reps/numeric/balanced_ternary.yaml", "spec/reps/numeric/binary_integer.yaml")],
                 outputs=[ROOT / o for o in outs], tool_versions={"python": sys.version.split()[0]},
                 results={"nodes": {k: {"reads": v["reads"], "outputs": v["outputs"]} for k, v in res.items()},
                          "promoted_set": {k: list(v) for k, v in graph_hdl.promoted()[0].items()},
                          "promotion_state": graph_hdl.promoted()[1]},
                 state="done", notes="Generation ran; acceptance of P5.1 is the lint step.")
    return 0


def lint_files(sv_files, vhdl_files, logdir: Path) -> dict:
    res = {}
    work = CACHE / "ghdl-lint"
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    for f in sv_files:
        r = sh(["verilator", "--lint-only", "-Wall", f], log=logdir / f"verilator_{Path(f).stem}.log")
        res[rel(f)] = {"tool": "verilator --lint-only -Wall", "exit_code": r.returncode,
                       "messages": (r.stdout + r.stderr).strip().splitlines()[:20]}
    for f in vhdl_files:
        r = sh(["ghdl", "-a", "--std=08", f"--workdir={work}", f], log=logdir / f"ghdl_{Path(f).stem}.log")
        res[rel(f)] = {"tool": "ghdl -a --std=08", "exit_code": r.returncode,
                       "messages": (r.stdout + r.stderr).strip().splitlines()[:20]}
    return res


def lint() -> int:
    t0 = utc_now()
    us = units()
    res = lint_files([u["sv"] for u in us], [u["vhdl"] for u in us], CACHE / "logs" / "lint")
    bad = {k: v for k, v in res.items() if v["exit_code"] != 0 or v["messages"]}
    for k, v in res.items():
        print(f"  {'CLEAN' if k not in bad else 'FAIL '} {v['tool']:28s} {k}")
    # The gate is shown refusing a planted defect before it is trusted.
    planted = refusal_check()
    ok = not bad and planted["verilator_refused"] and planted["ghdl_refused"]
    rc = 0 if ok else 1
    rec = write_record("P5.1", "lint", "repsynth hdl lint", rc, started_utc=t0,
                       inputs=[u["sv"] for u in us] + [u["vhdl"] for u in us], tool_versions=tool_versions(),
                       results={"files": res, "failing": sorted(bad), "planted_defect_check": planted},
                       state="done" if ok else "failed",
                       notes="Every unit linted with verilator --lint-only -Wall and analysed with ghdl -a --std=08; "
                             "the gate was first shown refusing a planted defect in a copy.")
    write_status("P5.1", "done" if ok else "failed", [rel(rec)],
                 f"{len(us)} units in SystemVerilog and VHDL-2008 ({sum(1 for u in us if u['spec']=='balanced_ternary')} balanced ternary, "
                 f"{sum(1 for u in us if u['spec']=='binary_integer')} binary baseline); lint {'clean' if not bad else 'NOT clean'}. "
                 f"Promoted set {graph_hdl.promoted()[1]}.", blocked_by=[] if ok else ["lint"])
    print(f"lint: {len(res) - len(bad)} of {len(res)} clean; planted defect refused: {planted}")
    return rc


def refusal_check() -> dict:
    """Plant a width defect in a SystemVerilog copy and a syntax defect in a VHDL copy; both tools must refuse."""
    d = CACHE / "lint-planted"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    u = next(x for x in units() if x["unit"] == "bt_add16")
    sv = d / "bt_add16.sv"
    sv.write_text(u["sv"].read_text().replace("  logic invalid;", "  logic [3:0] spare;\n  assign spare = a;\n  logic invalid;", 1))
    vh = d / "bt_add16.vhd"
    vh.write_text(u["vhdl"].read_text().replace("  invalid <= ", "  invalid <= a; -- planted\n  invalid <= ", 1))
    rv = sh(["verilator", "--lint-only", "-Wall", sv])
    rg = sh(["ghdl", "-a", "--std=08", f"--workdir={d}", vh])
    return {"verilator_refused": rv.returncode != 0, "verilator_message": (rv.stderr.strip().splitlines() or [""])[0],
            "ghdl_refused": rg.returncode != 0, "ghdl_message": (rg.stderr.strip().splitlines() or [""])[0]}


# ---------------------------------------------------------------- P5.3 unit simulation

MAKEFILE = """# {notice}
# SPDX-License-Identifier: GPL-3.0-or-later
# Generated by repsynth.lanes.hdl for one cocotb run. Do not edit.
SIM = {sim}
TOPLEVEL_LANG = {lang}
{sources}
TOPLEVEL = {top}
MODULE = test_unit
COCOTB_TOPLEVEL = {top}
COCOTB_TEST_MODULES = test_unit
{extra}
include $(shell cocotb-config --makefiles)/Makefile.sim
"""


def cocotb_env(venv: Path | None = VENV) -> dict:
    env = dict(os.environ)
    if venv is not None:
        env["PATH"] = f"{venv / 'bin'}:{env['PATH']}"
        env["VIRTUAL_ENV"] = str(venv)
    env["PYTHONPATH"] = str(RUNNER) + (":" + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["MAKEFLAGS"] = f"-j{JOBS}"
    env.pop("MAKELEVEL", None)
    return env


def sim_unit(top: str, source: Path, sim: str, vectors: Path, arity: int, work: Path, venv: Path | None = VENV) -> dict:
    """One cocotb run of one unit on one simulator. Returns the test's summary and the exit code."""
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    if sim == "verilator":
        lang, sources, extra = "verilog", f"VERILOG_SOURCES = {source}", "EXTRA_ARGS += -Wno-fatal"
    elif sim == "ghdl":
        lang, sources, extra = "vhdl", f"VHDL_SOURCES = {source}", "GHDL_ARGS = --std=08"
    else:
        raise ValueError(sim)
    (work / "Makefile").write_text(MAKEFILE.format(notice="© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.",
                                                   sim=sim, lang=lang, sources=sources, top=top, extra=extra))
    env = cocotb_env(venv)
    result = work / "summary.json"
    env.update({"RS_VECTORS": str(vectors), "RS_ARITY": str(arity), "RS_RESULT": str(result)})
    r = sh(["make", "-f", work / "Makefile", f"-j{JOBS}"], cwd=work, env=env, log=work / "run.log", timeout=3600)
    summ = json.loads(result.read_text()) if result.exists() else None
    xml = work / "results.xml"
    xml_fail = None
    if xml.exists():
        t = xml.read_text()
        xml_fail = ("<failure" in t) or ("<error" in t)
    return {"exit_code": r.returncode, "summary": summ, "results_xml_failure": xml_fail, "log": rel(work / "run.log")}


def sim(only=None) -> int:
    t0 = utc_now()
    if not (VENV / "bin" / "cocotb-config").exists():
        setup()
    us = [u for u in units() if not only or u["unit"] in only]
    rows = {}
    for u in us:
        for s, src in (("verilator", u["sv"]), ("ghdl", u["vhdl"])):
            res = sim_unit(u["unit"], src, s, u["vectors_path"], u["arity"], CACHE / "sim" / s / u["unit"])
            sm = res["summary"] or {}
            passed = res["exit_code"] == 0 and sm.get("failures") == 0 and sm.get("cases", 0) > 0 and res["results_xml_failure"] is False
            rows[f"{u['unit']}:{s}"] = {"unit": u["unit"], "simulator": s, "passed": passed, "cases": sm.get("cases"),
                                        "failures": sm.get("failures"), "first_failures": sm.get("first_failures"),
                                        "exit_code": res["exit_code"], "simulator_version": sm.get("simulator_version"),
                                        "cocotb": sm.get("cocotb"), "vectors": u["vectors"],
                                        "vectors_sha256": sha256_file(u["vectors_path"]), "log": res["log"]}
            print(f"  {'PASS' if passed else 'FAIL'} {s:9s} {u['unit']:10s} cases={sm.get('cases')} failures={sm.get('failures')} exit={res['exit_code']}", flush=True)
    ok = all(r["passed"] for r in rows.values()) and len(rows) == 2 * len(us)
    rc = 0 if ok else 1
    total = sum(r["cases"] or 0 for r in rows.values())
    rec = write_record("P5.3", "sim", "repsynth hdl sim" + (" " + " ".join(only) if only else ""), rc, started_utc=t0,
                       inputs=[u["sv"] for u in us] + [u["vhdl"] for u in us] + [u["vectors_path"] for u in us] + [RUNNER / "test_unit.py"],
                       tool_versions=tool_versions(), results={"runs": rows, "total_cases": total},
                       state="done" if ok else "failed",
                       notes="cocotb test reads the shared vector files; Verilator runs the SystemVerilog units, GHDL the VHDL-2008 units.")
    if not only:
        REPORTS.mkdir(parents=True, exist_ok=True)
        _write_sim_report(rows)
        write_status("P5.3", "done" if ok else "failed", [rel(rec)],
                     f"{len(us)} units, every vector on Verilator and GHDL through cocotb: {total} vector cases, "
                     f"{'all passing' if ok else 'NOT all passing'}.", blocked_by=[])
    print(f"sim: {sum(r['passed'] for r in rows.values())} of {len(rows)} runs pass; {total} cases")
    return rc


def _write_sim_report(rows):
    L = ["<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->", "",
         "# Unit simulation (P5.3, T-22)", "",
         "Generated by repsynth.lanes.hdl from the run record. One cocotb test reads the shared vector files.", "",
         "| Unit | Simulator | Cases | Failures | Result |", "|---|---|---:|---:|---|"]
    for r in rows.values():
        L.append(f"| {r['unit']} | {r['simulator']} {r['simulator_version'] or ''} | {r['cases']} | {r['failures']} | {'pass' if r['passed'] else 'FAIL'} |")
    (REPORTS / "simulation.md").write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------- P5.8 mutation self-test

def mutate() -> int:
    from repsynth.lanes import selftest_hdl as st
    t0 = utc_now()
    res = st.run_mutants(ROOT)
    planted = len(res)
    caught = sum(1 for v in res.values() if v["caught"])
    ok = planted > 0 and caught == planted
    rc = 0 if ok else 1
    rec = write_record("P5.8", "mutate", "repsynth hdl mutate", rc, started_utc=t0,
                       inputs=[ROOT / "repsynth/lanes/selftest_hdl.py"] + [u[l] for u in units() for l in ("sv", "vhdl")],
                       tool_versions=tool_versions(),
                       results={"planted": planted, "caught": caught, "mutants": res,
                                "equivalent_not_planted": [{"id": a, "reason": b} for a, b in st.EQUIVALENT]},
                       state="done" if ok else "failed",
                       notes="Mutants are copies under .cache/hdl/mutants; each runs the same cocotb test and vectors as the clean unit.")
    REPORTS.mkdir(parents=True, exist_ok=True)
    L = ["<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->", "",
         "# Hardware mutation self-test (P5.8, T-24)", "",
         f"Planted {planted}, caught {caught}. Each mutant is a copy of a generated unit with one defect, run through the "
         "same cocotb test and vector file as the clean unit.", "",
         "| Mutant | Caught | Evidence |", "|---|---|---|"]
    for k, v in res.items():
        L.append(f"| {k} | {'yes' if v['caught'] else 'NO'} | {v['refusal']} |")
    L += ["", "Equivalent mutants, not planted because no test can tell them apart from the clean unit:", ""]
    L += [f"- {a}: {b}" for a, b in st.EQUIVALENT]
    (REPORTS / "mutation.md").write_text("\n".join(L) + "\n")
    write_status("P5.8", "done" if ok else "failed", [rel(rec)],
                 f"Hardware mutation self-test: planted {planted} (flipped bits and swapped ports, in SystemVerilog and VHDL), caught {caught}.")
    print(f"mutate: planted {planted}, caught {caught}")
    return rc


# ---------------------------------------------------------------- P5.4 synthesis reports

FPGA = {"family": "iCE40", "device": "up5k", "package": "sg48", "luts": 5280}
SEED = 1
FREQ_MHZ = 12   # the target given to nextpnr; the measured figure is its reported maximum frequency
# Pins of the UP5K SG48 package for the serial test wrapper (the 12 MHz clock pin of common boards is 35).
PINS = {"clk": 35, "sin": 2, "cap": 3, "sout": 4}

WRAP = """// {notice}
// SPDX-License-Identifier: CERN-OHL-S-2.0
// Generated by repsynth.lanes.hdl: serial wrapper so that a wide unit fits a small package. Operands
// shift in on sin, the result is captured when cap is high and shifts out on sout. The timed path is
// operand registers -> unit -> result register.
module rs_wrap (input logic clk, input logic sin, input logic cap, output logic sout);
  logic [{w}:0] a, b, r, q;
  always_ff @(posedge clk) begin
    a <= {{a[{w1}:0], sin}};
    b <= {{b[{w1}:0], a[{w}]}};
    if (cap) q <= r; else q <= {{q[{w1}:0], 1'b0}};
  end
  assign sout = q[{w}];
  {unit} u ({ports});
endmodule
"""


def _yosys_stat(log_text: str) -> dict:
    """Cell counts from the last 'Printing statistics' block of a Yosys log."""
    blk = log_text.rsplit("Printing statistics", 1)[-1]
    cells = {m.group(1): int(m.group(2)) for m in re.finditer(r"^\s+(SB_\w+)\s+(\d+)\s*$", blk, re.M)}
    tot = re.search(r"Number of cells:\s+(\d+)", blk)
    return {"cells": int(tot.group(1)) if tot else None, "by_type": cells, "luts": cells.get("SB_LUT4", 0),
            "carries": cells.get("SB_CARRY", 0), "dffs": sum(v for k, v in cells.items() if k.startswith("SB_DFF")),
            "dsps": cells.get("SB_MAC16", 0)}


def synth_unit(u: dict, work: Path) -> dict:
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    w = u["register_bits"]
    sv = u["sv"]
    # 1. the bare unit: resources
    r1 = sh(["yosys", "-q", "-l", work / "unit.yosys.log", "-p", f"read_verilog -sv {sv}; synth_ice40 -top {u['unit']}; stat"],
            log=work / "unit.cmd.log", timeout=7200)
    unit_stat = _yosys_stat((work / "unit.yosys.log").read_text()) if (work / "unit.yosys.log").exists() else {}
    # 2. the wrapped unit: place and route, timing
    ports = ".a(a), .b(b), .r(r)" if u["arity"] == 2 else ".a(a), .r(r)"
    (work / "rs_wrap.sv").write_text(WRAP.format(notice="© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.",
                                                 w=w - 1, w1=w - 2, unit=u["unit"], ports=ports))
    (work / "rs_wrap.pcf").write_text("".join(f"set_io {k} {v}\n" for k, v in PINS.items()))
    r2 = sh(["yosys", "-q", "-l", work / "wrap.yosys.log", "-p",
             f"read_verilog -sv {sv} {work / 'rs_wrap.sv'}; synth_ice40 -top rs_wrap -json {work / 'rs_wrap.json'}; stat"],
            log=work / "wrap.cmd.log", timeout=7200)
    r3 = sh(["nextpnr-ice40", f"--{FPGA['device']}", "--package", FPGA["package"], "--json", work / "rs_wrap.json",
             "--pcf", work / "rs_wrap.pcf", "--asc", work / "rs_wrap.asc", "--freq", str(FREQ_MHZ), "--seed", str(SEED),
             "--report", work / "report.json", "--timing-allow-fail"], log=work / "nextpnr.log", timeout=7200)
    rep = json.loads((work / "report.json").read_text()) if (work / "report.json").exists() else {}
    fmax = None
    for clk, v in (rep.get("fmax") or {}).items():
        fmax = round(v.get("achieved"), 2)
    util = {k: v for k, v in (rep.get("utilization") or {}).items() if v.get("used")}
    r4 = sh(["icepack", work / "rs_wrap.asc", work / "rs_wrap.bin"], log=work / "icepack.log") if r3.returncode == 0 else None
    pnr_text = (work / "nextpnr.log").read_text()
    m = re.findall(r"Max frequency for clock\s+'([^']+)':\s+([\d.]+) MHz", pnr_text)
    return {"unit": u["unit"], "spec": u["spec"], "op": u["op"], "register_bits": w,
            "yosys_unit_exit": r1.returncode, "unit_resources": unit_stat,
            "yosys_wrap_exit": r2.returncode, "nextpnr_exit": r3.returncode,
            "icepack_exit": None if r4 is None else r4.returncode,
            "wrapped_utilisation": util, "fmax_mhz": fmax, "fmax_log_lines": m[-1:] if m else [],
            "bitstream_sha256": sha256_file(work / "rs_wrap.bin") if (work / "rs_wrap.bin").exists() else None,
            "error": None if r3.returncode == 0 else (r3.stderr or r3.stdout).strip().splitlines()[-3:]}


def synth(only=None, packet="P5.4") -> int:
    t0 = utc_now()
    us = [u for u in units() if not only or u["unit"] in only]
    rows = {}
    for u in us:
        a = synth_unit(u, CACHE / "synth" / u["unit"] / "run1")
        b = synth_unit(u, CACHE / "synth" / u["unit"] / "run2")
        keys = ("unit_resources", "wrapped_utilisation", "fmax_mhz", "bitstream_sha256")
        a["reproduced"] = all(a[k] == b[k] for k in keys)
        rows[u["unit"]] = a
        print(f"  {u['unit']:10s} LUT4={a['unit_resources'].get('luts')} carry={a['unit_resources'].get('carries')} "
              f"cells={a['unit_resources'].get('cells')} | wrapped LCs={a['wrapped_utilisation'].get('ICESTORM_LC', {}).get('used')} "
              f"Fmax={a['fmax_mhz']} MHz nextpnr={a['nextpnr_exit']} reproduced={a['reproduced']}", flush=True)
    ok = all(r["yosys_unit_exit"] == 0 for r in rows.values())
    placed = {k: r for k, r in rows.items() if r["nextpnr_exit"] == 0 and r["fmax_mhz"]}
    rc = 0 if ok else 1
    vers = tool_versions()
    rec = write_record(packet, "synth", "repsynth hdl synth" + (" " + " ".join(only) if only else ""), rc, started_utc=t0,
                       inputs=[u["sv"] for u in us], tool_versions=vers,
                       results={"fpga": FPGA, "seed": SEED, "target_mhz": FREQ_MHZ, "pins": PINS, "units": rows},
                       state="done" if ok else "failed",
                       notes="Measurements from Yosys synth_ice40 and nextpnr-ice40, never claims about silicon. Unit resources are "
                             "the bare unit; utilisation and Fmax are of the unit inside a serial register wrapper. VHDL units are "
                             "not synthesised: the Yosys GHDL plugin is absent here.")
    if not only:
        _write_synth_report(rows, vers)
        write_status("P5.4", "done" if ok else "failed", [rel(rec)],
                     f"Yosys and nextpnr-ice40 on iCE40 {FPGA['device'].upper()} {FPGA['package']} for {len(rows)} SystemVerilog units; "
                     f"{len(placed)} placed and routed with Fmax recorded; all figures are measurements.")
    return rc


def _write_synth_report(rows, vers):
    REPORTS.mkdir(parents=True, exist_ok=True)
    L = ["<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->", "",
         "# Synthesis figures (P5.4, HDL-04; binary rows feed P5.11 and D14)", "",
         f"Target: iCE40 {FPGA['device'].upper()}, package {FPGA['package']} ({FPGA['luts']} logic cells). Measurements from the open "
         "flow, never claims about silicon. Unit columns are the bare unit after `synth_ice40`; logic cells and maximum "
         "frequency are of the unit placed and routed inside a serial register wrapper (operand registers, unit, result "
         f"register), nextpnr seed {SEED}. Each unit was run twice; 'Reproduced' compares every figure and the bitstream hash.", "",
         "| Unit | Bits | LUT4 | Carry | DSP | Cells | Wrapped logic cells | Fmax (MHz) | Reproduced | Note |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    for r in rows.values():
        ur, lc = r["unit_resources"], r["wrapped_utilisation"].get("ICESTORM_LC", {})
        note = "" if r["nextpnr_exit"] == 0 else "place and route failed: " + " ".join(r["error"] or [])[:160]
        L.append(f"| {r['unit']} | {r['register_bits']} | {ur.get('luts')} | {ur.get('carries')} | {ur.get('dsps')} | {ur.get('cells')} | "
                 f"{lc.get('used', '')} | {r['fmax_mhz'] if r['fmax_mhz'] else ''} | {'yes' if r['reproduced'] else 'no'} | {note} |")
    L += ["", "Tool versions:", ""] + [f"- {k}: {v}" for k, v in vers.items()]
    (REPORTS / "synthesis.md").write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------- P5.7 physical hand-off

JUGAAD = {"name": "jugaad28", "url": "https://github.com/zistgah/jugaad28.git", "commit": "105edbfa5dcad04eaf1bafa89f6130591e0f775d"}
ZAMIN = {"name": "zamin", "url": "https://github.com/zistgah/zamin.git", "commit": "b0ac0ebd27addc6214dc8afe31e6516be5ed22a9"}
HANDOFF_J = ROOT / "handoff" / "jugaad28"
HANDOFF_Z = ROOT / "handoff" / "zamin"
# Identifiers are proposed in a range the catalogue does not use (it holds J28-001 to J28-014); the author assigns final ones.
DESCRIPTORS = {"J28-101": "balanced_ternary", "J28-102": "binary_integer"}


def _status_state(packet: str) -> str:
    p = ROOT / "reports" / "status" / f"{packet}.json"
    return json.loads(p.read_text())["state"] if p.exists() else "absent"


def descriptor(did: str, sid: str) -> dict:
    us = [u for u in units() if u["spec"] == sid]
    verified = _status_state("P5.3") == "done"
    ops = sorted({u["op"] for u in us})
    widths = sorted({u["digits"] for u in us})
    sim_rec = sorted((ROOT / "records").glob("*_P5.3_sim.json"))
    syn_rec = sorted((ROOT / "records").glob("*_P5.4_synth.json"))
    ev = {"spec": f"hmnsq/repsynth spec/reps/numeric/{sid}.yaml",
          "rtl": f"hmnsq/repsynth gen/hdl/units/{sid}/sv and gen/hdl/units/{sid}/vhdl (generated by repsynth.gen.hdl 0.3.0)"}
    if verified:
        ev["testbench"] = ("hmnsq/repsynth conformance/runners/hdl/test_unit.py on Verilator and GHDL over the shared vectors; "
                           f"record {rel(sim_rec[-1]) if sim_rec else 'absent'}")
    if sid == "balanced_ternary":
        d = {"name": "Balanced ternary arithmetic units on binary logic",
             "klass": "digital logic",
             "substrate": "28 nm bulk CMOS (binary logic; each trit held as two bits)",
             "purpose": ("Combinational units for the promoted balanced ternary operations of repsynth (" + ", ".join(ops) +
                         f") at {' and '.join(str(w) for w in widths)} trits, each trit emulated on binary logic as a two-bit code "
                         "taken from the specification's active encoding. They attach to a RISC-V core as a CV-X-IF coprocessor."),
             "interfaces": ["Combinational ports a, b, r of 2n bits per unit (n trits, two bits per trit)",
                            "OpenHW CV-X-IF coprocessor wrapper (gen/hdl/xif/rs_xif_xayebt.sv) for 32-bit cores such as CV32E40X"],
             "edges": ["zistgah/zamin"],
             "open_questions": ["Native ternary realisations of these operations belong to zistgah/zamin; the interface at that boundary is the trit code table, which zamin has not yet declared back (OWED)",
                                "Whether the 32-trit multiplier should be sequential on small parts: it does not fit an iCE40 UP5K combinationally"]}
    else:
        d = {"name": "Binary baseline adder and multiplier units",
             "klass": "digital logic",
             "substrate": "28 nm bulk CMOS",
             "purpose": ("Two's complement add and multiply units at " + " and ".join(str(w) for w in widths) +
                         " bits, generated beside the representation units so every hardware figure has its binary baseline (NUM-06)."),
             "interfaces": ["Combinational ports a, b, r of w bits per unit"],
             "edges": [],
             "open_questions": ["Which multiplier architecture the baseline should fix for 28 nm comparisons (array, Booth or DSP-mapped)"]}
    d.update({"id": did, "tapeout_path": "28nm-bulk-cmos", "rung": "VERIFIED" if verified else "RTL",
              "enablement": ["Synthesisable SystemVerilog and VHDL-2008 units regenerated from a specification with one command",
                             "A cocotb testbench that reads plain-text conformance vectors and runs on Verilator and GHDL",
                             "Open FPGA synthesis and timing figures (Yosys, nextpnr-ice40) recorded with tool versions as measurements"],
              "metrics": {k: "not established" for k in ("area_mm2", "power_mw", "fmax_mhz", "yield_pct", "cost_inr")},
              "evidence": ev, "copyright": "© 1993–2026 Abhishek Choudhary. All rights reserved.", "affiliation": "AyeAI",
              "licence": "CERN-OHL-S-2.0"})
    if syn_rec:
        d["open_questions"].append(f"FPGA figures are not 28 nm metrics and are kept out of metrics; see {rel(syn_rec[-1])}")
    order = ["id", "name", "klass", "substrate", "tapeout_path", "rung", "purpose", "interfaces", "enablement", "metrics",
             "evidence", "edges", "open_questions", "copyright", "affiliation", "licence"]
    return {k: d[k] for k in order}


def jvalidate(path: Path, clone: Path) -> dict:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    r = sh([sys.executable, clone / "ops" / "jugaad28.py", "validate", path], env=env)
    return {"command": f"python3 ops/jugaad28.py validate {rel(path)}", "exit_code": r.returncode,
            "output": (r.stdout + r.stderr).strip().splitlines()}


def handoff() -> int:
    t0 = utc_now()
    jc = ensure_clone(JUGAAD["name"], JUGAAD["url"], JUGAAD["commit"])
    zc = ensure_clone(ZAMIN["name"], ZAMIN["url"], ZAMIN["commit"])
    jdir, zdir = CACHE / JUGAAD["name"], CACHE / ZAMIN["name"]
    HANDOFF_J.mkdir(parents=True, exist_ok=True)
    HANDOFF_Z.mkdir(parents=True, exist_ok=True)
    outs, val = [], {}
    for did, sid in DESCRIPTORS.items():
        p = HANDOFF_J / f"{did.lower().replace('-', '_')}.json"
        p.write_text(json.dumps(descriptor(did, sid), indent=2, ensure_ascii=False) + "\n")
        (p.with_suffix(".json.license")).write_text("© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.\n"
                                                    "SPDX-License-Identifier: CERN-OHL-S-2.0\n"
                                                    "jugaad28 descriptor (its own schema has no notice key); generated by repsynth.lanes.hdl.\n")
        outs += [p, p.with_suffix(".json.license")]
        val[did] = jvalidate(p, jdir)
    # The validator is shown refusing planted defects in copies of the first descriptor.
    planted = {}
    base = json.loads((HANDOFF_J / "j28_101.json").read_text())
    pdir = CACHE / "handoff-planted"
    shutil.rmtree(pdir, ignore_errors=True)
    pdir.mkdir(parents=True)
    defects = {
        "J3 rung VERIFIED without testbench evidence": lambda d: (d.update(rung="VERIFIED"), d["evidence"].pop("testbench", None)),
        "J4 ternary substrate on the 28 nm path": lambda d: d.update(substrate="ternary MTCMOS on 28 nm"),
        "J5 zamin vocabulary without the edge": lambda d: d.update(edges=[]),
        "J1 a metric without evidence": lambda d: d["metrics"].update(fmax_mhz=5.0),
    }
    for name, f in defects.items():
        d = json.loads(json.dumps(base))
        f(d)
        q = pdir / (re.sub(r"\W+", "_", name) + ".json")
        q.write_text(json.dumps(d, indent=2))
        v = jvalidate(q, jdir)
        planted[name] = {"refused": v["exit_code"] != 0, "output": v["output"]}
    # The catalogue check with the descriptors added, in a derived copy (the clone is never edited).
    derived = CACHE / "jugaad28-derived"
    shutil.rmtree(derived, ignore_errors=True)
    shutil.copytree(jdir, derived, ignore=shutil.ignore_patterns(".git"))
    for did in DESCRIPTORS:
        shutil.copy2(HANDOFF_J / f"{did.lower().replace('-', '_')}.json", derived / "catalogue")
    r = sh([sys.executable, derived / "ops" / "jugaad28.py", "check"], env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    check = {"command": "python3 ops/jugaad28.py check (derived copy with the descriptors added)", "exit_code": r.returncode,
             "output": (r.stdout + r.stderr).strip().splitlines()[-8:]}
    jc_after, zc_after = git_ids(jdir), git_ids(zdir)
    zb = HANDOFF_Z / "BOUNDARY.md"
    zb.write_text(_zamin_boundary(zc, jc))
    outs.append(zb)
    ok = (all(v["exit_code"] == 0 for v in val.values()) and all(x["refused"] for x in planted.values())
          and check["exit_code"] == 0 and jc_after == {k: jc[k] for k in jc_after} and zc_after == {k: zc[k] for k in zc_after})
    rungs = {did: json.loads((HANDOFF_J / f"{did.lower().replace('-', '_')}.json").read_text())["rung"] for did in DESCRIPTORS}
    rec = write_record("P5.7", "handoff", "repsynth hdl handoff", 0 if ok else 1, started_utc=t0, outputs=outs,
                       tool_versions={"python": sys.version.split()[0], "jugaad28": f"{jc['commit']} tree {jc['tree']}",
                                      "zamin": f"{zc['commit']} tree {zc['tree']}"},
                       results={"rungs": rungs, "validate": val, "planted_defects": planted, "catalogue_check": check,
                                "clones_before": {"jugaad28": jc, "zamin": zc}, "clones_after": {"jugaad28": jc_after, "zamin": zc_after}},
                       state="done" if ok else "failed",
                       notes="Descriptors validated by jugaad28's own ops/jugaad28.py from a read-only clone; its catalogue check run "
                             "in a derived copy. Native ternary circuits are routed to zamin by the boundary statement.")
    write_status("P5.7", "done" if ok else "failed", [rel(rec)],
                 f"jugaad28 descriptors {', '.join(f'{k} at {v}' for k, v in rungs.items())} pass jugaad28's own validation; "
                 "the zamin boundary statement routes native ternary circuits to zamin.")
    print(f"handoff: {rungs}; validate {[v['exit_code'] for v in val.values()]}; planted refused "
          f"{sum(x['refused'] for x in planted.values())}/{len(planted)}; check {check['exit_code']}")
    return 0 if ok else 1


def _zamin_boundary(zc, jc) -> str:
    return f"""<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->

# Boundary statement: repsynth hardware units, jugaad28 and zamin (P5.7, HDL-07)

Generated by repsynth.lanes.hdl. Read from zistgah/zamin {zc['commit']} (tree {zc['tree']}) and
zistgah/jugaad28 {jc['commit']} (tree {jc['tree']}), both read-only clones.

## What repsynth's hardware lane produces

Balanced ternary units that **emulate** ternary on binary logic: every trit is a two-bit code taken from the
specification's active encoding (`pair` now, `planes` under change D2(d)), and every gate is an ordinary binary
CMOS gate. These follow the binary flow: jugaad28 descriptors on its `28nm-bulk-cmos` path
(handoff/jugaad28/j28_101.json, j28_102.json), validated by jugaad28's own `ops/jugaad28.py`.

## What goes to zamin

Native ternary circuits, in which a trit is one physical node with three states, belong to zamin and are not
produced here. zamin's CONTRACT.md and CONTEXT.md define its substrate: balanced ternary {{-1, 0, +1}} with the
0 state a physical high-impedance ground, never a resistive mid-rail; its cells are SPICE subcircuits in
spice/cells/ (TCG_X1 context gate, TEL_X1, TMC_NODE, TAR_NODE, TTR_X1, a memristor model) over placeholder
30 nm MTCMOS models in spice/models/mtcmos_30nm.sp. jugaad28's invariant J4 forbids such a substrate on its
28 nm bulk path, and J5 requires an edge to zistgah/zamin wherever the word ternary appears; descriptor J28-101
declares that edge.

## The interface at the boundary

The trit code table of the specification: the value of each two-bit code (00 is 0, 01 is +1, 10 is -1, 11 is
invalid under `pair`). A zamin realisation of an operation would take the same conformance vectors through that
table at its pins; repsynth does not model zamin's analogue behaviour, its high-impedance zero or its spawning
operator, and claims nothing about them.

## State

The edge is declared at repsynth's and jugaad28's end only; zamin has not declared it back, so under jugaad28's
J6 it is OWED. Nothing here is fabricated or measured silicon; FPGA figures in reports/hardware/ are
measurements of an open flow, not claims about any ASIC.
"""


# ---------------------------------------------------------------- P5.2 HLS route record

HLS_PROBES = [
    ("apt", ["apt-cache", "policy", "panda-bambu", "bambu"]),
    ("apt-search", ["apt-cache", "search", "bambu"]),
    ("appimage-release-site", ["curl", "-sS", "-L", "-o", "/dev/null", "-w", "http=%{http_code} size=%{size_download}", "--max-time", "60",
                               "https://release.bambuhls.eu/bambu-latest.AppImage"]),
    ("appimage-github", ["curl", "-sS", "-L", "-o", "/dev/null", "-w", "http=%{http_code} size=%{size_download}", "--max-time", "60",
                         "https://github.com/ferrandi/PandA-bambu/releases/download/v2024.03/bambu-2024.03.AppImage"]),
    ("github-archive-control", ["curl", "-sS", "-L", "-o", "/dev/null", "-w", "http=%{http_code} size=%{size_download}", "--max-time", "60",
                                "https://github.com/verilator/verilator/archive/refs/tags/v5.036.tar.gz"]),
    ("git-tags", ["git", "ls-remote", "--tags", "https://github.com/ferrandi/PandA-bambu.git"]),
    ("path", ["sh", "-c", "command -v bambu || echo 'bambu: not on PATH'"]),
]


def hls() -> int:
    """P5.2: try an open HLS tool for one unit (bt_add16 from the reference function); record what happened."""
    t0 = utc_now()
    probes = {}
    for name, cmd in HLS_PROBES:
        try:
            r = sh(cmd, timeout=180)
            text = (r.stdout + r.stderr).strip().splitlines()
            probes[name] = {"command": " ".join(cmd), "exit_code": r.returncode, "output": text[-4:] if text else []}
        except subprocess.TimeoutExpired:
            probes[name] = {"command": " ".join(cmd), "exit_code": None, "output": ["timed out"]}
    have = sh(["sh", "-c", "command -v bambu"]).returncode == 0
    synth = {}
    sp = sorted((ROOT / "records").glob("*_P5.4_synth.json"))
    if sp:
        synth = json.loads(sp[-1].read_text())["results"]["units"].get("bt_add16", {})
    state = "not_built" if not have else "wired_unproven"
    rec = write_record("P5.2", "hls", "repsynth hdl hls", 0 if have else 1, started_utc=t0, tool_versions=tool_versions(),
                       results={"tool": "PandA Bambu", "available": have, "probes": probes,
                                "direct_route_bt_add16": {"luts": synth.get("unit_resources", {}).get("luts"),
                                                          "fmax_mhz_wrapped": synth.get("fmax_mhz"), "latency_cycles": 0,
                                                          "record": rel(sp[-1]) if sp else None}},
                       state=state, notes="The HLS route is not established here: no package, the release downloads are refused by "
                                          "the network proxy, and a source build of Bambu (LLVM and Boost toolchains) was not attempted.")
    _write_adr(probes, synth, sp[-1] if sp else None, have)
    write_status("P5.2", state, [rel(rec)],
                 "Decision record written; the HLS route (PandA Bambu) is not established here, so only the direct route has measured "
                 "resources and latency.", blocked_by=[] if have else ["PandA Bambu not obtainable: apt has no package; release downloads answer 403/404 through the proxy"])
    print(f"hls: Bambu available: {have}; state {state}")
    return 0 if have else 1


def _write_adr(probes, synth, srec, have):
    REPORTS.mkdir(parents=True, exist_ok=True)
    ur = synth.get("unit_resources", {})
    L = ["<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->", "",
         "# Architecture decision record: route from specification to hardware (P5.2, HDL-01)", "",
         "Status: decided for the first build, direct route; the HLS route is **not established** here and stays open.", "",
         "## Context", "",
         "HDL-01 allows two routes per promoted operation: units generated directly from the specification's tables and "
         "bit definitions, or units produced by an open high-level synthesis tool from the reference function. The route is "
         "recorded per unit. The specification names `generation/hardware/route: direct` for balanced ternary.", "",
         "## Routes compared on one unit (bt_add16, 16-trit add)", "",
         "| Route | Tool | LUT4 (bare unit) | Fmax in register wrapper (MHz) | Latency (cycles) | State |", "|---|---|---:|---:|---:|---|",
         f"| Direct | repsynth.gen.hdl 0.3.0; Yosys synth_ice40; nextpnr-ice40 (iCE40 UP5K) | {ur.get('luts', 'not established')} | "
         f"{synth.get('fmax_mhz', 'not established')} | 0 (combinational) | measured, {rel(srec) if srec else 'no record'} |",
         "| HLS | PandA Bambu from spec/ref/balanced_ternary/balanced_ternary.c | not established | not established | not established | "
         + ("tool present, not run" if have else "tool not obtainable here") + " |", "",
         "## What was tried for the HLS route", "", "| Probe | Command | Exit | Output |", "|---|---|---|---|"]
    for k, v in probes.items():
        out = " / ".join(v["output"])[:220].replace("|", "\\|")
        L.append(f"| {k} | `{v['command'][:120]}` | {v['exit_code']} | {out} |")
    L += ["", "## Decision", "",
          "- Every promoted balanced ternary operation and the binary baseline units use the direct route. It is the only route "
          "with measured figures here; it reads the encoding through the recording accessor, so change D2(d) regenerates the "
          "units exactly; and it needs no tool beyond those already in the hardware container.",
          "- The reference functions are written for software (loops over trits with 64-bit integer arithmetic, `% 3`), so an "
          "HLS tool would synthesise integer division by three where the direct route uses a ternary ripple cell; whether "
          "Bambu does better on area or latency is not established until it runs.",
          "- To establish the HLS route: obtain PandA Bambu (its AppImage or a source build from tag v2024.03 of "
          "ferrandi/PandA-bambu) in the repsynth-hdl container, run `bambu --top-fname=bt_add16 spec/ref/balanced_ternary/balanced_ternary.c` "
          "with the generated codec header, and add its Yosys and nextpnr figures to the table above with `repsynth hdl hls`.", "",
          "## Question for the author", "",
          "May the hardware container build PandA Bambu from source (a long build pulling an LLVM toolchain), or should the HLS "
          "route wait until a packaged release is reachable from the build machine?"]
    (REPORTS / "adr_hdl_route.md").write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------- P5.5 and P5.11: the open core

CORE = {"name": "cv32e40x", "url": "https://github.com/openhwgroup/cv32e40x.git",
        "commit": "d952cd63bc1b4eb58cd893c28ef8283c781e345e", "tree": "e26f1433c878133f7831147a895655a02e011c1b",
        "why": "OpenHW CV32E40X implements the CV-X-IF eXtension interface natively (HDL-05) and RV32IMAC "
               "(M_EXT=M, A_EXT=A, C always on); it builds with the host Verilator 5.020 once BLKANDNBLK is "
               "downgraded, so no smaller substitute core was needed."}
COSIM = CACHE / "cosim"
COSIM_SRC = ROOT / "lanes" / "hdl" / "cosim"
XIF_OUT = ROOT / "gen" / "hdl" / "xif" / "rs_xif_xayebt.sv"
TIERA_BIN = ROOT / ".cache" / "tiera" / "bin" / "test_xayebt.rv32"
QEMU_PATCHED = ROOT / ".cache" / "qemu-patched"
QEMU_STOCK = ROOT / ".cache" / "qemu-stock"
VERILATOR_FLAGS = ["-O3", "-Wno-fatal", "-Wno-lint", "-Wno-style", "-Wno-UNOPTFLAT", "-Wno-BLKANDNBLK"]
MAX_CYCLES = 400_000_000


def git_ids(d: Path) -> dict:
    return {"commit": sh(["git", "-C", d, "rev-parse", "HEAD"]).stdout.strip(),
            "tree": sh(["git", "-C", d, "rev-parse", "HEAD^{tree}"]).stdout.strip(),
            "status_clean": sh(["git", "-C", d, "status", "--porcelain"]).stdout.strip() == ""}


def ensure_clone(name: str, url: str, commit: str) -> dict:
    """Shallow, read-only clone pinned to a commit, under .cache/hdl (git-ignored). Never edited."""
    d = CACHE / name
    if not d.exists():
        r = sh(["git", "clone", "-q", "--depth", "1", url, d])
        if r.returncode:
            raise RuntimeError(f"git clone {url} failed ({r.returncode}): {r.stderr}")
    ids = git_ids(d)
    if commit and ids["commit"] != commit:
        sh(["git", "-C", d, "fetch", "-q", "--depth", "1", "origin", commit])
        sh(["git", "-C", d, "checkout", "-q", commit])
        ids = git_ids(d)
    return {"url": url, **ids}


def ledger_entries(ops) -> tuple[list[dict], dict]:
    import yaml
    ents, hashes = [], {}
    for op in ops:
        p = ROOT / "ledger" / "allocations" / "balanced_ternary" / f"{op}.yaml"
        if not p.exists():
            raise FileNotFoundError(f"no ledger entry {rel(p)}: the coprocessor never invents an encoding")
        ents.append(yaml.safe_load(p.read_text()))
        hashes[rel(p)] = sha256_file(p)
    return ents, hashes


def gen_xif(digits: int = 16) -> tuple[Path, list[str], dict]:
    import importlib.util
    spec = importlib.util.spec_from_file_location("repsynth_gen_hdl_xif", ROOT / "gen" / "hdl" / "xif.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    ops = list(graph_hdl.promoted()[0]["balanced_ternary"])
    ents, hashes = ledger_entries(ops)
    text = m.generate(ents, digits, hashes)
    XIF_OUT.parent.mkdir(parents=True, exist_ok=True)
    if not XIF_OUT.exists() or XIF_OUT.read_text() != text:
        XIF_OUT.write_text(text)
    return XIF_OUT, ops, hashes


def core_files(core_dir: Path) -> list[Path]:
    rtl, bhv = core_dir / "rtl", core_dir / "bhv"
    first = [rtl / "include" / "cv32e40x_pkg.sv", rtl / "cv32e40x_if_c_obi.sv", rtl / "cv32e40x_if_xif.sv"]
    rest = sorted(p for p in rtl.glob("*.sv") if p not in first)
    return first + rest + [bhv / "cv32e40x_sim_clock_gate.sv"]


def build_stubs() -> Path:
    COSIM.mkdir(parents=True, exist_ok=True)
    elf, bin_ = COSIM / "stubs.elf", COSIM / "stubs.bin"
    r = sh(["riscv64-unknown-elf-gcc", "-march=rv32i_zicsr", "-mabi=ilp32", "-nostdlib", "-nostartfiles",
            "-Wl,-Ttext=0x800", "-Wl,--entry=rs_boot", "-o", elf, COSIM_SRC / "rs_trap.S"], log=COSIM / "stubs.log")
    if r.returncode:
        raise RuntimeError(f"stub assembly failed: {r.stderr}")
    sh(["riscv64-unknown-elf-objcopy", "-O", "binary", elf, bin_])
    return bin_


def build_platform(variant: str, units_sv=None, tag: str = None) -> dict:
    """variant 'xif' (core + generated coprocessor) or 'base' (core alone)."""
    core = CACHE / CORE["name"]
    tag = tag or variant
    obj = COSIM / tag / "obj"
    shutil.rmtree(obj.parent, ignore_errors=True)
    obj.mkdir(parents=True)
    srcs = core_files(core)
    defs = []
    if variant == "xif":
        if units_sv is None:
            units_sv = [ROOT / graph_hdl.UNITS / "balanced_ternary" / "sv" / f"bt_{op}16.sv" for op in graph_hdl.promoted()[0]["balanced_ternary"]]
        srcs += list(units_sv) + [XIF_OUT]
        defs = ["+define+RS_XIF"]
    srcs += [COSIM_SRC / "rs_tb_top.sv"]
    cmd = ["verilator", "--cc", "--exe", "--build", "-j", JOBS, *VERILATOR_FLAGS, *defs, "--top-module", "rs_tb_top",
           "--Mdir", obj, f"-I{core / 'rtl' / 'include'}", *srcs, COSIM_SRC / "rs_tb_main.cpp", "-o", "rs_tb"]
    r = sh(cmd, log=obj.parent / "build.log", timeout=7200)
    exe = obj / "rs_tb"
    return {"variant": variant, "exit_code": r.returncode, "exe": exe if exe.exists() else None,
            "command": " ".join(str(c) for c in cmd), "log": rel(obj.parent / "build.log"),
            "sources": {rel(p): sha256_file(p) for p in srcs}}


def run_core(exe: Path, elf: Path, args, work: Path, triggers=None) -> dict:
    work.mkdir(parents=True, exist_ok=True)
    stubs = COSIM / "stubs.bin"
    tr = [hex(triggers[0]), hex(triggers[1])] if triggers else ["-", "-"]
    cmd = [exe, elf, stubs, work / "stdout.txt", work / "summary.json", str(MAX_CYCLES), *tr, "--", *args]
    r = sh(cmd, log=work / "run.log", timeout=6 * 3600)
    summ = json.loads((work / "summary.json").read_text()) if (work / "summary.json").exists() else {}
    return {"exit_code": r.returncode, "summary": summ, "stdout": (work / "stdout.txt").read_bytes() if (work / "stdout.txt").exists() else b"",
            "command": " ".join(str(c) for c in cmd)}


def run_qemu(qemu: list, elf: Path, args) -> dict:
    cmd = [*qemu, elf, *args]
    r = subprocess.run([str(c) for c in cmd], capture_output=True, timeout=3600)
    return {"exit_code": r.returncode, "stdout": r.stdout, "stderr": r.stderr.decode(errors="replace")[-400:],
            "command": " ".join(str(c) for c in cmd)}


def symbol(elf: Path, name: str) -> int | None:
    out = sh(["riscv64-unknown-elf-nm", elf]).stdout
    for line in out.splitlines():
        p = line.split()
        if len(p) == 3 and p[2] == name:
            return int(p[0], 16)
    return None


def _parallel(fn, items, n=int(JOBS)):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=n) as ex:
        return list(ex.map(fn, items))


def cosim() -> int:
    """P5.5: Tier A's compiled vector test program, one binary, on the Verilated cv32e40x with the
    generated coprocessor and in Tier A's patched QEMU user mode; every vector, results compared byte for byte."""
    t0 = utc_now()
    clone = ensure_clone(CORE["name"], CORE["url"], CORE["commit"])
    xif, ops, ledger = gen_xif(16)
    blocked = []
    if not TIERA_BIN.exists():
        blocked.append(f"P4.3 test program {rel(TIERA_BIN)}")
    if not (QEMU_PATCHED / "qemu-riscv32").exists():
        blocked.append(f"P4.2 patched QEMU {rel(QEMU_PATCHED / 'qemu-riscv32')}")
    lint = lint_xif()
    build_stubs()
    b = build_platform("xif")
    results, refusal = {}, {}
    if b["exe"] and not blocked:
        elf = COSIM / "test_xayebt.rv32"      # frozen copy of the binary both machines run
        shutil.copy2(TIERA_BIN, elf)
        qemu = [QEMU_PATCHED / "qemu-riscv32", "-cpu", "rv32,x-xayebt=on"]

        def one(op):
            vec = ROOT / "conformance" / "vectors" / "balanced_ternary" / f"{op}.16.vec"
            c = run_core(b["exe"], elf, [vec], COSIM / "runs" / op)
            q = run_qemu(qemu, elf, [vec])
            last = c["stdout"].decode(errors="replace").strip().splitlines()
            return op, {"vectors": rel(vec), "vectors_sha256": sha256_file(vec),
                        "core_exit": c["exit_code"], "qemu_exit": q["exit_code"],
                        "equal_stdout": c["stdout"] == q["stdout"] and len(c["stdout"]) > 0,
                        "core_stdout_tail": last[-2:], "qemu_stdout_tail": q["stdout"].decode(errors="replace").strip().splitlines()[-2:],
                        "core_cycles": c["summary"].get("cycles"), "core_retired": c["summary"].get("retired"),
                        "core_fault": c["summary"].get("fault"), "core_command": c["command"], "qemu_command": q["command"]}
        results = dict(_parallel(one, ops))
        for op, r in results.items():
            print(f"  {op:9s} core exit {r['core_exit']} qemu exit {r['qemu_exit']} equal {r['equal_stdout']} {r['core_stdout_tail']}", flush=True)
        refusal = cosim_refusal(elf, qemu)
    ok = (not blocked and b["exit_code"] == 0 and len(results) == len(ops) and lint["own_file_warnings"] == 0 and
          all(r["core_exit"] == 0 and r["qemu_exit"] == 0 and r["equal_stdout"] and "RESULT PASS" in r["core_stdout_tail"] for r in results.values())
          and refusal.get("caught") is True)
    state = "done" if ok else ("not_built" if blocked else "failed")
    rec = write_record("P5.5", "cosim", "repsynth hdl cosim", 0 if ok else 1, started_utc=t0,
                       inputs=[xif, COSIM_SRC / "rs_tb_top.sv", COSIM_SRC / "rs_tb_main.cpp", COSIM_SRC / "rs_trap.S"]
                       + ([COSIM / "test_xayebt.rv32"] if (COSIM / "test_xayebt.rv32").exists() else []) + [ROOT / k for k in ledger],
                       outputs=[xif], tool_versions={**tool_versions(), "riscv64-unknown-elf-gcc": first_line(["riscv64-unknown-elf-gcc", "--version"]),
                                                     "qemu-riscv32(patched)": first_line([QEMU_PATCHED / "qemu-riscv32", "--version"]),
                                                     "qemu-patched PIN": (QEMU_PATCHED / "PIN").read_text().strip() if (QEMU_PATCHED / "PIN").exists() else "absent"},
                       results={"core": {**CORE, "clone": clone}, "ops": ops, "build": {k: v for k, v in b.items() if k != "exe"},
                                "xif_lint": lint, "runs": results, "planted_defect": refusal,
                                "binary_sha256": sha256_file(COSIM / "test_xayebt.rv32") if (COSIM / "test_xayebt.rv32").exists() else None},
                       state=state, notes="One binary (Tier A's test_xayebt.rv32) on both machines. The core runs it through a platform "
                                          "harness that loads it as Linux exec does and serves openat, read, close, write and exit through "
                                          "a trap stub outside the program.")
    write_status("P5.5", state, [rel(rec)],
                 f"CV-X-IF coprocessor for {len(ops)} balanced ternary operations on a Verilated cv32e40x; the same binary in patched QEMU: "
                 + ("results equal on every vector." if ok else "NOT accepted, see the record."), blocked_by=blocked)
    _write_cosim_report(results, ops, refusal, lint, clone)
    return 0 if ok else 1


def lint_xif() -> dict:
    core = CACHE / CORE["name"]
    units_sv = [ROOT / graph_hdl.UNITS / "balanced_ternary" / "sv" / f"bt_{op}16.sv" for op in graph_hdl.promoted()[0]["balanced_ternary"]]
    r = sh(["verilator", "--lint-only", "-Wall", core / "rtl" / "cv32e40x_if_xif.sv", *units_sv, XIF_OUT, "--top-module", "rs_xif_xayebt"])
    own = [l for l in r.stderr.splitlines() if l.startswith("%") and (XIF_OUT.name in l or "/bt_" in l)]
    return {"command": "verilator --lint-only -Wall <cv32e40x_if_xif.sv> <units> rs_xif_xayebt.sv", "exit_code": r.returncode,
            "own_file_warnings": len(own), "own_messages": own[:10],
            "note": "warnings in the upstream interface file (signals a lone coprocessor leaves dangling) are not counted"}


def cosim_refusal(elf: Path, qemu) -> dict:
    """The comparison is shown refusing a planted defect: a flipped truth-table bit in a copy of bt_add16."""
    from repsynth.lanes import selftest_hdl as st
    src = ROOT / graph_hdl.UNITS / "balanced_ternary" / "sv" / "bt_add16.sv"
    d = COSIM / "planted"
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    m = d / "bt_add16.sv"
    edit = next(x for x in st.MUTANTS if x[0] == "flip-add-cell")[3]["sv"]
    m.write_text(st.plant(src.read_text(), *edit, "bt_add16.sv"))
    units = [m if p.name == "bt_add16.sv" else p for p in
             [ROOT / graph_hdl.UNITS / "balanced_ternary" / "sv" / f"bt_{op}16.sv" for op in graph_hdl.promoted()[0]["balanced_ternary"]]]
    b = build_platform("xif", units_sv=units, tag="xif-planted")
    if not b["exe"]:
        return {"caught": False, "refusal": f"planted build failed: {b['log']}"}
    vec = ROOT / "conformance" / "vectors" / "balanced_ternary" / "add.16.vec"
    c = run_core(b["exe"], elf, [vec], d / "run")
    q = run_qemu(qemu, elf, [vec])
    tail = c["stdout"].decode(errors="replace").strip().splitlines()[-2:]
    caught = c["stdout"] != q["stdout"] and c["exit_code"] != 0
    return {"caught": caught, "mutant": rel(m), "edit": list(edit), "core_exit": c["exit_code"], "core_stdout_tail": tail,
            "refusal": f"core output differs from QEMU's; core reports {tail}" if caught else "NOT caught"}


def _write_cosim_report(results, ops, refusal, lint, clone):
    REPORTS.mkdir(parents=True, exist_ok=True)
    L = ["<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->", "",
         "# One program on two machines (P5.5, D4, T-23)", "",
         f"Core: {CORE['name']} {clone.get('commit')} ({CORE['url']}). {CORE['why']}", "",
         "Coprocessor: gen/hdl/xif/rs_xif_xayebt.sv, generated from the allocation ledger (custom-0, funct3 7) around the "
         "16-trit units. The program is Tier A's test_xayebt.rv32 (RV32IMAC), unchanged; QEMU is Tier A's patched "
         "qemu-riscv32 with `-cpu rv32,x-xayebt=on`. Cycle counts are from the Verilated core, never claims about silicon.", "",
         "| Operation | Core | QEMU | Output equal | Core cycles | Core retired |", "|---|---|---|---|---:|---:|"]
    for op in ops:
        r = results.get(op)
        if not r:
            L.append(f"| {op} | not run | not run | | | |")
            continue
        L.append(f"| {op} | exit {r['core_exit']}, {' '.join(r['core_stdout_tail'])} | exit {r['qemu_exit']} | {'yes' if r['equal_stdout'] else 'NO'} | "
                 f"{r['core_cycles']} | {r['core_retired']} |")
    L += ["", f"Planted defect (flipped adder-cell bit in bt_add16): {'caught' if refusal.get('caught') else 'NOT caught'}; {refusal.get('refusal', 'not run')}.",
          "", f"Coprocessor lint (verilator -Wall): {lint['own_file_warnings']} warnings in generated files."]
    (REPORTS / "cosim.md").write_text("\n".join(L) + "\n")


def baseline() -> int:
    """P5.11: the P4.13 RV32IMAC workload binaries, unchanged, on the Verilated cv32e40x without the coprocessor;
    cycles and retired instructions, twice; outputs and exit codes compared with stock QEMU user mode."""
    t0 = utc_now()
    clone = ensure_clone(CORE["name"], CORE["url"], CORE["commit"])
    bj = ROOT / "reports" / "baseline" / "baseline.json"
    blocked = [] if bj.exists() else ["P4.13 reports/baseline/baseline.json"]
    rows = {r["workload"]: r for r in json.loads(bj.read_text())["rows"] if r["profile"] == "RV32IMAC"} if bj.exists() else {}
    build_stubs()
    b = build_platform("base")
    qemu = [QEMU_STOCK / "qemu-riscv32"]
    out = {}
    if b["exe"] and rows:
        def one(name):
            elf = ROOT / ".cache" / "baseline" / "build" / "RV32IMAC" / f"{name}.elf"
            if not elf.exists() or sha256_file(elf) != rows[name]["elf_sha256"]:
                return name, {"error": f"binary absent or differs from the P4.13 record: {rel(elf)}"}
            trig = (symbol(elf, "start_trigger"), symbol(elf, "stop_trigger"))
            trig = trig if None not in trig else None
            runs = [run_core(b["exe"], elf, [], COSIM / "baseline" / name / f"run{i}", triggers=trig) for i in (1, 2)]
            q = run_qemu(qemu, elf, [])
            s1, s2 = runs[0]["summary"], runs[1]["summary"]
            keys = ("cycles", "retired", "region_cycles", "region_retired", "exit_code")
            return name, {"elf_sha256": rows[name]["elf_sha256"], "qemu_insns_P4.13": rows[name]["insns"],
                          "core_exit": runs[0]["exit_code"], "fault": s1.get("fault"), "qemu_exit": q["exit_code"],
                          "equal_stdout": runs[0]["stdout"] == q["stdout"],
                          "cycles": s1.get("cycles"), "retired": s1.get("retired"),
                          "region_cycles": s1.get("region_cycles"), "region_retired": s1.get("region_retired"),
                          "reproduced": all(s1.get(k) == s2.get(k) for k in keys) and runs[0]["stdout"] == runs[1]["stdout"],
                          "command": runs[0]["command"]}
        out = dict(_parallel(one, sorted(rows)))
        for k, v in out.items():
            print(f"  {k:16s} exit {v.get('core_exit')} cycles {v.get('cycles')} retired {v.get('retired')} qemu {v.get('qemu_insns_P4.13')} "
                  f"equal {v.get('equal_stdout')} reproduced {v.get('reproduced')} {v.get('error') or v.get('fault') or ''}", flush=True)
    ok = (not blocked and b["exit_code"] == 0 and out and
          all(v.get("core_exit") == 0 and v.get("equal_stdout") and v.get("reproduced") for v in out.values()))
    state = "done" if ok else ("not_built" if blocked else "failed")
    rec = write_record("P5.11", "baseline", "repsynth hdl baseline", 0 if ok else 1, started_utc=t0,
                       inputs=[COSIM_SRC / "rs_tb_top.sv", COSIM_SRC / "rs_tb_main.cpp", COSIM_SRC / "rs_trap.S", bj],
                       tool_versions={**tool_versions(), "qemu-riscv32(stock)": first_line([QEMU_STOCK / "qemu-riscv32", "--version"])},
                       results={"core": {**CORE, "clone": clone}, "build": {k: v for k, v in b.items() if k not in ("exe", "sources")},
                                "workloads": out},
                       state=state, notes="Cycles of the Verilated core (single-cycle memories that grant at once), never hardware speed. "
                                          "Retired counts use the core's minstret event, which excludes trapping instructions (ecall).")
    _write_baseline_report(out, clone)
    write_status("P5.11", state, [rel(rec)],
                 f"{len(out)} RV32IMAC workloads of P4.13 on the Verilated cv32e40x, run twice: "
                 + ("cycles recorded, reproduced, outputs equal to QEMU's." if ok else "NOT accepted, see the record."), blocked_by=blocked)
    return 0 if ok else 1


def _write_baseline_report(out, clone):
    REPORTS.mkdir(parents=True, exist_ok=True)
    L = ["<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->", "",
         "# Binary hardware baseline: cycles on a Verilated open core (P5.11, D14, T-29)", "",
         f"Core: {CORE['name']} {clone.get('commit')}, RV32IMAC, no coprocessor; memories grant at once and answer in one "
         "cycle. The binaries are exactly those of P4.13 (sha256 checked). 'Region' counts run from the retirement of "
         "start_trigger to the retirement of stop_trigger (Embench's timed region). Simulated cycles, never hardware speed. "
         "QEMU counts are P4.13's dynamic instruction counts for the whole program.", "",
         "| Workload | Cycles | Retired | Region cycles | Region retired | CPI (whole) | QEMU insns (P4.13) | Output equal to QEMU | Reproduced |",
         "|---|---:|---:|---:|---:|---:|---:|---|---|"]
    for k, v in out.items():
        if "error" in v:
            L.append(f"| {k} | {v['error']} | | | | | | | |")
            continue
        cpi = round(v["cycles"] / v["retired"], 3) if v.get("cycles") and v.get("retired") else ""
        L.append(f"| {k} | {v['cycles']} | {v['retired']} | {v['region_cycles'] if v.get('region_cycles', -1) != -1 else ''} | "
                 f"{v['region_retired'] if v.get('region_retired', -1) != -1 else ''} | {cpi} | {v['qemu_insns_P4.13']} | "
                 f"{'yes' if v['equal_stdout'] else 'NO'} | {'yes' if v['reproduced'] else 'NO'} |")
    L += ["", "Synthesis figures for the generated binary and balanced ternary units are in synthesis.md, side by side."]
    (REPORTS / "baseline_cycles.md").write_text("\n".join(L) + "\n")


# ---------------------------------------------------------------- dispatcher

STEPS = {"setup": setup, "gen": gen, "lint": lint, "sim": sim, "mutate": mutate, "synth": synth, "cosim": cosim, "baseline": baseline, "hls": hls, "handoff": handoff}


def main(argv) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    step, rest = argv[0], argv[1:]
    if step == "all":
        rc = 0
        for s in ORDER:
            print(f"== hdl {s}", flush=True)
            rc |= STEPS[s]()
        return rc
    if step not in STEPS:
        print(f"unknown hdl step {step!r}; steps: {', '.join(STEPS)}, all")
        return 2
    f = STEPS[step]
    return f(rest) if rest and step in ("sim", "synth") else f()


ORDER = ["setup", "gen", "lint", "sim", "mutate", "synth", "hls", "cosim", "baseline", "handoff"]


def run(ctx) -> int:
    return main(list(getattr(ctx, "rest", []) or []))
