# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Software lane (H3, GEN-02, P2.2): generated codec, native, WebAssembly and Python builds of the
reference functions with existing toolchains (gcc, clang with wasm-ld, cffi)."""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

from .accessor import Accessor
from .records import ROOT
from .numeric import SPECS, spec_of

CFLAGS = ["-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pedantic", "-fno-strict-aliasing"]


def _load_gen(name: str):
    p = ROOT / "gen" / "software" / f"{name}.py"
    s = importlib.util.spec_from_file_location(f"repsynth_gen_{name}", p)
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


def write_if_changed(path: Path, text: str) -> bool:
    """Write only when content changes (restat semantics, DEP-03)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == text:
        return False
    path.write_text(text, encoding="utf-8")
    return True


def gen_codec(root: Path = ROOT) -> tuple[Path, list[str], bool]:
    spec = spec_of("balanced_ternary", root)
    gen = _load_gen("codec")
    acc = Accessor(spec, gen.READS, gen.GENERATOR)
    text = gen.generate(acc)
    out = root / "spec" / "ref" / "balanced_ternary" / "bt_codec.h"
    return out, acc.reads, write_if_changed(out, text)


def run(cmd, cwd=None, log=None):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=cwd, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout, end="")
    if r.stderr:
        print(r.stderr, end="", file=sys.stderr)
    if r.returncode != 0:
        raise subprocess.CalledProcessError(r.returncode, cmd, r.stdout, r.stderr)
    return r


def sources(sid: str, root: Path = ROOT) -> list[Path]:
    return [root / s for s in spec_of(sid, root)["semantics"]["reference_sources"]]


def build_native(sid: str, root: Path = ROOT) -> Path:
    out = root / "out" / "software" / sid
    out.mkdir(parents=True, exist_ok=True)
    srcs = sources(sid, root)
    inc = srcs[0].parent
    so = out / f"lib{sid}.so"
    run(["gcc", *CFLAGS, "-fPIC", "-shared", f"-I{inc}", *srcs, "-o", so])
    obj = out / f"{sid}.o"
    run(["gcc", *CFLAGS, "-c", f"-I{inc}", *srcs, "-o", obj])
    return so


def build_wasm(sid: str, root: Path = ROOT) -> Path:
    out = root / "out" / "software" / sid
    out.mkdir(parents=True, exist_ok=True)
    srcs = sources(sid, root)
    inc = srcs[0].parent
    wasm = out / f"{sid}.wasm"
    run(["clang", "--target=wasm32", "-nostdlib", *CFLAGS, f"-I{inc}", "-Wl,--no-entry",
         "-Wl,--export-all", "-Wl,--strip-debug", *srcs, "-o", wasm])
    return wasm


def build_python(sid: str, root: Path = ROOT) -> Path:
    """cffi API-mode extension module exposing every reference function."""
    from cffi import FFI
    out = root / "out" / "software" / sid / "py"
    out.mkdir(parents=True, exist_ok=True)
    srcs = sources(sid, root)
    header = (srcs[0].with_suffix(".h")).read_text()
    decls = "\n".join(l for l in header.splitlines() if l.startswith("uint64_t "))
    ffi = FFI()
    ffi.cdef(decls)
    ffi.set_source(f"_rs_{sid}", f'#include "{srcs[0].with_suffix(".h").name}"',
                   sources=[str(s) for s in srcs], include_dirs=[str(srcs[0].parent)],
                   extra_compile_args=["-std=c11", "-O2"])
    lib = ffi.compile(tmpdir=str(out), verbose=False)
    return Path(lib)


def build_all(sid: str, root: Path = ROOT) -> dict:
    res = {}
    if sid == "balanced_ternary":
        res["codec"] = str(gen_codec(root)[0])
    res["native"] = str(build_native(sid, root))
    res["wasm"] = str(build_wasm(sid, root))
    res["python"] = str(build_python(sid, root))
    return res
