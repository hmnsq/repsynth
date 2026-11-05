# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""repsynth command-line tool (H13, CLI-01). Subcommands: doctor, intake, spec, gen, vectors, impact,
run, conform, report, selftest, and the lanes registered in repsynth/lanes/__init__.py."""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

from . import NOTICE, __version__
from .records import ROOT


def _spec_check(args) -> int:
    from .spec import load_spec, check, SpecError
    rc = 0
    for p in args.paths:
        path = Path(p)
        try:
            errs = check(load_spec(path), path.resolve())
        except SpecError as e:
            errs = [e]
        if errs:
            rc = 1
            for e in errs:
                print(f"REFUSED {p} at {e.path}: {e.message}")
        else:
            print(f"VALID {p}")
    return rc


def _spec_hash(args) -> int:
    from .spec import load_spec, slice_hash, spec_sha256
    s = load_spec(args.path)
    print(slice_hash(s, args.pointer) if args.pointer else spec_sha256(s))
    return 0


def _vectors(args) -> int:
    from .conformance import generate_vectors
    return generate_vectors(args.spec)


def _conform(args) -> int:
    from .conformance import conform
    return conform(args.lane, args.spec)


def _gen(args) -> int:
    from .graph import build
    return build(args.targets)


def _impact(args) -> int:
    from .graph import impact
    return impact(args.change, confirm=args.confirm)


def _selftest(args) -> int:
    from .selftest import selftest
    return selftest(args.lane)


def _report(args) -> int:
    from .report import report
    return report()


def _run(args) -> int:
    from .runner import run_iteration
    return run_iteration(args.iteration, args.milestone, native=args.native, resume=not args.fresh)


def _doctor(args) -> int:
    from .doctor import doctor
    return doctor(build=args.build)


def _lane(name: str):
    def f(args) -> int:
        from .lanes import load_lane
        m = load_lane(name)
        if m is None:
            return 2
        return m.run(args)
    return f


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="repsynth", description="Representation synthesis harness.\n" + NOTICE,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version", version=f"repsynth {__version__}\n{NOTICE}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("doctor", help="timed check of containers and tools; installs nothing on the host")
    d.add_argument("--build", action="store_true", help="build the containers once")
    d.set_defaults(func=_doctor)

    sp = sub.add_parser("spec", help="specification store")
    ssub = sp.add_subparsers(dest="spec_cmd", required=True)
    c = ssub.add_parser("check", help="validate specifications (P1.1)")
    c.add_argument("paths", nargs="+")
    c.set_defaults(func=_spec_check)
    h = ssub.add_parser("hash", help="hash of a specification or of the slice at a JSON Pointer (P1.2)")
    h.add_argument("path")
    h.add_argument("pointer", nargs="?")
    h.set_defaults(func=_spec_hash)

    v = sub.add_parser("vectors", help="generate conformance vectors (P2.1)")
    v.add_argument("--spec", action="append", help="specification id (default: all numeric)")
    v.set_defaults(func=_vectors)

    g = sub.add_parser("gen", help="regenerate artefacts through the dependency graph (Ninja)")
    g.add_argument("targets", nargs="*")
    g.set_defaults(func=_gen)

    go = sub.add_parser("gen-one", help="run one generator node (called by Ninja)")
    go.add_argument("node")
    go.set_defaults(func=lambda a: __import__("repsynth.graph", fromlist=["gen_one"]).gen_one(a.node))

    i = sub.add_parser("impact", help="predict what a change regenerates (P3.4)")
    i.add_argument("change", help="a changed specification file, or one of the named DEP-05 changes")
    i.add_argument("--confirm", action="store_true", help="build afterwards and compare predicted with observed")
    i.set_defaults(func=_impact)

    cf = sub.add_parser("conform", help="run conformance on a lane (P2.3)")
    cf.add_argument("--lane", default="software")
    cf.add_argument("--spec", action="append")
    cf.set_defaults(func=_conform)

    st = sub.add_parser("selftest", help="mutation self-tests (CNF-04)")
    st.add_argument("--lane", default="all")
    st.set_defaults(func=_selftest)

    rp = sub.add_parser("report", help="regenerate RESUME.md and the status page from run records")
    rp.set_defaults(func=_report)

    r = sub.add_parser("run", help="run an iteration or milestone end to end, resumable")
    r.add_argument("--iteration")
    r.add_argument("--milestone")
    r.add_argument("--native", action="store_true", help="run on this machine instead of in the containers")
    r.add_argument("--fresh", action="store_true", help="ignore completed stages")
    r.set_defaults(func=_run)

    from .lanes import LANES
    for name in sorted(LANES):
        if name.startswith(("graph-", "selftest-", "conform-")):
            continue
        lp = sub.add_parser(name, help=f"lane {name}")
        lp.add_argument("rest", nargs=argparse.REMAINDER)
        lp.set_defaults(func=_lane(name))

    args = ap.parse_args(argv)
    return args.func(args)
