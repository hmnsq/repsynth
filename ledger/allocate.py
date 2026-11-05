# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""P4.1 allocation ledger (ISA-01, ISA-02, ISA-04).

Allocates R-type encodings in the RISC-V custom opcode space for every specification
operation marked `candidate: true`, and keeps them in ledger/allocations/<spec>/<op>.yaml, which are
under version control. An allocation, once written, is never moved: the allocator reads
the ledger first, keeps every entry exactly, and only appends entries for candidates
that have none.

Checks, run on every invocation over every entry:
  * against the RISC-V opcode database (riscv/riscv-opcodes, parsed by its own
    create_inst_dict): an overlap with a ratified standard instruction is REFUSED
    (exit 2); an overlap with an unratified one is reported;
  * against the vendor extensions the pinned binutils knows (opcodes/riscv-opc.c and
    include/opcode/riscv-opc.h): an overlap is REPORTED (vendor extensions share the
    custom space by design; the CPU property and -march select one at a time).
  * --previous LEDGER: every entry of the previous ledger must be present with the same
    encoding; a moved or dropped allocation is refused (exit 3).

Two patterns (match m, mask k) overlap when some 32-bit word satisfies both, that is
when ((m1 ^ m2) & k1 & k2) == 0.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from repsynth.spec import load_spec, spec_sha256  # noqa: E402

GENERATOR = "repsynth.ledger.allocate 0.3.0"
NOTICE = "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC0-1.0"
LEDGER = ROOT / "ledger" / "allocations"
EXTFILE = ROOT / "ledger" / "extensions.yaml"
REPORT = ROOT / "ledger" / "collisions.json"
OPCODES = ROOT / ".cache" / "riscv-opcodes"
BINUTILS = ROOT / ".cache" / "binutils-src" / "binutils-2.47"
SPECS = [ROOT / "spec" / "reps" / "numeric" / f"{s}.yaml" for s in ("balanced_ternary", "packed_decimal", "binary_integer")]

SPACES = {"custom-0": 0x0B, "custom-1": 0x2B}
# Extension name and mnemonic stem per specification (vendor prefix xaye, RD3).
EXTENSIONS = {"balanced_ternary": ("xayebt", "aye.bt"), "packed_decimal": ("xayepd", "aye.pd")}
R_MASK = 0xFE00707F            # funct7, funct3, opcode
RS2_MASK = 0x01F00000


def encode(opcode: int, funct3: int, funct7: int, unary: bool) -> tuple[int, int]:
    match = (funct7 << 25) | (funct3 << 12) | opcode
    mask = R_MASK | (RS2_MASK if unary else 0)
    return match, mask


def overlaps(m1: int, k1: int, m2: int, k2: int) -> bool:
    return ((m1 ^ m2) & k1 & k2) == 0


# ---------------------------------------------------------------- databases
def standard_db() -> list[dict]:
    """Ratified and unratified instructions from riscv-opcodes, through its own parser."""
    sys.path.insert(0, str(OPCODES / "src"))
    from riscv_opcodes.shared_utils import create_inst_dict  # type: ignore
    out = []
    for flt, ratified in ((["rv*"], True), (["unratified/rv*"], False)):
        try:
            d = create_inst_dict(flt, include_pseudo=True)
        except SystemExit:
            d = {}
        for name, v in d.items():
            out.append({"name": name, "match": int(v["match"], 16), "mask": int(v["mask"], 16),
                        "extension": v["extension"], "ratified": ratified})
    return out


def vendor_db() -> list[dict]:
    h = (BINUTILS / "include" / "opcode" / "riscv-opc.h").read_text()
    defs = {k: int(v, 0) for k, v in re.findall(r"#define\s+((?:MATCH|MASK)_\w+)\s+(0x[0-9a-fA-F]+|\d+)\s*$", h, re.M)}
    c = (BINUTILS / "opcodes" / "riscv-opc.c").read_text()
    out = []
    for name, xlen, cls, ma, mk in re.findall(
            r'\{"([\w.]+)",\s*(\d+),\s*(INSN_CLASS_X\w+),\s*"[^"]*",\s*(\w+),\s*(\w+),', c):
        if ma not in defs or mk not in defs:
            raise SystemExit(f"cannot resolve {ma} or {mk} for {name} in the pinned binutils")
        out.append({"name": name, "xlen": int(xlen), "class": cls, "match": defs[ma], "mask": defs[mk]})
    return out


def db_versions() -> dict:
    def head(p):
        r = subprocess.run(["git", "-C", str(p), "rev-parse", "HEAD"], capture_output=True, text=True)
        return r.stdout.strip()
    return {"riscv-opcodes": f"https://github.com/riscv/riscv-opcodes commit {head(OPCODES)}",
            "binutils": "binutils 2.47 release tarball (binutils_2.47.orig.tar.xz from archive.ubuntu.com, "
                        "sha256 154ab23b60070e8f27013c22977f1129425d67d1e8acd6e13010e617811e4cff); "
                        "github.com/bminor/binutils-gdb and hmnsq/binutils-gdb were not reachable"}


# ---------------------------------------------------------------- allocation
def tier_a_specs() -> list[tuple[str, dict]]:
    out = []
    for p in SPECS:
        s = load_spec(p)
        sid = s["identity"]["id"]
        if any(o.get("candidate") is True for o in s.get("operations", [])):
            if sid not in EXTENSIONS:
                raise SystemExit(f"{sid} has candidate operations but no extension name")
            out.append((sid, s))
    return out


def choose_funct3(space: int, n_ops: int, used: set, vendors: list[dict], standard: list[dict]) -> int:
    """The funct3 slot of the custom space whose first n_ops funct7 codes overlap the fewest
    vendor instructions (ties: lowest funct3), among slots not already used by this ledger."""
    best = None
    for f3 in range(8):
        if (space, f3) in used:
            continue
        pats = [encode(space, f3, f7, False) for f7 in range(n_ops)]
        if any(overlaps(m, k, s["match"], s["mask"]) for m, k in pats for s in standard if s["ratified"]):
            continue
        n = sum(1 for v in vendors if any(overlaps(m, k, v["match"], v["mask"]) for m, k in pats))
        if best is None or n < best[0]:
            best = (n, f3)
    if best is None:
        raise SystemExit(f"no free funct3 slot in opcode 0x{space:02x}")
    return best[1]


def init_extensions(path: Path, vendors, standard) -> list[str]:
    """Gives every Tier A specification an extension slot (opcode, funct3) once; never changes one."""
    data = yaml.safe_load(path.read_text()) if path.exists() else {"_notice": NOTICE, "generator": GENERATOR,
                                                                      "extensions": {}}
    exts = data["extensions"]
    used = {(e["opcode"], e["funct3"]) for e in exts.values()}
    added = []
    for sid, s in tier_a_specs():
        if sid in exts:
            continue
        space_name = s.get("generation", {}).get("tier_a", {}).get("opcode_space")
        if space_name not in SPACES:
            raise SystemExit(f"{sid}: generation.tier_a.opcode_space {space_name!r} is not a custom space")
        space = SPACES[space_name]
        n = sum(1 for o in s["operations"] if o.get("candidate") is True)
        f3 = choose_funct3(space, n, used, vendors, standard)
        used.add((space, f3))
        ext, stem = EXTENSIONS[sid]
        exts[sid] = {"extension": ext, "mnemonic_stem": stem, "cpu_property": f"x-{ext}",
                     "opcode_space": space_name, "opcode": space, "funct3": f3,
                     "funct7_rule": "the operation's index in the specification's operations list (operations are "
                                    "appended, never reordered); fixed once written"}
        added.append(sid)
    if added:
        path.write_text("# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.\n"
                        "# SPDX-License-Identifier: CC0-1.0\n"
                        "# Extension slots of the allocation ledger (ISA-04). Written once by ledger/allocate.py.\n"
                        + yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120), encoding="utf-8")
    return added


ENTRY_KEYS = ("spec", "op", "extension", "mnemonic", "format", "operands", "opcode_space", "opcode", "funct3",
              "funct7", "rs2", "match", "mask", "allocated_in")


def render_op(ctx: dict, root: Path = ROOT) -> dict:
    """Graph node ledger:<sid>:<op>. A new entry takes funct7 = the operation's index; an existing
    entry keeps every allocation field and only records the semantics slice hash it was checked with."""
    sid, op, i, ext = ctx["sid"], ctx["op"]["name"], ctx["index"], ctx["ext"]
    rel = f"ledger/allocations/{sid}/{op}.yaml"
    p = root / rel
    unary = ctx["op"]["arity"] == 1
    if p.exists():
        old = yaml.safe_load(p.read_text())
        entry = {k: old[k] for k in ENTRY_KEYS}
        if (entry["rs2"] == "zero") != unary:
            raise SystemExit(f"{rel}: the arity of {sid}.{op} changed; an allocation is never moved, "
                             "so this needs a new operation name")
    else:
        if i > 127:
            raise SystemExit(f"{sid}.{op}: operation index {i} exceeds funct7")
        m, k = encode(ext["opcode"], ext["funct3"], i, unary)
        entry = {"spec": sid, "op": op, "extension": ext["extension"],
                 "mnemonic": f"{ext['mnemonic_stem']}.{op.replace('_', '')}", "format": "R",
                 "operands": "rd, rs1" if unary else "rd, rs1, rs2", "opcode_space": ext["opcode_space"],
                 "opcode": ext["opcode"], "funct3": ext["funct3"], "funct7": i,
                 "rs2": "zero" if unary else "register", "match": f"0x{m:08x}", "mask": f"0x{k:08x}",
                 "allocated_in": ctx["version"]}
    entry["semantics_slice_sha256"] = ctx["slice_sha256"]
    entry["generator"] = GENERATOR
    head = ("# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.\n"
            "# SPDX-License-Identifier: CC0-1.0\n"
            "# Allocation ledger entry (ISA-04). The encoding fields are never moved once written; the slice\n"
            "# hash records the operation semantics (including the active encoding) last checked against it.\n")
    return {rel: head + yaml.safe_dump(entry, sort_keys=False, allow_unicode=True, width=120)}


def load_entries(ledger_dir: Path) -> list[dict]:
    return [yaml.safe_load(p.read_text()) for p in sorted(ledger_dir.glob("*/*.yaml"))]


def check(entries: list[dict], standard, vendors) -> tuple[list, list, list]:
    refused, reported_std, reported_vendor = [], [], []
    seen = {}
    for e in entries:
        m, k = int(e["match"], 16), int(e["mask"], 16)
        unary = e["rs2"] == "zero"
        if (m, k) != encode(e["opcode"], e["funct3"], e["funct7"], unary):
            refused.append(f"{e['mnemonic']}: match/mask disagree with its fields")
        for other, (m2, k2) in seen.items():
            if overlaps(m, k, m2, k2):
                refused.append(f"{e['mnemonic']}: overlaps ledger entry {other}")
        seen[e["mnemonic"]] = (m, k)
        for s in standard:
            if overlaps(m, k, s["match"], s["mask"]):
                if s["ratified"]:
                    refused.append(f"{e['mnemonic']}: collides with standard {s['name']} ({', '.join(s['extension'])})")
                else:
                    reported_std.append({"allocation": e["mnemonic"], "standard": s["name"],
                                         "extension": s["extension"]})
        for v in vendors:
            if overlaps(m, k, v["match"], v["mask"]):
                reported_vendor.append({"allocation": e["mnemonic"], "vendor": v["name"], "class": v["class"],
                                        "xlen": v["xlen"]})
    return refused, reported_std, reported_vendor


def compare_previous(prev: list[dict], cur: list[dict]) -> list[str]:
    now = {(e["spec"], e["op"]): e for e in cur}
    out = []
    for e in prev:
        n = now.get((e["spec"], e["op"]))
        if n is None:
            out.append(f"{e['mnemonic']}: allocation dropped")
            continue
        for k in ENTRY_KEYS:
            if e[k] != n[k]:
                out.append(f"{e['mnemonic']}: {k} moved from {e[k]} to {n[k]}")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ledger", default=str(LEDGER), help="directory of allocation entries")
    ap.add_argument("--report", default=str(REPORT))
    ap.add_argument("--previous", help="a previous ledger directory; a moved or dropped allocation is refused")
    ap.add_argument("--check-only", action="store_true", help="do not allocate; only check the entries")
    a = ap.parse_args(argv)
    standard, vendors = standard_db(), vendor_db()
    added = []
    if not a.check_only:
        added = init_extensions(EXTFILE, vendors, standard)
        sys.path.insert(0, str(ROOT))
        from repsynth.lanes import graph_tiera
        written = graph_tiera.generate_all(ROOT, kinds=("ledger",))
        added += written
    entries = load_entries(Path(a.ledger))
    refused, rep_std, rep_vendor = check(entries, standard, vendors)
    moved = compare_previous(load_entries(Path(a.previous)), entries) if a.previous else []
    report = {"_notice": NOTICE, "generator": GENERATOR, "databases": db_versions(),
              "standard_instructions": len(standard), "vendor_instructions": len(vendors),
              "entries": len(entries), "refused": refused, "moved": moved, "reported_unratified": rep_std,
              "reported_vendor": rep_vendor,
              "vendor_summary": sorted({f"{r['allocation']} ~ {r['class']}" for r in rep_vendor})}
    Path(a.report).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    for r in refused:
        print("REFUSED", r)
    for r in moved:
        print("MOVED", r)
    print(f"written {len(added)}; entries {len(entries)}; vendor overlaps reported {len(rep_vendor)} "
          f"({len(report['vendor_summary'])} allocation-class pairs); unratified overlaps {len(rep_std)}")
    if refused:
        return 2
    if moved:
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
