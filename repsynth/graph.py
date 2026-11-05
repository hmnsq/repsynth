# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Dependency and impact engine (H4): declared reads, slices, the Ninja file, the edge list and the
impact command (DEP-01 to DEP-04; packets P3.1 to P3.4).

A generator is a Node: an id, the specification it reads, its declared read paths, its file inputs
(other artefacts or sources) and its outputs. Slices are written only when their canonical content
changes; Ninja runs each generator with restat, so an unchanged output stops the cascade. Lanes add
their generators through LANES["graph-<lane>"] modules exposing nodes(root) -> list[Node]."""
from __future__ import annotations

import hashlib
import importlib
import json
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from .records import ROOT, sha256_file, utc_now, write_record
from .spec import canonical, load_spec, resolve, SpecError
from .numeric import SPECS, spec_of, vector_path, vector_reads

GRAPH = ROOT / "graph"
EDGE_TYPES = ("depends_on", "implements", "transforms", "preserves", "accelerates", "requires", "validates")


@dataclass
class Node:
    id: str
    spec: str | None
    reads: list[str]
    inputs: list[str]          # repository-relative files
    outputs: list[str]         # repository-relative files
    command: list[str]         # run from the repository root
    kind: str = "software"     # software | vectors | qemu | intrinsics | hardware | script | ...
    edges: list[tuple[str, str, str]] = field(default_factory=list)  # (type, from, to)


def _esc(ptr: str) -> str:
    return ptr.strip("/").replace("/", "~") or "_root"


def slice_file(spec_id: str, ptr: str, root: Path = ROOT) -> Path:
    return root / "graph" / "slices" / spec_id / f"{_esc(ptr)}.json"


def spec_path(spec_id: str, root: Path = ROOT) -> Path:
    if spec_id in SPECS:
        return root / SPECS[spec_id]["path"]
    for p in (root / "spec" / "reps").rglob("*.yaml"):
        try:
            if load_spec(p)["identity"]["id"] == spec_id:
                return p
        except Exception:
            continue
    raise KeyError(spec_id)


# ---------------------------------------------------------------- the software lane's generators


def software_nodes(root: Path = ROOT) -> list[Node]:
    py = [sys.executable, "-m", "repsynth", "gen-one"]
    nodes: list[Node] = []
    for sid in SPECS:
        spec = spec_of(sid, root)
        srcs = [s for s in spec["semantics"]["reference_sources"]]
        hdrs = [str(Path(s).with_suffix(".h")) for s in srcs]
        extra = []
        if sid == "balanced_ternary":
            codec = "spec/ref/balanced_ternary/bt_codec.h"
            nodes.append(Node(f"codec:{sid}", sid, ["/identity/id", "/identity/version", "/encoding/active", "/encoding/encodings"],
                              ["gen/software/codec.py"], [codec], py + [f"codec:{sid}"],
                              edges=[("implements", codec, f"{sid}#/encoding")]))
            extra = [codec]
        base = f"out/software/{sid}"
        so, wasm = f"{base}/lib{sid}.so", f"{base}/{sid}.wasm"
        pyglue = f"{base}/{sid}_glue.py"
        jsglue = f"{base}/{sid}.mjs"
        nodes.append(Node(f"native:{sid}", sid, ["/semantics/reference_sources"], srcs + hdrs + extra, [so], py + [f"native:{sid}"],
                          edges=[("implements", so, f"{sid}#/operations"), ("requires", so, "tool:gcc")]))
        nodes.append(Node(f"wasm:{sid}", sid, ["/semantics/reference_sources"], srcs + hdrs + extra, [wasm], py + [f"wasm:{sid}"],
                          edges=[("implements", wasm, f"{sid}#/operations"), ("requires", wasm, "tool:clang")]))
        nodes.append(Node(f"glue:{sid}", sid, ["/identity/id", "/operations", "/domain/widths"], [], [pyglue, jsglue], py + [f"glue:{sid}"],
                          edges=[("depends_on", jsglue, wasm), ("depends_on", pyglue, so),
                                 ("implements", jsglue, f"{sid}#/operations"), ("implements", pyglue, f"{sid}#/operations")]))
        for w in spec["domain"]["widths"]:
            for op in spec["operations"]:
                vec = str(vector_path(sid, op["name"], w["digits"], root).relative_to(root))
                nodes.append(Node(f"vectors:{sid}:{op['name']}:{w['digits']}", sid, vector_reads(spec, op), [so], [vec],
                                  py + [f"vectors:{sid}:{op['name']}:{w['digits']}"], kind="vectors",
                                  edges=[("validates", vec, f"{sid}#/operations/{op['name']}"), ("depends_on", vec, so)]))
    return nodes


def all_nodes(root: Path = ROOT) -> list[Node]:
    from .lanes import LANES, load_lane
    nodes = software_nodes(root)
    for name in sorted(LANES):
        if name.startswith("graph-"):
            m = load_lane(name)
            if m is None:
                continue
            try:
                nodes += m.nodes(root)
            except Exception as e:  # a lane that fails stops itself; the others carry on
                print(f"LANE ERROR {name}: nodes() raised {type(e).__name__}: {e}", file=sys.stderr)
    return nodes


# ---------------------------------------------------------------- generator execution (gen-one)


def gen_one(node_id: str, root: Path = ROOT) -> int:
    from . import software, numeric
    from .accessor import Accessor
    kind, _, rest = node_id.partition(":")
    if kind == "codec":
        software.gen_codec(root)
    elif kind == "native":
        _write_atomic_build(lambda: software.build_native(rest, root), root / f"out/software/{rest}/lib{rest}.so")
    elif kind == "wasm":
        _write_atomic_build(lambda: software.build_wasm(rest, root), root / f"out/software/{rest}/{rest}.wasm")
    elif kind == "glue":
        _gen_glue(rest, root)
    elif kind == "vectors":
        sid, opname, digits = rest.split(":")
        spec = spec_of(sid, root)
        op = next(o for o in spec["operations"] if o["name"] == opname)
        acc = Accessor(spec, vector_reads(spec, op), f"vectors:{sid}:{opname}")
        for p in vector_reads(spec, op):
            acc(p)
        ref = numeric.RefLib(sid, spec, root)
        software.write_if_changed(numeric.vector_path(sid, opname, int(digits), root),
                                  "\n".join(numeric.vector_lines(sid, spec, op, int(digits), ref)) + "\n")
    else:
        from .lanes import LANES, load_lane
        for name in LANES:
            if name.startswith("graph-"):
                m = load_lane(name)
                if m is not None and hasattr(m, "gen_one") and m.gen_one(node_id, root):
                    return 0
        raise KeyError(f"no generator {node_id}")
    return 0


def _write_atomic_build(build, out: Path):
    """Rebuild into place but keep the old file (and its mtime) when the bytes are identical (restat)."""
    old = out.read_bytes() if out.exists() else None
    tmp = out.with_suffix(out.suffix + ".prev")
    if old is not None:
        tmp.write_bytes(old)
    build()
    if old is not None and out.read_bytes() == old:
        out.unlink()
        tmp.rename(out)
    elif tmp.exists():
        tmp.unlink()


def _gen_glue(sid: str, root: Path):
    from . import software
    from .accessor import Accessor
    spec = spec_of(sid, root)
    acc = Accessor(spec, ["/identity/id", "/operations", "/domain/widths"], f"glue:{sid}")
    ops, widths = acc("/operations"), acc("/domain/widths")
    syms = [(o["name"], w["digits"], o["reference"]["symbol_pattern"].replace("{width}", str(w["digits"]))) for w in widths for o in ops]
    hdr = "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI."
    js = [f"// {hdr}", "// SPDX-License-Identifier: GPL-3.0-or-later",
          f"// Generated by repsynth.graph glue 0.3.0 for {acc('/identity/id')}. Do not edit.",
          f"export async function load(bytes) {{",
          "  const { instance } = await WebAssembly.instantiate(bytes, {});",
          "  const x = instance.exports;", "  const u = (v) => BigInt.asUintN(64, v);", "  return {"]
    js += [f"    {n}{d}: (a, b = 0n) => u(x.{s}(BigInt.asIntN(64, a), BigInt.asIntN(64, b)))," for n, d, s in syms]
    js += ["  };", "}", ""]
    py = [f"# {hdr}", "# SPDX-License-Identifier: GPL-3.0-or-later",
          f"# Generated by repsynth.graph glue 0.3.0 for {acc('/identity/id')}. Do not edit.",
          "import ctypes", "", "SYMBOLS = {"]
    py += [f"    {(n + str(d))!r}: {s!r}," for n, d, s in syms]
    py += ["}", "", "", "def load(path):", "    lib = ctypes.CDLL(path)", "    out = {}",
           "    for k, s in SYMBOLS.items():", "        f = getattr(lib, s)", "        f.restype = ctypes.c_uint64",
           "        f.argtypes = [ctypes.c_uint64, ctypes.c_uint64]", "        out[k] = f", "    return out", ""]
    base = root / "out" / "software" / sid
    software.write_if_changed(base / f"{sid}.mjs", "\n".join(js))
    software.write_if_changed(base / f"{sid}_glue.py", "\n".join(py))


# ---------------------------------------------------------------- slices, Ninja, edges (P3.2, P3.3)


def write_slices(nodes, root: Path = ROOT) -> list[Path]:
    changed = []
    cache: dict[str, dict] = {}
    for n in nodes:
        if not n.spec:
            continue
        spec = cache.setdefault(n.spec, load_spec(spec_path(n.spec, root)))
        for ptr in n.reads:
            f = slice_file(n.spec, ptr, root)
            try:
                text = canonical(resolve(spec, ptr)).decode() + "\n"
            except SpecError:
                text = "null\n"   # a path that does not exist yet is a slice whose value is absent
            f.parent.mkdir(parents=True, exist_ok=True)
            if not f.exists() or f.read_text() != text:
                f.write_text(text)
                changed.append(f)
    return changed


def write_ninja(nodes, root: Path = ROOT) -> Path:
    lines = ["# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.",
             "# SPDX-License-Identifier: GPL-3.0-or-later",
             "# Generated by repsynth.graph 0.3.0. Do not edit.",
             "ninja_required_version = 1.10", "",
             "rule gen", "  command = $cmd", "  description = $desc", "  restat = 1", ""]
    for n in nodes:
        ins = [str(slice_file(n.spec, p, root).relative_to(root)) for p in n.reads] if n.spec else []
        ins += n.inputs
        cmd = " ".join(shlex.quote(c) for c in n.command)
        lines.append(f"build {' '.join(_nesc(o) for o in n.outputs)}: gen {' '.join(_nesc(i) for i in ins)}")
        lines.append(f"  cmd = cd {shlex.quote(str(root))} && {cmd}")
        lines.append(f"  desc = {n.id}")
    path = root / "graph" / "build.ninja"
    text = "\n".join(lines) + "\n"
    if not path.exists() or path.read_text() != text:
        path.write_text(text)
    return path


def _nesc(p: str) -> str:
    return p.replace("$", "$$").replace(" ", "$ ").replace(":", "$:")


def write_edges(nodes, root: Path = ROOT) -> Path:
    edges = set()
    for n in nodes:
        for o in n.outputs:
            for p in n.reads:
                edges.add(("depends_on", o, f"{n.spec}#{p}"))
            for i in n.inputs:
                edges.add(("depends_on", o, i))
        for e in n.edges:
            if e[0] not in EDGE_TYPES:
                raise ValueError(f"unknown edge type {e[0]}")
            edges.add(e)
    path = root / "graph" / "edges.txt"
    head = ["# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC0-1.0",
            "# repsynth edge list 1: <type> <from> <to>; types: " + ", ".join(EDGE_TYPES)]
    path.write_text("\n".join(head + [" ".join(e) for e in sorted(edges)]) + "\n")
    _render(sorted(edges), root)
    return path


def _render(edges, root: Path):
    """A generated rendering (Graphviz DOT, regenerated from the edge list)."""
    lines = ["// Generated from graph/edges.txt by repsynth.graph 0.3.0. Do not edit.", "digraph repsynth {", "  rankdir=LR;"]
    for t, a, b in edges:
        lines.append(f'  "{a}" -> "{b}" [label="{t}"];')
    lines.append("}")
    (root / "graph" / "edges.dot").write_text("\n".join(lines) + "\n")


def check_edges(nodes, root: Path = ROOT) -> list[str]:
    """Every artefact has at least one implements or validates edge (P3.3)."""
    text = (root / "graph" / "edges.txt").read_text().splitlines()
    have = {l.split()[1] for l in text if l and not l.startswith("#") and l.split()[0] in ("implements", "validates")}
    missing = []
    for n in nodes:
        for o in n.outputs:
            if o not in have:
                # an artefact may be covered by an implements/validates edge of its producing node
                if not any(e[0] in ("implements", "validates") for e in n.edges):
                    missing.append(o)
    return missing


def build(targets=None, root: Path = ROOT, quiet=False) -> int:
    nodes = all_nodes(root)
    write_slices(nodes, root)
    write_ninja(nodes, root)
    write_edges(nodes, root)
    cmd = ["ninja", "-f", str(root / "graph" / "build.ninja"), "-C", str(root)] + list(targets or [])
    r = subprocess.run(cmd, capture_output=quiet, text=True)
    if quiet and r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:])
    return r.returncode


# ---------------------------------------------------------------- impact (P3.4)


def artefact_hashes(nodes, root: Path = ROOT) -> dict:
    out = {}
    for n in nodes:
        for o in n.outputs:
            p = root / o
            out[o] = sha256_file(p) if p.exists() else "absent"
    return out


def predict(nodes, changed_spec: dict, root: Path = ROOT) -> tuple[set, set]:
    """Artefacts whose declared slices change, and everything downstream of them through file inputs.
    Returns (predicted artefacts, conformance cells)."""
    sid = changed_spec["identity"]["id"]
    direct = set()
    for n in nodes:
        if n.spec != sid:
            continue
        for p in n.reads:
            f = slice_file(sid, p, root)
            try:
                new = canonical(resolve(changed_spec, p)).decode() + "\n"
            except SpecError:
                new = "null\n"
            if not f.exists() or f.read_text() != new:
                direct.add(n.id)
                break
    by_input: dict[str, list[Node]] = {}
    for n in nodes:
        for i in n.inputs:
            by_input.setdefault(i, []).append(n)
    produced = {n.id: n for n in nodes}
    pending, seen = list(direct), set(direct)
    while pending:
        n = produced[pending.pop()]
        for o in n.outputs:
            for d in by_input.get(o, []):
                if d.id not in seen and _content_sensitive(d):
                    seen.add(d.id)
                    pending.append(d.id)
    arts = {o for nid in seen for o in produced[nid].outputs}
    cells = {o for o in arts if o.endswith(".vec")}
    return arts, cells


def _content_sensitive(n: Node) -> bool:
    """Vector files are recomputed from the library but restat keeps them unchanged unless their
    values change; their prediction comes from their own slices, not from the library's rebuild."""
    return n.kind not in ("vectors",)


def impact(change: str, confirm: bool = False, root: Path = ROOT) -> int:
    from .impact_cases import resolve_change
    t0 = utc_now()
    case = resolve_change(change, root)
    nodes = all_nodes(root)
    build(root=root, quiet=True)
    before = artefact_hashes(nodes, root)
    with case.applied(root):
        new_spec = load_spec(spec_path(case.spec_id, root))
        nodes_new = all_nodes(root)
        predicted, cells = predict(nodes_new, new_spec, root)
        # source edits (new reference functions) predict the builds that take those sources
        for n in nodes_new:
            if any(i in case.changed_files for i in n.inputs):
                predicted |= set(n.outputs)
        print(f"impact of {case.name}: {len(predicted)} artefacts predicted")
        for a in sorted(predicted):
            print(f"  predicted {a}")
        if not confirm:
            return 0
        rc = build(root=root, quiet=True)
        after = artefact_hashes(nodes_new, root)
    observed = {a for a in set(before) | set(after) if before.get(a, "absent") != after.get(a, "absent")}
    expected = case.expected(nodes_new, root)
    ok = predicted == observed == expected
    result = {"case": case.name, "predicted": sorted(predicted), "observed": sorted(observed),
              "expected": sorted(expected), "predicted_minus_observed": sorted(predicted - observed),
              "observed_minus_predicted": sorted(observed - predicted),
              "expected_minus_observed": sorted(expected - observed),
              "observed_minus_expected": sorted(observed - expected), "build_exit": rc, "equal": ok}
    for k in ("predicted_minus_observed", "observed_minus_predicted", "expected_minus_observed", "observed_minus_expected"):
        if result[k]:
            print(f"  {k}: {result[k]}")
    # restore the baseline build
    build(root=root, quiet=True)
    restored = artefact_hashes(nodes, root)
    result["restored_equal_to_baseline"] = restored == before
    rep = root / "reports" / "impact" / f"{case.name}.json"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text(json.dumps(result, indent=2) + "\n")
    print(f"{case.name}: predicted={len(predicted)} observed={len(observed)} expected={len(expected)} equal={ok} "
          f"restored={result['restored_equal_to_baseline']}")
    write_record("P3.5", f"impact-{case.name}", f"repsynth impact {change} --confirm", 0 if ok else 1, started_utc=t0,
                 outputs=[rep], results={k: result[k] for k in ("equal", "restored_equal_to_baseline", "build_exit")},
                 state="done" if ok else "failed")
    return 0 if ok else 1
