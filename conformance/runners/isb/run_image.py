# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boot a Tier B test image on its QEMU target and judge it (P7.4, T-27).

  python3 conformance/runners/isb/run_image.py --qemu QEMU_SYSTEM_BINARY --machine NAME-board IMAGE [--plugin SO]

The image's UART is QEMU's stdio. A run passes when QEMU exits 0 within the timeout, the UART shows
"ok machine", one "ok <op> <cases>" line per operation of the specification with the full case count, and
"PASS". Prints a JSON summary; exit 0 on pass, 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def run(qemu: str, machine: str, image: str, timeout: int = 120, plugin: str | None = None) -> dict:
    cmd = [qemu, "-M", machine, "-display", "none", "-serial", "stdio", "-monitor", "none", "-kernel", image]
    if plugin:
        cmd += ["-plugin", plugin, "-d", "plugin"]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        rc, out, err, to = p.returncode, p.stdout, p.stderr, False
    except subprocess.TimeoutExpired as e:
        rc, out, err, to = None, (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), \
            (e.stderr or b"").decode(errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or ""), True
    oks = {mm.group(1): int(mm.group(2)) for mm in re.finditer(r"^ok (\w+) (\d+)$", out, re.M)}
    return {"command": " ".join(cmd), "exit_code": rc, "timeout": to, "uart": out[-2000:], "stderr": err[-2000:],
            "ok_lines": oks, "machine_ok": "ok machine" in out, "pass_line": bool(re.search(r"^PASS$", out, re.M)),
            "fail_lines": re.findall(r"^FAIL .*$", out, re.M)}


def judge(res: dict, expected: dict) -> bool:
    """expected: {op: cases}."""
    return (res["exit_code"] == 0 and not res["timeout"] and res["machine_ok"] and res["pass_line"]
            and not res["fail_lines"] and res["ok_lines"] == expected)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qemu", required=True)
    ap.add_argument("--machine", required=True)
    ap.add_argument("--expect", help="JSON {op: cases}")
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("image")
    a = ap.parse_args(argv)
    r = run(a.qemu, a.machine, a.image, a.timeout)
    ok = judge(r, json.loads(Path(a.expect).read_text())) if a.expect else (r["exit_code"] == 0 and r["pass_line"])
    r["pass"] = ok
    print(json.dumps(r, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
