# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact-anchor patcher for the Tier B derived QEMU tree (P7.2).

  python3 gen/isb/patch.py --tree DERIVED_TREE [--dry-run] PATCHES.json

Every anchor must occur exactly once in its file. If an anchor occurs zero times or more than once, the
patcher stops before writing anything, names the file and the anchor, and exits 4. An insertion already
in place next to its anchor is skipped, so applying twice changes nothing. Copied files are written only
when their bytes differ. The patcher refuses a git work tree: patches go to a derived copy, never to the
pinned clone.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent


class AnchorMoved(Exception):
    pass


def plan(tree: Path, ps: dict, root: Path = ROOT):
    texts, log = {}, []
    for p in ps["anchors"]:
        f = tree / p["file"]
        if f not in texts:
            if not f.exists():
                raise AnchorMoved(f"{p['file']}: file not found (anchor {p['anchor']!r})")
            texts[f] = f.read_text(encoding="utf-8")
        t = texts[f]
        anchor, ins = p["anchor"], p["text"]
        done = (anchor + ins) if p["where"] == "after" else (ins + anchor)
        if done in t:
            log.append(f"present  {p['file']}: {ins.strip()}")
            continue
        n = t.count(anchor)
        if n != 1:
            raise AnchorMoved(f"{p['file']}: anchor {anchor!r} found {n} times (expected exactly once); "
                              "the pinned tree has moved, so nothing was written")
        texts[f] = t.replace(anchor, done)
        log.append(f"inserted {p['file']}: {ins.strip()}")
    copies = []
    for c in ps.get("copy", []):
        src = root / c["from"]
        for s in sorted(src.glob(c["pattern"])):
            if s.is_file():
                copies.append((s, tree / c["to"] / s.relative_to(src)))
    return texts, copies, log


def apply(tree: Path, patch_file: Path, dry_run: bool = False, root: Path = ROOT) -> list[str]:
    if (tree / ".git").exists():
        raise SystemExit(f"{tree} is a git work tree; patches go to a derived copy, never to a clone")
    texts, copies, log = plan(tree, json.loads(patch_file.read_text()), root)
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
            log.append(f"copied   {s.relative_to(root)} -> {d.relative_to(tree)}")
    return log


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tree", required=True)
    ap.add_argument("--root", default=str(ROOT))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("patches")
    a = ap.parse_args(argv)
    try:
        log = apply(Path(a.tree), Path(a.patches), a.dry_run, Path(a.root))
    except AnchorMoved as e:
        print(f"ANCHOR MOVED: {e}", file=sys.stderr)
        return 4
    for line in log:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
