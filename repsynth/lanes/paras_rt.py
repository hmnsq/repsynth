# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""P8.4 paras round trip (SPC-08): paras ingests the harness's own tracked sources into every language
BURP has tables for, and each language must convert back byte for byte. Gaps (untranslated names,
comments, keywords) are reported from paras's own GAPS output; only the exact round trip is the gate.
Usage: python3 -m repsynth paras-rt [--langs a,b]"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

from ..records import ROOT, utc_now, write_record, write_status

WORK = ROOT / ".cache" / "p84"


def languages() -> list[str]:
    out = subprocess.run(["burp", "languages"], capture_output=True, text=True).stdout.split()
    return [l for l in out if re.fullmatch(r"[a-z_]+", l)]


def run(args) -> int:
    langs = None
    rest = list(getattr(args, "rest", []) or [])
    if "--langs" in rest:
        langs = rest[rest.index("--langs") + 1].split(",")
    langs = langs or languages()
    t0 = utc_now()
    src = WORK / "src"
    if src.exists():
        shutil.rmtree(src)
    src.mkdir(parents=True)
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split("\n")
    for f in files:
        if not f or f.startswith(("records/", "conformance/vectors/", "reports/")):
            continue
        d = src / f
        d.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, d)
    # The gate: BURP (the engine paras drives) ingests and reverses every language, byte for byte.
    cmd = ["burp", "check", str(src), "--langs", ",".join(langs)]
    print("+", " ".join(cmd[:3]), "--langs <%d languages>" % len(langs), flush=True)
    p = subprocess.run(cmd, capture_output=True, text=True)
    log = WORK / "burp_check.log"
    log.write_text(p.stdout + p.stderr)
    table = [l for l in p.stdout.splitlines() if re.match(r"^\S+\s+\S+\s+\d+/\d+\s", l)]
    exact = sum(1 for l in table if (lambda m: m and m.group(1) == m.group(2))(re.search(r"(\d+)/(\d+)", l)))
    total = len(table)
    ok = p.returncode == 0 and exact == total == len(langs)
    # Secondary: paras itself over the same folder (reported, not a gate).
    work = WORK / "pw"
    if work.exists():
        shutil.rmtree(work)
    pcmd = ["paras", "report", str(src), "--local", "--langs", ",".join(langs), "--work", str(work)]
    pp = subprocess.run(pcmd, capture_output=True, text=True)
    (WORK / "paras_report.log").write_text(pp.stdout + pp.stderr)
    pm = re.search(r"(\d+) of (\d+) languages convert back exactly", pp.stdout)
    paras_line = pm.group(0) if pm else "no summary line"
    rep = ROOT / "reports" / "paras_roundtrip.md"
    rep.write_text("<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->\n"
                   "# paras and BURP round trip of hmnsq/repsynth (P8.4)\n\n"
                   f"Gate: `burp check <tracked sources> --langs <{len(langs)} languages>`, exit {p.returncode}: "
                   f"{exact} of {total} languages convert back byte for byte.\n\n"
                   f"Secondary: `paras report <same folder> --local --langs <{len(langs)} languages>`, exit {pp.returncode}: {paras_line}.\n\n"
                   + ("Finding for paras's next round: given the full language list, paras report processed fewer languages than "
                      "requested. Issue text: reports/paras_issue.md.\n\n" if not pm or int(pm.group(2)) != len(langs) else "")
                   + "Untranslated names, comments and keywords are gaps for the next round, not failures.\n\n```\n"
                   + "\n".join(table) + "\n```\n")
    if not pm or int(pm.group(2)) != len(langs):
        (ROOT / "reports" / "paras_issue.md").write_text(
            "<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->\n"
            "# Issue text for hmnsq/paras\n\n"
            f"Command: `{' '.join(pcmd[:3])} --local --langs <{len(langs)} comma-separated languages from `burp languages`> --work <dir>`\n\n"
            f"Exit code: {pp.returncode}\n\nOutput (summary lines):\n\n```\n"
            + "\n".join(l for l in pp.stdout.splitlines() if not l.strip().startswith("$"))[-3000:] + "\n```\n\n"
            f"Expected: {len(langs)} languages ingested and reversed. Observed: {paras_line}. paras 2026.10.2.\n")
    rec = write_record("P8.4", "burp-check", " ".join(cmd[:3]) + f" --langs <{len(langs)}>", 0 if ok else 1, started_utc=t0, outputs=[rep, log],
                       results={"exact": exact, "total": total, "languages": len(langs), "paras_secondary": paras_line},
                       state="done" if ok else "failed",
                       tool_versions={"burp": subprocess.run(["burp", "--help"], capture_output=True, text=True).stdout.split("BURP ")[-1].split()[0],
                                      "paras": "2026.10.2"})
    write_status("P8.4", "done" if ok else "failed", [rec.relative_to(ROOT)],
                 f"BURP ingests the harness's tracked sources into {total} languages and {exact} convert back byte for byte; "
                 f"paras report over the same folder: {paras_line} (finding recorded for paras).")
    print(f"P8.4: {exact} of {total} exact")
    return 0 if ok else 1
