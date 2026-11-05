# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble and decode round trip against each specification's encodings (P7.3 acceptance).

  python3 conformance/runners/isb/asm_roundtrip.py [--root DIR] [NAME ...]

customasm assembles the generated roundtrip.asm with the generated instruction definition; every word of
the output must equal the word the specification's encoding gives (roundtrip.expect) and must decode,
through the specification's encoding table, to the instruction and fields it was written from. Out-of-range
operands must be refused by the assembler (a register r16, an immediate one past its field, a misaligned
branch). Exit 0 only when all of this holds.
"""
from __future__ import annotations

import argparse
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "gen" / "isb"))
import isa  # noqa: E402

CUSTOMASM = ROOT / ".cache/isb/customasm/bin/customasm"


def assemble(src: Path, out: Path) -> subprocess.CompletedProcess:
    return subprocess.run([str(CUSTOMASM), "-q", "--color=off", src.name, "-f", "binary", "-o", str(out)],
                          cwd=src.parent, capture_output=True, text=True)


def check(name: str, root: Path, work: Path) -> dict:
    m = isa.derive(name, root)
    d = root / f"gen/isb/targets/{name}"
    work.mkdir(parents=True, exist_ok=True)
    out = work / f"{name}_roundtrip.bin"
    r = assemble(d / "roundtrip.asm", out)
    res = {"assemble_exit": r.returncode, "stderr": r.stderr[-400:], "failures": []}
    if r.returncode != 0:
        res["ok"] = False
        return res
    data = out.read_bytes()
    words = [struct.unpack_from("<I", data, i)[0] for i in range(0, len(data), 4)]
    exp = [ln.split() for ln in (d / "roundtrip.expect").read_text().splitlines() if ln.strip()]
    if len(words) != len(exp):
        res["failures"].append(f"{len(words)} words assembled, {len(exp)} expected")
    for w, e in zip(words, exp):
        want = int(e[0], 16)
        fields = {k: int(v) for k, v in (x.split("=") for x in e[2:])}
        if w != want:
            res["failures"].append(f"{e[1]} {fields}: assembled {w:08x}, specification {want:08x}")
        dec = isa.decode(m, w)
        if dec != (e[1], fields):
            res["failures"].append(f"{w:08x} decodes to {dec}, written as {e[1]} {fields}")
    res["words"] = len(words)
    # refusals
    neg = {"register r16": "add r1, r16, r2" if any(i["name"] == "add" for i in m["instructions"]) else None,
           "immediate past its field": f"ld r1, {1 << 17}(r2)",
           "misaligned branch": "beq r1, r2, 0x2"}
    refused = {}
    for k, line in neg.items():
        src = work / f"{name}_neg.asm"
        src.write_text(f"#include \"{d / (name + '.cpu.asm')}\"\n#bank ram\n    {line}\n")
        rr = assemble(src, work / f"{name}_neg.bin")
        refused[k] = rr.returncode != 0
        if rr.returncode == 0:
            res["failures"].append(f"assembler accepted {line!r} ({k})")
    res["refusals"] = refused
    res["ok"] = not res["failures"]
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("names", nargs="*")
    a = ap.parse_args(argv)
    root = Path(a.root)
    ok = True
    for n in a.names or list(isa.instances(root)):
        r = check(n, root, ROOT / ".cache/isb/asm" / root.name)
        ok &= r["ok"]
        print(f"{n}: {'PASS' if r['ok'] else 'FAIL'} words={r.get('words')} refusals={r.get('refusals')} "
              f"failures={r['failures'][:10]} {r['stderr'] if not r['ok'] else ''}")
    print("ROUND TRIP HOLDS" if ok else "ROUND TRIP FAILURE")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
