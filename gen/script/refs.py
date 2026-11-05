# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where the pinned script references live (P6.2), and their versions and hashes.

On a build machine the Ubuntu 24.04 packages are fetched with `apt-get download` and unpacked under
.cache/script/refs (nothing installed on the host); in the repsynth-script container the same package
versions are installed at /, and the CLDR JSON packages unpacked at /opt/cldr. A clone of the repository
made by the impact engine (.cache/tmp/d2) has no .cache of its own, so the cache of the repository it was
cloned from is used (the references are read only)."""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import subprocess
from functools import lru_cache
from pathlib import Path

# Pinned versions (Ubuntu 24.04 "noble" archive and the npm registry). The Dockerfile installs exactly these.
DEBS = {
    "unicode-data": "15.1.0-1",
    "fonts-noto-core": "20201225-2",
    "fonts-noto-cjk": "1:20230817+repack1-3",
    "libicu-dev": "74.2-1ubuntu3.1",
    "libharfbuzz-bin": "8.3.0-2build2",
    "libharfbuzz-cairo0": "8.3.0-2build2",
    "libchafa0t64": "1.14.0-1.1build1",
    "wasi-libc": "0.0~git20230113.4362b18-3",
    "libclang-rt-18-dev-wasm32": "1:18.1.3-1ubuntu1",
}
# Installed on the host already and used through their shared libraries (recorded, not downloaded).
HOST_DEBS = ("libicu74", "libharfbuzz0b", "libfreetype6", "clang-18", "lld-18", "flex", "libfl-dev", "nodejs")
NPM = {"cldr-misc-full": "44.1.0", "cldr-localenames-full": "44.1.0", "cldr-core": "44.1.0"}
PIP = {"fonttools": "4.55.3"}
ICU_SUFFIX = "_74"


def _origin_root(root: Path) -> Path | None:
    try:
        url = subprocess.run(["git", "-C", str(root), "config", "--get", "remote.origin.url"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return None
    p = Path(url) if url else None
    return p if p and p.is_dir() else None


def cache_root(root: Path) -> Path:
    env = os.environ.get("REPSYNTH_SCRIPT_CACHE")
    if env:
        return Path(env)
    own = root / ".cache" / "script"
    if (own / "refs").is_dir():
        return own
    o = _origin_root(root)
    if o and (o / ".cache" / "script" / "refs").is_dir():
        return o / ".cache" / "script"
    return own


def assets_root(root: Path) -> Path:
    own = root / ".cache" / "assets"
    if own.is_dir():
        return own
    o = _origin_root(root)
    if o and (o / ".cache" / "assets").is_dir():
        return o / ".cache" / "assets"
    return own


def prefix(root: Path) -> Path:
    """The file-system prefix holding the unpacked packages: .cache/script/refs here, / in the container."""
    p = cache_root(root) / "refs"
    return p if (p / "usr").is_dir() else Path("/")


def cldr_dir(root: Path) -> Path:
    p = cache_root(root) / "refs" / "cldr"
    return p if p.is_dir() else Path("/opt/cldr")


def ucd_dir(root: Path) -> Path:
    return prefix(root) / "usr/share/unicode"


def font_dirs(root: Path) -> list[Path]:
    pf = prefix(root)
    return [pf / "usr/share/fonts/truetype/noto", pf / "usr/share/fonts/opentype/noto"]


def tool_env(root: Path) -> dict:
    env = dict(os.environ)
    env["LANG"] = env["LC_ALL"] = "C.UTF-8"
    pf = prefix(root)
    if str(pf) != "/":
        lib = str(pf / "usr/lib/x86_64-linux-gnu")
        env["LD_LIBRARY_PATH"] = lib + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    return env


def hb_tool(root: Path, name: str) -> str:
    return str(prefix(root) / "usr/bin" / name)


def wasi_sysroot(root: Path) -> dict:
    pf = prefix(root)
    return {"include": pf / "usr/include/wasm32-wasi", "lib": pf / "usr/lib/wasm32-wasi",
            "builtins": pf / "usr/lib/llvm-18/lib/clang/18/lib/wasi/libclang_rt.builtins-wasm32.a"}


def apcisr_src(root: Path) -> Path:
    """The read-only clone of hindawiai/chintamani made at intake (P0.2)."""
    for cand in (assets_root(root) / "hindawiai__chintamani", cache_root(root) / "clones" / "hindawiai__chintamani"):
        if (cand / "APCISR" / "acii2csr.c").is_file():
            return cand
    raise FileNotFoundError("hindawiai/chintamani clone with APCISR/ not found under .cache/assets or .cache/script/clones")


def registry_tsv(root: Path) -> Path:
    """The ILM script registry as pinned in zistgah/tajziya (registry/ilm/scripts.tsv)."""
    for cand in (assets_root(root) / "zistgah__tajziya" / "registry/ilm/scripts.tsv",
                 cache_root(root) / "clones" / "zistgah__tajziya" / "registry/ilm/scripts.tsv"):
        if cand.is_file():
            return cand
    raise FileNotFoundError("zistgah/tajziya clone with registry/ilm/scripts.tsv not found")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@lru_cache(maxsize=None)
def icu_libs():
    uc = ctypes.CDLL("libicuuc.so.74")
    return uc


def icu_versions() -> dict:
    uc = icu_libs()
    buf = (ctypes.c_uint8 * 4)()
    getattr(uc, "u_getVersion" + ICU_SUFFIX)(buf)
    icu = ".".join(str(b) for b in buf[:3])
    getattr(uc, "u_getUnicodeVersion" + ICU_SUFFIX)(buf)
    uni = ".".join(str(b) for b in buf[:3])
    return {"icu": icu, "icu_unicode": uni}


def git_state(repo: Path) -> dict:
    def g(*a):
        return subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True).stdout.strip()
    return {"commit": g("rev-parse", "HEAD"), "tree": g("rev-parse", "HEAD^{tree}"),
            "status_clean": g("status", "--porcelain") == ""}


def json_dump(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
