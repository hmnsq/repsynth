# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tier B generators as nodes of the dependency graph (DEP-01 to DEP-03; P7.1 to P7.4).

Per instance <n> of the word machine family:
  isb-spec:<n>    spec/reps/machine/<n>.yaml                  instance specification (from the family)
  isb-ref:<n>     spec/ref/machine_<n>/<n>.{h,c}              reference functions
  isb-asm:<n>     gen/isb/targets/<n>/<n>.cpu.asm, roundtrip   customasm definition and round-trip source
  isb-qemu:<n>    gen/isb/targets/<n>/qemu/**                  QEMU target and board
Per family:
  isb-patches     gen/isb/targets/qemu_patches.json            exact-anchor patch set for the pinned tree
  isb-workloads   gen/isb/targets/bwm/workloads/*              binary machine workloads (P7.4 counts)
Outputs are written only when their bytes change and carry the generator version and the hashes of the
specifications they come from (no timestamps).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from repsynth.records import ROOT

GEN = "gen/isb"
LANE_FILE = "repsynth/lanes/graph_isb.py"
FAMILY = "spec/reps/machine/word_machine_family.yaml"
FAMILY_ID = "word_machine_family"


def _mod(name: str, root: Path = ROOT):
    p = root / GEN / f"{name}.py"
    if str(root / GEN) not in sys.path:
        sys.path.insert(0, str(root / GEN))
    s = importlib.util.spec_from_file_location(f"repsynth_isb_{name}", p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def _instances(root: Path) -> dict:
    return _mod("isa", root).instances(root)


def _outputs(kind: str, n: str | None, root: Path) -> dict:
    if kind == "isb-spec":
        return {f"spec/reps/machine/{n}.yaml": None}
    if kind == "isb-ref":
        return _mod("gen_ref", root).render(n, root)
    if kind == "isb-asm":
        return _mod("gen_asm", root).render(n, root)
    if kind in ("isb-qemu", "isb-patches"):
        allf = _mod("gen_qemu", root).render(root)
        if kind == "isb-patches":
            return {k: v for k, v in allf.items() if k.endswith("qemu_patches.json")}
        return {k: v for k, v in allf.items() if k.startswith(f"gen/isb/targets/{n}/qemu/")}
    if kind == "isb-workloads":
        return _mod("gen_workloads", root).render(root)
    raise KeyError(kind)


def nodes(root: Path = ROOT):
    from repsynth.graph import Node
    out = []
    py = [sys.executable, "-m", "repsynth", "gen-one"]
    isa_in = [f"{GEN}/isa.py", LANE_FILE]
    names = list(_instances(root))
    for n in names:
        num = _mod("isa", root).NUMERIC_PATHS[_instances(root)[n]["numeric"]]
        spec_out = f"spec/reps/machine/{n}.yaml"
        fam_reads = ["/identity", "/structure", "/encoding", "/decoding", "/semantics", "/composition",
                     "/constraints", "/interfaces", "/verification", f"/generation/isb/instances/{n}", "/evolution",
                     "/provenance"]
        out.append(Node(f"isb-spec:{n}", FAMILY_ID, fam_reads, isa_in + [f"{GEN}/instantiate.py", num], [spec_out],
                        py + [f"isb-spec:{n}"], kind="tier_b", edges=[("implements", spec_out, f"{FAMILY_ID}#/generation/isb/instances/{n}")]))
        ref = list(_outputs("isb-ref", n, root))
        out.append(Node(f"isb-ref:{n}", n, ["/operations", "/structure/parameters", "/domain/widths"],
                        isa_in + [f"{GEN}/gen_ref.py", spec_out, num], ref, py + [f"isb-ref:{n}"], kind="tier_b",
                        edges=[("implements", o, f"{n}#/operations") for o in ref]))
        asm = list(_outputs("isb-asm", n, root))
        out.append(Node(f"isb-asm:{n}", n, ["/encoding/encodings/fixed32", "/interfaces/memory_map"],
                        isa_in + [f"{GEN}/gen_asm.py", spec_out], asm, py + [f"isb-asm:{n}"], kind="tier_b",
                        edges=[("implements", o, f"{n}#/encoding/encodings/fixed32") for o in asm]))
        q = list(_outputs("isb-qemu", n, root))
        out.append(Node(f"isb-qemu:{n}", n, ["/encoding/encodings/fixed32", "/operations", "/interfaces/memory_map",
                                               "/interfaces/fault_exit_code", "/structure/parameters"],
                        isa_in + [f"{GEN}/gen_qemu.py", spec_out] + ref, q, py + [f"isb-qemu:{n}"], kind="tier_b",
                        edges=[("implements", o, f"{n}#/encoding/encodings/fixed32") for o in q]))
    p = list(_outputs("isb-patches", None, root))
    out.append(Node("isb-patches", FAMILY_ID, ["/generation/isb/instances"],
                    isa_in + [f"{GEN}/gen_qemu.py"] + [f"spec/reps/machine/{n}.yaml" for n in names], p,
                    py + ["isb-patches"], kind="tier_b", edges=[("requires", o, f"{FAMILY_ID}#/generation/isb") for o in p]))
    if "bwm" in names:
        w = list(_outputs("isb-workloads", None, root))
        out.append(Node("isb-workloads", "bwm", ["/interfaces/memory_map"], isa_in + [f"{GEN}/gen_workloads.py", "spec/reps/machine/bwm.yaml"],
                        w, py + ["isb-workloads"], kind="tier_b", edges=[("validates", o, "bwm#/operations") for o in w]))
    return out


def _write(root: Path, rel: str, text: str) -> bool:
    p = root / rel
    if p.exists() and p.read_text(encoding="utf-8") == text:
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return True


def gen_one(node_id: str, root: Path = ROOT) -> bool:
    kind, _, n = node_id.partition(":")
    if kind not in ("isb-spec", "isb-ref", "isb-asm", "isb-qemu", "isb-patches", "isb-workloads"):
        return False
    if kind == "isb-spec":
        text = _mod("instantiate", root).render(n, root)
        _write(root, f"spec/reps/machine/{n}.yaml", text)
        return True
    for rel, text in _outputs(kind, n or None, root).items():
        _write(root, rel, text)
    return True
