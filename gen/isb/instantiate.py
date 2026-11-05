# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Instance specifications of the word machine family (P7.1).

  python3 gen/isb/instantiate.py [--check] [NAME ...]

Writes spec/reps/machine/<name>.yaml for every instance in the family's /generation/isb/instances, derived
from the family and the instance's numeric specification. With --check, writes nothing and exits 1 if a
written specification differs from its derivation (the instance_derivation property).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import isa  # noqa: E402


def render(name: str, root: Path = isa.ROOT) -> str:
    m = isa.derive(name, root)
    fam = isa.family(root)
    p = m["params"]
    num = m["numeric"]
    nid = num["identity"]["id"]
    rd = isa.ref_dir(name)
    insns = [{k: v for k, v in i.items() if k != "alu"} for i in m["instructions"]]
    ops = [{"name": f["name"], "arity": f["arity"],
            "meaning": (f"{f['meaning']}; calls {isa.num_sym(m, f['name'])} of {nid} unchanged"
                        if f["kind"] == "alu" else f["meaning"]),
            "reference": {"symbol_pattern": f"{name}_{f['name']}{{width}}"}, "candidate": False}
           for f in m["functions"]]
    spec = {
        "_notice": f"{isa.NOTICE} SPDX-License-Identifier: CC0-1.0",
        "identity": {"id": name, "version": fam["identity"]["version"], "family": "machine", "title": p["title"],
                     "equality": fam["identity"]["equality"], "canonical_form": fam["identity"]["canonical_form"]},
        "domain": {"description": (f"Machine states of {name}: sixteen {p['register_bits']}-bit registers holding "
                                   f"{nid} words of {p['digits']} digits, a byte-addressed memory and a program counter."),
                   "finite": True, "widths": [{"digits": p["digits"], "register_bits": p["register_bits"]}]},
        "structure": {"instance_of": fam["identity"]["id"],
                      "derived_from": {"family": isa.FAMILY_PATH, "family_sha256": m["family_sha256"],
                                       "numeric": isa.NUMERIC_PATHS[nid], "numeric_sha256": m["numeric_sha256"],
                                       "generator": f"repsynth.gen.isb.instantiate {isa.GENERATOR_VERSION}"},
                      "parameters": {"numeric": nid, "digits": p["digits"], "register_bits": p["register_bits"]},
                      "registers": fam["structure"]["registers"], "program_counter": fam["structure"]["program_counter"],
                      "memory": fam["structure"]["memory"], "data_encoding": num["encoding"]["active"]},
        "encoding": {"active": "fixed32", "encodings": {"fixed32": {
            "description": fam["encoding"]["encodings"]["fixed32"]["description"], "word_bits": m["word_bits"],
            "byte_order": "little", "formats": m["formats"], "instructions": insns}}},
        "decoding": fam["decoding"],
        "semantics": {"statement": fam["semantics"]["statement"],
                      "reference_sources": [f"{rd}/{name}.c"],
                      "oracle": f"The {nid} vectors (independent Python oracle, NUM-04) for the ALU functions; Python integers for the machine functions."},
        "operations": ops,
        "composition": fam["composition"],
        "transformations": [{"name": "assemble", "to": "customasm instruction definition", "preserves": "encodings"},
                            {"name": "translate", "to": "QEMU target", "preserves": "semantics through the reference functions"}],
        "constraints": fam["constraints"],
        "substrate": {"logical": "binary" if num["substrate"]["logical"] == "binary" else "ternary",
                      "register_widths": [{"digits": p["digits"], "register_bits": p["register_bits"]}]},
        "interfaces": fam["interfaces"],
        "verification": fam["verification"],
        "generation": {"isb": {"qemu_target": f"{name}-softmmu", "customasm": f"gen/isb/targets/{name}/{name}.cpu.asm",
                               "reference": rd}},
        "evolution": fam["evolution"],
        "provenance": {"oracle": {"value": f"{nid} vectors and Python integers", "evidence": "derived",
                                  "source": isa.NUMERIC_PATHS[nid]},
                       "extraction": f"Derived from {isa.FAMILY_PATH} by gen/isb/instantiate.py; do not edit.",
                       "evidence_state": "decided", "decided_by": fam["provenance"]["decided_by"]},
    }
    return yaml.safe_dump(spec, sort_keys=False, allow_unicode=True, width=120)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--root", default=str(isa.ROOT))
    ap.add_argument("names", nargs="*")
    a = ap.parse_args(argv)
    root = Path(a.root)
    names = a.names or list(isa.instances(root))
    bad = 0
    for n in names:
        text = render(n, root)
        p = root / isa.instance_path(n)
        if a.check:
            if not p.exists() or p.read_text(encoding="utf-8") != text:
                print(f"DIFFERS {p.relative_to(root)}: not equal to its derivation from the family")
                bad = 1
            else:
                print(f"equal {p.relative_to(root)}")
        elif not p.exists() or p.read_text(encoding="utf-8") != text:
            p.write_text(text, encoding="utf-8")
            print(f"wrote {p.relative_to(root)}")
    return bad


if __name__ == "__main__":
    sys.exit(main())
