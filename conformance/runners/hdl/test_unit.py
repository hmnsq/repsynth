# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""One cocotb test for every hardware unit (HDL-02, P5.3): it reads the shared vector file named by the
environment and drives the unit on whichever simulator cocotb runs (Verilator, GHDL).

Environment: RS_VECTORS (vector file), RS_ARITY (1 or 2), RS_RESULT (JSON summary written here).
Written to run unchanged on cocotb 1.9 and 2.x: only cocotb.test, Timer with the default step unit,
handle.value assignment and int(handle.value) are used."""
import json
import os

import cocotb
from cocotb.triggers import Timer


def read_vectors(path):
    head, rows = {}, []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                if ":" in line:
                    k, v = line[1:].split(":", 1)
                    head[k.strip()] = v.strip()
                continue
            rows.append([int(x, 16) for x in line.split()])
    return head, rows


@cocotb.test()
async def vectors(dut):
    path = os.environ["RS_VECTORS"]
    arity = int(os.environ["RS_ARITY"])
    head, rows = read_vectors(path)
    declared = int(head["cases"])
    if declared != len(rows):
        raise AssertionError(f"{path}: header says {declared} cases, file holds {len(rows)}")
    fails, first = 0, []
    for row in rows:
        if len(row) != arity + 1:
            raise AssertionError(f"{path}: row {row} does not have {arity} inputs and one output")
        dut.a.value = row[0]
        if arity == 2:
            dut.b.value = row[1]
        await Timer(1)
        try:
            got = int(dut.r.value)
        except ValueError:
            got = None  # unresolved bits (X or Z) count as a failure
        want = row[-1]
        if got != want:
            fails += 1
            if len(first) < 5:
                first.append({"inputs": [f"{x:x}" for x in row[:-1]], "expected": f"{want:x}",
                              "got": None if got is None else f"{got:x}"})
    summary = {"vectors": path, "cases": len(rows), "failures": fails, "first_failures": first,
               "cocotb": cocotb.__version__, "simulator": cocotb.SIM_NAME, "simulator_version": cocotb.SIM_VERSION,
               "toplevel": dut._name}
    out = os.environ.get("RS_RESULT")
    if out:
        with open(out, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2)
    assert fails == 0, f"{fails} of {len(rows)} vectors failed; first: {first[:2]}"
