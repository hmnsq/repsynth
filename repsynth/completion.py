# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Completion reports (MRD section 13) for the spine's packets, composed from the packet's row in the
Build Plan, its status file and its run records, plus the implementer's notes in plan/notes/<packet>.yaml."""
from __future__ import annotations

import csv
import json
from pathlib import Path

import yaml

from .records import ROOT


def compose(packet: str, root: Path = ROOT) -> str:
    rows = {r["id"]: r for r in csv.DictReader(open(root / "plan/packets.csv", encoding="utf-8"))}
    r = rows[packet]
    st = json.loads((root / "reports/status" / f"{packet}.json").read_text()) if (root / "reports/status" / f"{packet}.json").exists() else {"state": "not_built", "evidence": [], "summary": ""}
    notes_p = root / "plan" / "notes" / f"{packet}.yaml"
    notes = yaml.safe_load(notes_p.read_text(encoding="utf-8")) if notes_p.exists() else {}
    recs = sorted((root / "records").glob(f"*_{packet}_*.json"))
    lines = [f"<!-- © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC-BY-SA-4.0 -->",
             f"# Completion report {packet}: {r['title']}", "",
             f"State: **{st['state']}**. {st.get('summary','')}", "",
             "## Intent, as written", "", f"Produces: {r['produces']}", "", f"Accepted when: {r['accepted_when']}", "",
             "## Commands run and exit codes", ""]
    for p in recs[-8:]:
        d = json.loads(p.read_text())
        lines.append(f"- `{d['command']}` exit {d['exit_code']} ({d['finished_utc']}), record `{p.relative_to(root)}`")
    if not recs:
        lines.append("- None recorded.")
    for key, title in (("produced", "What was produced"), ("not_done", "What was not done"),
                       ("failed_first", "The test shown failing before it passed"), ("reused", "What was reused"),
                       ("questions", "Questions for the author")):
        lines += ["", f"## {title}", ""]
        val = notes.get(key)
        if not val:
            lines.append("None recorded.")
        elif isinstance(val, list):
            lines += [f"- {v}" for v in val]
        else:
            lines.append(str(val))
    return "\n".join(lines) + "\n"


def write_all(packets, root: Path = ROOT):
    d = root / "reports" / "completion"
    d.mkdir(parents=True, exist_ok=True)
    for p in packets:
        (d / f"{p}.md").write_text(compose(p, root), encoding="utf-8")


if __name__ == "__main__":
    import sys
    write_all(sys.argv[1:])
