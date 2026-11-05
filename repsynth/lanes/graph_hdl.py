# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hardware generators as nodes of the dependency graph (DEP-01 to DEP-03; P5.1, P5.9).

One node per (specification, operation, artefact): SystemVerilog units, VHDL-2008 units and the cocotb
manifest that tells the shared cocotb test which units and vector files belong together. Each node reads
the specification only through the recording accessor and only at its declared pointers; outputs are
written only when their bytes change (restat)."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

from repsynth.records import ROOT

GEN_FILE = "gen/hdl/hdl.py"
LANE_FILE = "repsynth/lanes/graph_hdl.py"
UNITS = "gen/hdl/units"
MANIFESTS = "conformance/runners/hdl/manifests"
# The promoted set is read from P4.4's promotion report (reports/promotion/promotion.json): every
# balanced ternary operation whose "promoted" is true gets units. If that report is absent the lane falls
# back to the provisional working set it was first built with (add, sub, neg, mul, cmp) and says so.
# Binary add and mul are the baseline units of P5.11 (binary_integer has no candidates by design). A
# candidate that is not promoted (for example one appended by change D2(c)) gets no hardware unit.
PROMOTION = "reports/promotion/promotion.json"
PROVISIONAL = ("add", "sub", "neg", "mul", "cmp")
BASELINE = ("add", "mul")


def promoted(root: Path = ROOT) -> tuple[dict, str]:
    """({spec: (ops...)}, state). Operations keep the generator's order, never the report's."""
    from repsynth.records import sha256_file
    p = root / PROMOTION
    order = ("add", "sub", "neg", "mul", "cmp", "shl", "shr", "from_int", "to_int")
    if p.exists():
        prom = json.loads(p.read_text()).get("promotion", {})
        bt = tuple(op for op in order if prom.get(f"balanced_ternary.{op}", {}).get("promoted") is True)
        state = f"from {PROMOTION} (sha256 {sha256_file(p)})"
    else:
        bt, state = PROVISIONAL, "provisional pending P4.4 (no promotion report)"
    return {"balanced_ternary": bt, "binary_integer": BASELINE}, state


LANGS = ("sv", "vhdl", "cocotb")
NOTICE = "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI."


def _gen_module(root: Path = ROOT):
    p = root / GEN_FILE
    s = importlib.util.spec_from_file_location("repsynth_gen_hdl", p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _spec(sid: str, root: Path):
    from repsynth.numeric import spec_of
    return spec_of(sid, root)


def op_index(spec: dict, op: str) -> int:
    """Position of an operation; structural only (operations are appended, never reordered)."""
    return [o["name"] for o in spec["operations"]].index(op)


def manifest_reads(op_i: int) -> list[str]:
    return ["/identity/id", "/identity/version", f"/operations/{op_i}", "/domain/widths"]


def _outputs(gen, sid: str, op: str, lang: str, spec: dict) -> list[str]:
    widths = [w["digits"] for w in spec["domain"]["widths"]]
    pre = "bt" if sid == "balanced_ternary" else "bin"
    if lang == "sv":
        return [f"{UNITS}/{sid}/sv/{pre}_{op}{w}.sv" for w in widths]
    if lang == "vhdl":
        return [f"{UNITS}/{sid}/vhdl/{pre}_{op}{w}.vhd" for w in widths]
    return [f"{MANIFESTS}/{sid}/{op}.json"]


def nodes(root: Path = ROOT):
    from repsynth.graph import Node
    gen = _gen_module(root)
    out = []
    for sid, ops in promoted(root)[0].items():
        spec = _spec(sid, root)
        names = [o["name"] for o in spec["operations"]]
        for op in ops:
            if op not in names:
                continue
            i = op_index(spec, op)
            for lang in LANGS:
                nid = f"hdl:{sid}:{op}:{lang}"
                reads = gen.reads_for(sid, i) if lang != "cocotb" else manifest_reads(i)
                outs = _outputs(gen, sid, op, lang, spec)
                n = Node(nid, sid, reads, [GEN_FILE, LANE_FILE] if lang != "cocotb" else [LANE_FILE], outs,
                         [sys.executable, "-m", "repsynth", "gen-one", nid],
                         # The cocotb manifests are test wiring (unit names, widths, vector paths); they read no
                         # encoding, so change D2(d) leaves them unchanged and they are not hardware artefacts.
                         kind="hardware" if lang != "cocotb" else "hardware-tests",
                         edges=[("implements", o, f"{sid}#/operations/{i}") for o in outs if lang != "cocotb"]
                         + [("validates", o, f"{sid}#/operations/{i}") for o in outs if lang == "cocotb"])
                n.op = op
                n.lang = lang
                out.append(n)
    return out


def _write_if_changed(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def _digest(acc, reads) -> str:
    from repsynth.spec import canonical
    h = hashlib.sha256()
    for p in reads:
        h.update(p.encode() + b"=" + hashlib.sha256(canonical(acc(p))).hexdigest().encode() + b"\n")
    return h.hexdigest()


def generate_node(sid: str, op: str, lang: str, root: Path = ROOT) -> dict:
    """Run one node. Returns {"written": [paths changed], "outputs": [...], "reads": [...], "units": [...]}."""
    from repsynth.accessor import Accessor
    gen = _gen_module(root)
    spec = _spec(sid, root)
    i = op_index(spec, op)
    if lang == "cocotb":
        reads = manifest_reads(i)
        acc = Accessor(spec, reads, f"hdl:{sid}:{op}:cocotb")
        digest = _digest(acc, reads)
        opd = acc(f"/operations/{i}")
        pre = "bt" if sid == "balanced_ternary" else "bin"
        units = [{"unit": f"{pre}_{opd['name']}{w['digits']}", "digits": w["digits"], "register_bits": w["register_bits"],
                  "arity": opd["arity"], "vectors": f"conformance/vectors/{acc('/identity/id')}/{opd['name']}.{w['digits']}.vec"}
                 for w in acc("/domain/widths")]
        doc = {"_notice": f"{NOTICE} SPDX-License-Identifier: CC0-1.0",
               "generator": "repsynth.lanes.graph_hdl 0.3.0", "spec": sid, "version": acc("/identity/version"),
               "slice_sha256": digest, "op": opd["name"], "units": units}
        files = {_outputs(gen, sid, op, lang, spec)[0]: json.dumps(doc, indent=2, ensure_ascii=False) + "\n"}
    else:
        reads = gen.reads_for(sid, i)
        acc = Accessor(spec, reads, f"hdl:{sid}:{op}:{lang}")
        digest = _digest(acc, reads)
        res = gen.generate(acc, digest, i, lang)
        files = {f"{UNITS}/{sid}/{k}": v for k, v in res["files"].items()}
        units = res["units"]
    undeclared = set(acc.reads) - set(reads)
    unused = set(reads) - set(acc.reads)
    if undeclared or unused:
        raise RuntimeError(f"hdl:{sid}:{op}:{lang}: reads differ from the declaration: undeclared {sorted(undeclared)}, unused {sorted(unused)}")
    expected = set(_outputs(gen, sid, op, lang, spec))
    if set(files) != expected:
        raise RuntimeError(f"hdl:{sid}:{op}:{lang}: produced {sorted(files)}, declared {sorted(expected)}")
    written = [p for p, t in sorted(files.items()) if _write_if_changed(root / p, t)]
    return {"written": written, "outputs": sorted(files), "reads": reads, "units": units}


def gen_one(node_id: str, root: Path = ROOT) -> bool:
    parts = node_id.split(":")
    if len(parts) != 4 or parts[0] != "hdl":
        return False
    _, sid, op, lang = parts
    prom = promoted(root)[0]
    if sid not in prom or op not in prom[sid] or lang not in LANGS:
        raise KeyError(f"no hardware generator {node_id}")
    generate_node(sid, op, lang, root)
    return True


def generate_all(root: Path = ROOT) -> dict:
    res = {}
    for sid, ops in promoted(root)[0].items():
        for op in ops:
            for lang in LANGS:
                res[f"hdl:{sid}:{op}:{lang}"] = generate_node(sid, op, lang, root)
    return res


def run(ctx) -> int:  # not a subcommand of its own; present so the registry entry is uniform
    print("graph-hdl provides the hardware nodes of the dependency graph; use `repsynth gen` or `repsynth hdl gen`.")
    return 0
