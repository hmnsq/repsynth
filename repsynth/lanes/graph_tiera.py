# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Tier A generators as nodes of the dependency graph (DEP-01 to DEP-03; P4.1, P4.2, P4.3, P4.5, P4.9, P5.9).

Per operation (attribute `op` set):
  ledger:<sid>:<op>    ledger/allocations/<sid>/<op>.yaml       allocation entry (never moved once written)
  insn:<sid>:<op>      gen/insn/out/<sid>/ops/<op>.h            .insn macro and intrinsic
  qemu:<sid>:<op>      gen/qemu/out/<sid>/ops/<op>.*            translation function, helper declaration and body
  gas:<sid>:<op>       gen/binutils/out/<sid>/ops/<op>.*        opcode entry, MATCH/MASK, gas test lines
Per specification (op None):
  insn:<sid>           intrinsics header and the vector test program
  qemu:<sid>           decodetree file, includes, helper source, the anchor patch set
  gas:<sid>            binutils patch set and gas test files
  hindawi:<sid>        construct list of new mnemonics (ISA-11)

Every node reads the specification only through the recording accessor at its declared pointers, and
every output carries the generator version and the hash of exactly those slices (no timestamps).
Outputs are written only when their bytes change.
"""
from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

from repsynth.records import ROOT

GENERATOR_VERSION = "0.3.0"
LANE_FILE = "repsynth/lanes/graph_tiera.py"
LEDGER_FILE = "ledger/allocate.py"
EXTENSIONS = "ledger/extensions.yaml"
GEN_FILES = {"ledger": LEDGER_FILE, "insn": "gen/insn/gen_insn.py", "qemu": "gen/qemu/gen_qemu.py",
             "gas": "gen/binutils/gen_binutils.py", "hindawi": "gen/hindawi/gen_constructs.py"}
PER_OP = ("ledger", "insn", "qemu", "gas")
PER_SPEC = ("insn", "qemu", "gas", "hindawi")
NOTICE = "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI."


def tier_a_specs(root: Path = ROOT) -> list[str]:
    import yaml
    p = root / EXTENSIONS
    return list(yaml.safe_load(p.read_text())["extensions"]) if p.exists() else []


def extension(sid: str, root: Path = ROOT) -> dict:
    import yaml
    return yaml.safe_load((root / EXTENSIONS).read_text())["extensions"][sid]


def module(kind: str, root: Path = ROOT):
    p = root / GEN_FILES[kind]
    s = importlib.util.spec_from_file_location(f"repsynth_gen_{kind}", p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def spec_of(sid: str, root: Path = ROOT) -> dict:
    from repsynth.numeric import spec_of as _s
    return _s(sid, root)


def candidate_ops(spec: dict) -> list[tuple[int, str]]:
    """(index, name) of every candidate operation. Indices are structural (operations are appended)."""
    return [(i, o["name"]) for i, o in enumerate(spec.get("operations", [])) if o.get("candidate") is True]


def op_reads(i: int) -> list[str]:
    return ["/identity/id", "/identity/version", f"/operations/{i}", "/encoding/active", "/domain/widths",
            "/generation/tier_a"]


def spec_reads() -> list[str]:
    return ["/identity/id", "/identity/version", "/operations", "/encoding/active", "/domain/widths",
            "/generation/tier_a"]


def ledger_path(sid: str, op: str) -> str:
    return f"ledger/allocations/{sid}/{op}.yaml"


def op_outputs(kind: str, sid: str, op: str) -> list[str]:
    if kind == "ledger":
        return [ledger_path(sid, op)]
    if kind == "insn":
        return [f"gen/insn/out/{sid}/ops/{op}.h"]
    if kind == "qemu":
        b = f"gen/qemu/out/{sid}/ops/{op}"
        return [f"{b}.trans.c.inc", f"{b}.helper.h", f"{b}.helper.c.inc"]
    if kind == "gas":
        b = f"gen/binutils/out/{sid}/ops/{op}"
        return [f"{b}.opc.h", f"{b}.opc.c", f"{b}.s"]
    raise KeyError(kind)


def spec_outputs(kind: str, sid: str, root: Path = ROOT) -> list[str]:
    ext = extension(sid, root)["extension"]
    if kind == "insn":
        return [f"gen/insn/out/{sid}/{ext}.h", f"gen/insn/out/{sid}/test_{ext}.c"]
    if kind == "qemu":
        b = f"gen/qemu/out/{sid}"
        return [f"{b}/{ext}.decode", f"{b}/trans_{ext}.c.inc", f"{b}/helper_{ext}.h", f"{b}/{ext}_helper.c",
                f"{b}/patches.json"]
    if kind == "gas":
        b = f"gen/binutils/out/{sid}"
        return [f"{b}/{ext}-opc.h", f"{b}/{ext}-opc.c", f"{b}/patches.json", f"{b}/gas/{ext}.s", f"{b}/gas/{ext}.d"]
    if kind == "hindawi":
        return [f"gen/hindawi/out/{sid}/{ext}.constructs.json"]
    raise KeyError(kind)


def nodes(root: Path = ROOT):
    from repsynth.graph import Node
    out = []
    py = [sys.executable, "-m", "repsynth", "gen-one"]
    for sid in tier_a_specs(root):
        spec = spec_of(sid, root)
        ops = candidate_ops(spec)
        live = {k for k, f in GEN_FILES.items() if (root / f).exists()}
        for i, op in ops:
            for kind in (k for k in PER_OP if k in live):
                nid = f"{kind}:{sid}:{op}"
                inputs = [LANE_FILE, GEN_FILES[kind], EXTENSIONS]
                if kind != "ledger":
                    inputs.append(ledger_path(sid, op))
                outs = op_outputs(kind, sid, op)
                rel = "implements"
                n = Node(nid, sid, op_reads(i), inputs, outs, py + [nid], kind="tier_a",
                         edges=[(rel, o, f"{sid}#/operations/{i}") for o in outs])
                n.op = op
                out.append(n)
        for kind in (k for k in PER_SPEC if k in live):
            nid = f"{kind}:{sid}"
            inputs = [LANE_FILE, GEN_FILES[kind], EXTENSIONS] + [ledger_path(sid, op) for _, op in ops]
            if kind in ("insn", "qemu", "gas"):
                inputs += [o for _, op in ops for o in op_outputs(kind, sid, op)]
            outs = spec_outputs(kind, sid, root)
            n = Node(nid, sid, spec_reads(), inputs, outs, py + [nid], kind="tier_a",
                     edges=[("implements", o, f"{sid}#/operations") for o in outs])
            n.op = None
            out.append(n)
    return out


# ---------------------------------------------------------------- running one node
def digest(acc, reads) -> str:
    from repsynth.spec import canonical
    h = hashlib.sha256()
    for p in reads:
        try:
            v = acc(p)
        except Exception:
            v = None
        h.update(p.encode() + b"=" + hashlib.sha256(canonical(v)).hexdigest().encode() + b"\n")
    return h.hexdigest()


def write_if_changed(path: Path, text: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def load_entry(sid: str, op: str, root: Path = ROOT) -> dict:
    import yaml
    p = root / ledger_path(sid, op)
    if not p.exists():
        raise FileNotFoundError(f"no allocation for {sid}.{op}: run ledger:{sid}:{op} first ({p})")
    return yaml.safe_load(p.read_text())


def op_context(sid: str, i: int, nid: str, root: Path = ROOT) -> dict:
    from repsynth.accessor import Accessor
    spec = spec_of(sid, root)
    reads = op_reads(i)
    acc = Accessor(spec, reads, nid)
    opd = acc(f"/operations/{i}")
    try:
        enc = acc("/encoding/active")
    except Exception:
        enc = None
    return {"sid": acc("/identity/id"), "version": acc("/identity/version"), "index": i, "op": opd,
            "encoding": enc, "widths": acc("/domain/widths"), "tier_a": acc("/generation/tier_a"),
            "slice_sha256": digest(acc, reads), "reads": reads, "ext": extension(sid, root),
            "generator": f"repsynth.gen.{nid.split(':')[0]} {GENERATOR_VERSION}", "node": nid}


def spec_context(sid: str, nid: str, root: Path = ROOT) -> dict:
    from repsynth.accessor import Accessor
    spec = spec_of(sid, root)
    reads = spec_reads()
    acc = Accessor(spec, reads, nid)
    ops = acc("/operations")
    try:
        enc = acc("/encoding/active")
    except Exception:
        enc = None
    cands = [(i, o) for i, o in enumerate(ops) if o.get("candidate") is True]
    return {"sid": acc("/identity/id"), "version": acc("/identity/version"), "ops": cands, "encoding": enc,
            "widths": acc("/domain/widths"), "tier_a": acc("/generation/tier_a"),
            "slice_sha256": digest(acc, reads), "reads": reads, "ext": extension(sid, root),
            "entries": [load_entry(sid, o["name"], root) for _, o in cands],
            "generator": f"repsynth.gen.{nid.split(':')[0]} {GENERATOR_VERSION}", "node": nid}


def run_node(nid: str, root: Path = ROOT) -> list[str]:
    parts = nid.split(":")
    kind, sid = parts[0], parts[1]
    gen = module(kind, root)
    if len(parts) == 3:
        spec = spec_of(sid, root)
        i = [o["name"] for o in spec["operations"]].index(parts[2])
        ctx = op_context(sid, i, nid, root)
        if kind != "ledger":
            ctx["entry"] = load_entry(sid, parts[2], root)
        files = gen.render_op(ctx, root)
        expect = op_outputs(kind, sid, parts[2])
    else:
        ctx = spec_context(sid, nid, root)
        files = gen.render_spec(ctx, root)
        expect = spec_outputs(kind, sid, root)
    if sorted(files) != sorted(expect):
        raise RuntimeError(f"{nid} rendered {sorted(files)}, declared {sorted(expect)}")
    written = []
    for rel, text in files.items():
        if write_if_changed(root / rel, text):
            written.append(rel)
    return written


def gen_one(node_id: str, root: Path = ROOT) -> bool:
    kind = node_id.split(":")[0]
    if kind not in GEN_FILES or node_id.count(":") not in (1, 2):
        return False
    sid = node_id.split(":")[1]
    if sid not in tier_a_specs(root):
        return False
    run_node(node_id, root)
    return True


def generate_all(root: Path = ROOT, kinds=None) -> list[str]:
    """Runs every Tier A node in dependency order (ledger, per-op, per-spec), outside Ninja."""
    written = []
    ns = nodes(root)
    order = {"ledger": 0}
    for n in sorted(ns, key=lambda n: (order.get(n.id.split(":")[0], 1), n.op is None)):
        k = n.id.split(":")[0]
        if kinds and k not in kinds:
            continue
        written += run_node(n.id, root)
    return written
