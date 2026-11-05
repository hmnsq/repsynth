# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hardware mutation self-test (CNF-04, P5.8, T-24). Defects are planted in copies of generated units
under .cache/hdl/mutants (the generated tree is never touched); each copy runs through the same cocotb
test and vector file as the clean unit, on Verilator for SystemVerilog and on GHDL for VHDL. A defect is
caught when the run fails with at least one disagreeing vector.

Planted: flipped bits (a truth-table bit of the adder cell, a truth-table bit of the comparison cell, a
result bit of the multiplier, a result bit of the binary adder) and swapped ports (the operands of the
non-commutative sub and cmp, and the two code bits of every result trit of neg).
Not planted, with reason: swapped operands of add and mul are equivalent mutants (both commute), so no
test can catch them; they are listed in the report as equivalent."""
from __future__ import annotations

import shutil
from pathlib import Path

from repsynth.records import ROOT

# (id, kind, unit, {sv: (old, new), vhdl: (old, new)}); each old string must occur exactly once.
MUTANTS = [
    ("flip-add-cell", "flipped bit", "bt_add16", {
        "sv": ("6'b101000: tadd = 4'b0110;", "6'b101000: tadd = 4'b0100;"),
        "vhdl": ('when "101000" => return "0110";', 'when "101000" => return "0100";')}),
    ("flip-cmp-cell", "flipped bit", "bt_cmp16", {
        "sv": ("4'b1001: tcmp = 2'b10;", "4'b1001: tcmp = 2'b00;"),
        "vhdl": ('when "1001" => return "10";', 'when "1001" => return "00";')}),
    ("flip-mul-result", "flipped bit", "bt_mul32", {
        "sv": ("    if (invalid) r = {64{1'b1}};", "    r[17] = ~r[17];\n    if (invalid) r = {64{1'b1}};"),
        "vhdl": ("    if invalid = '1' then w := (others => '1'); end if;",
                 "    w(17) := not w(17);\n    if invalid = '1' then w := (others => '1'); end if;")}),
    ("flip-bin-add-result", "flipped bit", "bin_add32", {
        "sv": ("assign r = a + b;", "assign r = (a + b) ^ 32'h00010000;"),
        "vhdl": ("r <= std_logic_vector(unsigned(a) + unsigned(b));",
                 'r <= std_logic_vector(unsigned(a) + unsigned(b)) xor x"00010000";')}),
    ("swap-sub-operands", "swapped ports", "bt_sub16", {
        "sv": ("= dec({a[2*i+1], a[2*i]});", "= dec({b[2*i+1], b[2*i]}); // a"),
        "vhdl": ("d := dec(a(2*i+1) & a(2*i));", "d := dec(b(2*i+1) & b(2*i)); -- a")}),
    ("swap-cmp-operands", "swapped ports", "bt_cmp32", {
        "sv": ("= dec({a[2*i+1], a[2*i]});", "= dec({b[2*i+1], b[2*i]}); // a"),
        "vhdl": ("d := dec(a(2*i+1) & a(2*i));", "d := dec(b(2*i+1) & b(2*i)); -- a")}),
    ("swap-neg-code-bits", "swapped ports", "bt_neg16", {
        "sv": ("{r[2*i+1], r[2*i]} = enc(", "{r[2*i], r[2*i+1]} = enc("),
        "vhdl": ("w(2*i+1) := c(1); w(2*i) := c(0);", "w(2*i+1) := c(0); w(2*i) := c(1);")}),
]
EQUIVALENT = [
    ("swap-add-operands", "bt_add16, bt_add32, bin_add32, bin_add64: a + b = b + a"),
    ("swap-mul-operands", "bt_mul16, bt_mul32, bin_mul32, bin_mul64: a * b = b * a"),
]


def plant(text: str, old: str, new: str, where: str) -> str:
    n = text.count(old)
    if n != 1:
        raise RuntimeError(f"mutant anchor occurs {n} times in {where}: {old!r}")
    return text.replace(old, new, 1)


def run_mutants(root: Path = ROOT, log=print) -> dict:
    from repsynth.lanes import hdl
    us = {u["unit"]: u for u in hdl.units(root)}
    base = hdl.CACHE / "mutants"
    shutil.rmtree(base, ignore_errors=True)
    out = {}
    for mid, kind, unit, edits in MUTANTS:
        u = us[unit]
        for lang, sim in (("sv", "verilator"), ("vhdl", "ghdl")):
            src = u[lang]
            d = base / f"{mid}.{lang}"
            d.mkdir(parents=True)
            m = d / src.name
            m.write_text(plant(src.read_text(), *edits[lang], f"{unit}.{lang}"))
            res = hdl.sim_unit(unit, m, sim, u["vectors_path"], u["arity"], d / "work")
            sm = res["summary"] or {}
            # cocotb 1.9's makefile exits 0 even when a test fails, so the verdict comes from the test's own
            # summary and from results.xml, never from the exit code alone.
            caught = (sm.get("failures") or 0) > 0 and res["results_xml_failure"] is True
            ff = (sm.get("first_failures") or [{}])[0]
            refusal = (f"results.xml records a failure; {sm.get('failures')} of {sm.get('cases')} vectors disagree; first: inputs {ff.get('inputs')} "
                       f"expected {ff.get('expected')} got {ff.get('got')}") if caught else f"NOT caught (exit {res['exit_code']}, summary {sm})"
            key = f"{mid} [{kind}] {unit} {lang} on {sim}"
            out[key] = {"caught": caught, "refusal": refusal, "mutant": hdl.rel(m), "edit": list(edits[lang]),
                        "log": res["log"], "failures": sm.get("failures"), "cases": sm.get("cases")}
            log(f"  {'CAUGHT' if caught else 'MISSED'} {key}: {refusal}")
    return out


def selftest() -> dict:
    """Interface for `repsynth selftest`: {description: {"caught": bool, "refusal": str}}."""
    return {k: {"caught": v["caught"], "refusal": v["refusal"]} for k, v in run_mutants().items()}
