# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""The Noto reference fonts (fonts-noto-core 20201225-2 and fonts-noto-cjk 1:20230817+repack1-3, P6.2):
an index of every face's character map, read with fontTools 4.55.3, and the choice of a reference face
for a script (the face covering most of the script's repertoire; ties go to Sans, Regular, then name)."""
from __future__ import annotations

import json
from pathlib import Path

from . import refs

# Explicit choices where SCR-05 names an orthography: Arabic is read in Urdu orthography (Nastaliq).
OVERRIDES = {"Arab": "NotoNastaliqUrdu-Regular.ttf"}


def ensure_fonttools(root: Path) -> None:
    """fontTools is pinned in the repsynth-script container; on a build machine it sits in .cache/script/venv."""
    import sys
    try:
        import fontTools  # noqa: F401
        return
    except ImportError:
        pass
    for sp in sorted((refs.cache_root(root) / "venv" / "lib").glob("python3*/site-packages")):
        sys.path.append(str(sp))


def _faces(path: Path):
    from fontTools.ttLib import TTFont, TTCollection
    if path.suffix.lower() == ".ttc":
        coll = TTCollection(str(path), lazy=True)
        for i, f in enumerate(coll.fonts):
            yield i, f
    else:
        yield 0, TTFont(str(path), lazy=True)


def build_index(root: Path) -> dict:
    ensure_fonttools(root)
    cache = refs.cache_root(root) / "font_index.json"
    files = sorted(p for d in refs.font_dirs(root) if d.is_dir() for p in d.iterdir() if p.suffix.lower() in (".ttf", ".otf", ".ttc"))
    key = [[str(p), p.stat().st_size] for p in files]
    if cache.exists():
        old = json.loads(cache.read_text())
        if old.get("key") == key:
            return old
    faces = []
    for p in files:
        if "-Bold" in p.name or "Italic" in p.name or "-Black" in p.name or "-Light" in p.name:
            continue
        for i, f in _faces(p):
            cmap = f.getBestCmap() or {}
            name = f["name"].getDebugName(4) or p.stem
            ranges, cps = [], sorted(cmap)
            for c in cps:
                if ranges and ranges[-1][1] == c - 1:
                    ranges[-1][1] = c
                else:
                    ranges.append([c, c])
            faces.append({"file": p.name, "path": str(p), "face": i, "name": name, "upem": f["head"].unitsPerEm, "ranges": ranges})
    idx = {"key": key, "faces": faces}
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(idx))
    return idx


def _covers(face, cps) -> int:
    import bisect
    starts = [r[0] for r in face["ranges"]]
    n = 0
    for c in cps:
        i = bisect.bisect_right(starts, c) - 1
        if i >= 0 and face["ranges"][i][1] >= c:
            n += 1
    return n


def choose(root: Path, script: str, cps: list[int]) -> dict | None:
    idx = build_index(root)
    if script in OVERRIDES:
        for f in idx["faces"]:
            if f["file"] == OVERRIDES[script]:
                return {**f, "covered": _covers(f, cps), "of": len(cps), "choice": "override (SCR-05 orthography)"}
    best, best_key = None, None
    for f in idx["faces"]:
        if f["file"].startswith("NotoColorEmoji"):
            continue
        n = _covers(f, cps)
        if n == 0:
            continue
        nm = f["name"]
        k = (-n, "Sans" not in nm, "Regular" not in nm and "regular" not in f["file"].lower(), "UI" in nm, ("SC" not in nm) if script == "Hani" else 0, len(nm), nm)
        if best_key is None or k < best_key:
            best, best_key = f, k
    if best is None:
        return None
    return {**best, "covered": _covers(best, cps), "of": len(cps), "choice": "largest coverage of the repertoire"}
