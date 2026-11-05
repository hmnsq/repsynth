# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""repsynth doctor (P0.1, CLI-04): timed, installs nothing on the host, reports what is missing;
doctor --build builds every container once and keeps it."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from .records import ROOT, utc_now, write_record, write_status


def containers(root: Path = ROOT) -> list[tuple[str, Path]]:
    return [(p.name.split("Dockerfile.", 1)[1], p) for p in sorted((root / "containers").glob("Dockerfile.*"))]


def _build_args() -> list[str]:
    """Optional proxy hook: only when the build machine sets a proxy (never on the author's machine)."""
    args = []
    for k in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "no_proxy", "NO_PROXY"):
        if os.environ.get(k):
            args += ["--build-arg", k]
    if args or os.environ.get("REPSYNTH_BUILD_NETWORK_HOST"):
        args += ["--network", "host"]
    return args


def _extra_ca(root: Path):
    src = os.environ.get("REPSYNTH_EXTRA_CA")
    if src and Path(src).is_file():
        shutil.copy(src, root / "containers" / "extra-ca" / "extra.crt")


def doctor(build: bool = False, root: Path = ROOT) -> int:
    t0, s0 = utc_now(), time.time()
    print("repsynth doctor: containers are built once and kept; nothing is installed on this machine.")
    docker = shutil.which("docker")
    rows, missing = [], []
    if not docker:
        print("MISSING docker: install Docker on this machine first; doctor installs nothing itself.")
        missing.append("docker")
    if build:
        _extra_ca(root)
    for name, df in containers(root):
        row = {"container": name, "dockerfile": str(df.relative_to(root))}
        if docker:
            insp = subprocess.run(["docker", "image", "inspect", name, "--format", "{{.Id}} {{.Size}}"], capture_output=True, text=True)
            if insp.returncode != 0 and build:
                b0 = time.time()
                ctx = root / "containers"
                r = subprocess.run(["docker", "build", *_build_args(), "-t", name, "-f", str(df), str(ctx)], capture_output=True, text=True)
                logf = root / "records" / "logs" / f"docker_build_{name}.log"
                logf.parent.mkdir(parents=True, exist_ok=True)
                logf.write_text(r.stdout + r.stderr)
                row["build_seconds"] = round(time.time() - b0, 1)
                row["build_exit"] = r.returncode
                row["build_log"] = str(logf.relative_to(root))
                insp = subprocess.run(["docker", "image", "inspect", name, "--format", "{{.Id}} {{.Size}}"], capture_output=True, text=True)
            if insp.returncode == 0:
                iid, size = insp.stdout.split()
                row.update(image_digest=iid, size_bytes=int(size), state="present")
            else:
                row["state"] = "not built"
                missing.append(name)
        else:
            row["state"] = "not established (no docker)"
        rows.append(row)
        print(f"  {name:22s} {row.get('state'):12s} {row.get('image_digest', '')[:19]} "
              f"{('build ' + str(row['build_seconds']) + ' s, exit ' + str(row['build_exit'])) if 'build_seconds' in row else ''}")
    dt = time.time() - s0
    print(f"doctor took {dt:.1f} s; missing: {', '.join(missing) or 'nothing'}")
    rc = 0 if not missing else 1
    rep = root / "reports" / "doctor.json"
    rep.write_text(json.dumps({"containers": rows, "missing": missing, "seconds": round(dt, 1)}, indent=2) + "\n")
    rec = write_record("P0.1", "doctor" + ("-build" if build else ""), "repsynth doctor" + (" --build" if build else ""), rc,
                       started_utc=t0, outputs=[rep], image_digests={r["container"]: r.get("image_digest", "absent") for r in rows},
                       results={"rows": rows}, state="done" if rc == 0 else "failed")
    return rc
