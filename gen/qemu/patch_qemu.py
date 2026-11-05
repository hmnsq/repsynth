# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact-anchor patcher for the pinned QEMU tree (ISA-05, P4.2), also used for binutils (P4.5).

  python3 gen/qemu/patch_qemu.py --tree DERIVED_QEMU_TREE PATCHES.json [PATCHES.json ...]

Every anchor must occur exactly once in its file. If an anchor occurs zero times or more than once
the patcher stops before writing anything, names the file and the anchor, and exits 4. A patch whose
text is already in place next to its anchor is skipped, so applying twice changes nothing. Copied
files are written only when their bytes differ, so an incremental build recompiles only what changed.
The patcher never touches a pristine clone: it refuses a tree that is a git work tree.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class AnchorMoved(Exception):
    pass


def plan(tree: Path, patchsets: list[dict]) -> tuple[dict, list]:
    """Returns ({file: new text}, [(src, dst)]) or raises AnchorMoved."""
    texts: dict[Path, str] = {}
    log = []
    for ps in patchsets:
        for p in ps["anchors"]:
            f = tree / p["file"]
            if f not in texts:
                if not f.exists():
                    raise AnchorMoved(f"{p['file']}: file not found (anchor {p['anchor'].strip()!r})")
                texts[f] = f.read_text(encoding="utf-8")
            t = texts[f]
            anchor, ins = p["anchor"], p["text"]
            already = (anchor + ins) if p["where"] == "after" else (ins + anchor)
            if already in t or (ins in t and t.count(anchor) == 1):
                log.append(f"present {p['file']}: " + ins.strip().replace(chr(10), ' | '))
                continue
            n = t.count(anchor)
            if n != 1:
                raise AnchorMoved(f"{p['file']}: anchor {anchor.strip()!r} found {n} times (expected exactly once); "
                                  f"the pinned tree has moved, so nothing was written")
            t = t.replace(anchor, already)
            texts[f] = t
            log.append(f"inserted {p['file']}: " + ins.strip().replace(chr(10), ' | '))
    copies = []
    for ps in patchsets:
        for c in ps.get("copy", []):
            src = ROOT / c["from"]
            for s in sorted(src.glob(c["pattern"])):
                if s.is_file() and s.name not in c.get("exclude", []):
                    rel = s.relative_to(src)
                    if c.get("rename_prefix"):
                        rel = rel.with_name(c["rename_prefix"] + rel.name)
                    copies.append((s, tree / c["to"] / rel))
    return texts, copies, log


def apply(tree: Path, patch_files: list[Path], dry_run: bool = False) -> list[str]:
    if (tree / ".git").exists():
        raise SystemExit(f"{tree} is a git work tree; patches go to a derived copy, never to a clone")
    patchsets = [json.loads(Path(p).read_text()) for p in patch_files]
    texts, copies, log = plan(tree, patchsets)
    if dry_run:
        return log
    for f, t in texts.items():
        if f.read_text(encoding="utf-8") != t:
            f.write_text(t, encoding="utf-8")
    for s, d in copies:
        d.parent.mkdir(parents=True, exist_ok=True)
        data = s.read_bytes()
        if not d.exists() or d.read_bytes() != data:
            d.write_bytes(data)
            log.append(f"copied {s.relative_to(ROOT)} -> {d.relative_to(tree)}")
    return log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("patches", nargs="+")
    a = ap.parse_args(argv)
    try:
        log = apply(Path(a.tree), [Path(p) for p in a.patches], a.dry_run)
    except AnchorMoved as e:
        print(f"ANCHOR MOVED: {e}", file=sys.stderr)
        return 4
    for line in log:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
