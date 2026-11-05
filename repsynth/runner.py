# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""repsynth run --iteration N (CLI-01, CLI-03): runs the steps of ops/iterations/<N>.steps in order,
shows live progress, records every step, and resumes without repeating completed steps.

Step line format:  <container> | <command>     (blank lines and # comments ignored)
Native mode runs the command here; container mode runs it in the named kept container, with the
repository mounted at /work (sibling containers through the host's Docker socket)."""
from __future__ import annotations

import hashlib
import os
import shlex
import subprocess
import time
from pathlib import Path

from .records import ROOT, utc_now, write_record

STATE = ROOT / ".cache" / "run"


def steps_for(iteration: str, root: Path = ROOT) -> list[tuple[str, str]]:
    f = root / "ops" / "iterations" / f"{iteration}.steps"
    if not f.exists():
        raise FileNotFoundError(f"no steps file {f.relative_to(root)}")
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "|" not in line:
            raise ValueError(f"{f.name}: step needs '<container> | <command>': {line}")
        c, cmd = (x.strip() for x in line.split("|", 1))
        out.append((c, cmd))
    return out


def _key(i: int, c: str, cmd: str) -> str:
    return hashlib.sha256(f"{i}|{c}|{cmd}".encode()).hexdigest()[:16]


def run_iteration(iteration=None, milestone=None, native=False, resume=True, root: Path = ROOT) -> int:
    if milestone and not iteration:
        iteration = milestone
    if not iteration:
        raise SystemExit("give --iteration or --milestone")
    steps = steps_for(iteration, root)
    sdir = STATE / iteration
    sdir.mkdir(parents=True, exist_ok=True)
    log = root / "records" / "logs"
    log.mkdir(parents=True, exist_ok=True)
    host_root = os.environ.get("REPSYNTH_HOST_ROOT", str(root))
    failures = 0
    for i, (container, cmd) in enumerate(steps, 1):
        k = _key(i, container, cmd)
        marker = sdir / f"{i:03d}_{k}.done"
        remaining = len(steps) - i
        if resume and marker.exists():
            print(f"[{i}/{len(steps)}] already done, skipped: {cmd}", flush=True)
            continue
        print(f"[{i}/{len(steps)}] running ({remaining} after this) in {'this machine' if native else container}: {cmd}", flush=True)
        if native:
            full = ["bash", "-c", cmd]
        else:
            full = ["docker", "run", "--rm", "-v", f"{host_root}:/work", "-w", "/work",
                    "-v", "/var/run/docker.sock:/var/run/docker.sock", "-e", f"REPSYNTH_HOST_ROOT={host_root}",
                    container, "bash", "-c", cmd]
        t0, s0 = utc_now(), time.time()
        lf = log / f"{iteration}_{i:03d}.log"
        with open(lf, "w", encoding="utf-8") as fh:
            p = subprocess.Popen(full, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            for line in p.stdout:
                print("    " + line, end="", flush=True)
                fh.write(line)
            rc = p.wait()
        dt = time.time() - s0
        write_record(f"run-{iteration}", f"step{i:03d}", " ".join(shlex.quote(x) for x in full), rc, started_utc=t0,
                     outputs=[lf], results={"seconds": round(dt, 1), "container": container, "native": native},
                     state="done" if rc == 0 else "failed")
        print(f"[{i}/{len(steps)}] exit {rc} in {dt:.0f} s", flush=True)
        if rc == 0:
            marker.write_text(cmd + "\n")
        else:
            failures += 1   # lanes are independent: a failed step is reported and the run carries on
    subprocess.run([os.sys.executable, "-m", "repsynth", "report"], cwd=root)
    print(f"iteration {iteration}: {len(steps)} steps, {failures} failed. See RESUME.md and records/.")
    return 1 if failures else 0
