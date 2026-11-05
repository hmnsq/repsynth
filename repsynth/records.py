# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run records (PRV-01) and packet status files (PRV-06)."""
from __future__ import annotations
import datetime as _dt
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATES = ("done", "wired_unproven", "not_built", "failed")


def utc_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_file(path: os.PathLike | str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_paths(paths) -> dict:
    out = {}
    for p in paths:
        p = Path(p)
        if p.is_dir():
            for q in sorted(p.rglob("*")):
                if q.is_file():
                    out[str(q.relative_to(ROOT) if q.is_relative_to(ROOT) else q)] = sha256_file(q)
        elif p.is_file():
            out[str(p.relative_to(ROOT) if p.is_relative_to(ROOT) else p)] = sha256_file(p)
        else:
            out[str(p)] = "absent"
    return out


def write_record(packet: str, step: str, command: str, exit_code: int, *, started_utc: str,
                 inputs=(), outputs=(), tool_versions=None, image_digests=None, results=None,
                 state: str = "wired_unproven", notes: str = "", root: Path = ROOT) -> Path:
    if state not in STATES:
        raise ValueError(f"state must be one of {STATES}, got {state!r}")
    rec = {
        "packet": packet, "step": step, "command": command, "exit_code": exit_code,
        "started_utc": started_utc, "finished_utc": utc_now(),
        "inputs": hash_paths(inputs), "outputs": hash_paths(outputs),
        "tool_versions": tool_versions or {}, "image_digests": image_digests or {},
        "results": results or {}, "state": state, "notes": notes,
    }
    d = root / "records"
    d.mkdir(parents=True, exist_ok=True)
    stamp = rec["finished_utc"].replace("-", "").replace(":", "")
    path = d / f"{stamp}_{packet}_{step}.json"
    path.write_text(json.dumps(rec, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    write_statement(rec, path, root)
    return path


def write_statement(rec: dict, record_path: Path, root: Path = ROOT) -> Path:
    """The run record as an in-toto Statement v1 (PRV-02). Timestamping (OpenTimestamps) and sealing are
    the author's acts on his machine, through Candor and Tok DOI."""
    subjects = [{"name": k, "digest": {"sha256": v}} for k, v in sorted(rec["outputs"].items()) if v != "absent"]
    subjects.append({"name": str(record_path.relative_to(root)), "digest": {"sha256": sha256_file(record_path)}})
    st = {"_type": "https://in-toto.io/Statement/v1", "subject": subjects,
          "predicateType": "https://hmnsq.github.io/repsynth/run-record/v1",
          "predicate": {k: rec[k] for k in ("packet", "step", "command", "exit_code", "started_utc", "finished_utc",
                                            "inputs", "tool_versions", "image_digests", "state")}}
    out = root / "records" / "attestations" / (record_path.stem + ".intoto.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(st, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    return out


def write_status(packet: str, state: str, evidence, summary: str, blocked_by=(), root: Path = ROOT) -> Path:
    if state not in STATES:
        raise ValueError(f"state must be one of {STATES}, got {state!r}")
    d = root / "reports" / "status"
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{packet}.json"
    path.write_text(json.dumps({"packet": packet, "state": state, "evidence": [str(e) for e in evidence],
                                "summary": summary, "blocked_by": list(blocked_by)},
                               indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path
