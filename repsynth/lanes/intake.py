# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Intake lane: host profile (P0.6), intake of the author's work (P0.2),
licence intake (P0.4) and received material (P0.5).

Subcommands (python3 -m repsynth intake <sub> ...):
  host       measure memory, processors, disk and container storage (P0.6)
  clone      shallow pinned clones of the assets of MRD section 7.1 (P0.2)
  names      check the proposed repository names for collisions (P0.2)
  locate     search cloned trees for the received-only assets (P0.2)
  licences   record SPDX identifiers from each tool's own licence file (P0.4)
  received   hash, clean and report received documents (P0.5)
  selftest   show each check refusing a planted defect
  all        host, clone, names, locate, licences, received in order

Nothing here writes a credential. On the author's machine the GitHub CLI
login is handed in through the environment (GH_TOKEN) or the gh config
directory mounted read-only; git is given the token through a credential
helper that reads it from the environment at call time, so it never lands
in a file, a log or a record.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

from repsynth.records import ROOT, sha256_file, utc_now, write_record, write_status

NOTICE = "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI."
VERSION = "0.3.0"
CACHE = ROOT / ".cache"
ASSETS = CACHE / "assets"
LOGS = CACHE / "logs"
TMP = CACHE / "tmp"
REPORTS = ROOT / "reports"

# Words that must not reach a report (a proxy's exclusion list may carry vendor host names).
_SECRET_RX = re.compile(r"(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|x-access-token:[A-Za-z0-9_]{20,})")


# Product names of the build host's tooling that may appear in a proxy's refusal message, and
# names of language-model products that appear in some of the author's file names: none may
# reach this repository's tree (sprint contract rule 7), so they are masked in every output.
_HOST_RX = re.compile(r"(?i)\b(claude(?:[ -]code)?|anthropic)\b[\w./-]*")
_MODEL_RX = re.compile(r"(?i)(chat-?gpt|\bgpt\b|gpt-?\d|gemini|grok|claude|anthropic|openai|copilot|ai-generated)")


def redact(text: str) -> str:
    """Remove anything shaped like a GitHub token, and the build host's own product names
    (a proxy may name them in a refusal), from every captured output."""
    return _MODEL_RX.sub("[model-name]", _HOST_RX.sub("[build-host]", _SECRET_RX.sub("[redacted]", text or "")))


def scrub(obj):
    """Apply redact() to every string inside a JSON-like object (keys included)."""
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {scrub(k): scrub(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [scrub(x) for x in obj]
    return obj


def record(packet: str, step: str, command: str, exit_code: int, **kw) -> Path:
    """write_record with every string scrubbed first."""
    for k in ("results", "notes", "tool_versions"):
        if k in kw:
            kw[k] = scrub(kw[k])
    return write_record(packet, step, redact(command), exit_code, **kw)


def _env_for_git() -> dict:
    """Environment for git: never prompt; if GH_TOKEN or GITHUB_TOKEN is present, pass it through
    a credential helper that reads the variable when git asks, so nothing is written to disk."""
    env = dict(os.environ)
    env["GIT_TERMINAL_PROMPT"] = "0"
    env.setdefault("GIT_ASKPASS", "true")
    return env


def _git_auth_args() -> list[str]:
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        helper = ('!f() { test "$1" = get || exit 0; echo username=x-access-token; '
                  'echo "password=${GH_TOKEN:-$GITHUB_TOKEN}"; }; f')
        return ["-c", "credential.helper=", "-c", f"credential.helper={helper}"]
    return []


def run_cmd(cmd: list[str], *, cwd: Path | None = None, env: dict | None = None,
            timeout: int = 900, log_name: str | None = None) -> dict:
    """Run a command, capture everything, keep a full log under .cache/logs, return a summary."""
    started = utc_now()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                           timeout=timeout, errors="replace")
        code, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        code, out, err = 124, (e.stdout or b"").decode("utf-8", "replace") if isinstance(e.stdout, bytes) else (e.stdout or ""), f"timeout after {timeout} s"
    except FileNotFoundError as e:
        code, out, err = 127, "", str(e)
    out, err = redact(out), redact(err)
    shown = " ".join(redact(c) for c in cmd if not c.startswith("credential.helper=!"))
    res = {"command": shown, "cwd": str(cwd) if cwd else str(Path.cwd()), "exit_code": code,
           "started_utc": started, "finished_utc": utc_now(), "stdout": out, "stderr": err}
    if log_name:
        LOGS.mkdir(parents=True, exist_ok=True)
        (LOGS / f"{log_name}.log").write_text(
            f"$ {shown}\n# cwd {res['cwd']}\n# exit {code}\n--- stdout\n{out}\n--- stderr\n{err}\n",
            encoding="utf-8")
    return res


def tail(text: str, n: int = 20) -> str:
    lines = (text or "").rstrip("\n").splitlines()
    return "\n".join(lines[-n:])


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(text), encoding="utf-8")


def _write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    obj = scrub(obj)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n", encoding="utf-8")


def _tool_version(cmd: list[str]) -> str:
    r = run_cmd(cmd, timeout=30)
    return (r["stdout"] or r["stderr"]).strip().splitlines()[0] if r["exit_code"] == 0 and (r["stdout"] or r["stderr"]).strip() else f"unavailable (exit {r['exit_code']})"


# --------------------------------------------------------------------------------------------
# P0.6 host profile
# --------------------------------------------------------------------------------------------

def _meminfo() -> dict:
    out = {}
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, v = line.split(":", 1)
            parts = v.split()
            out[k] = int(parts[0]) * (1024 if len(parts) > 1 and parts[1] == "kB" else 1)
    except OSError:
        pass
    return out


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def _cpu_model() -> str:
    txt = _read("/proc/cpuinfo") or ""
    for line in txt.splitlines():
        if line.lower().startswith("model name"):
            return line.split(":", 1)[1].strip()
    return platform.processor() or "not established: /proc/cpuinfo has no model name"


def _docker_storage() -> dict:
    fmt = "{{json .DockerRootDir}}|{{json .Driver}}|{{json .ServerVersion}}|{{json .NCPU}}|{{json .MemTotal}}|{{json .Images}}"
    r = run_cmd(["docker", "info", "--format", fmt], timeout=60)
    res = {"docker_info": {"command": r["command"], "exit_code": r["exit_code"]}}
    if r["exit_code"] != 0:
        res["docker_info"]["stderr_tail"] = tail(r["stderr"], 5)
        res["state"] = "not established: docker info failed"
        return res
    root, driver, ver, ncpu, mem, images = [json.loads(x) for x in r["stdout"].strip().split("|")]
    res.update({"docker_root_dir": root, "storage_driver": driver, "server_version": ver,
                "docker_ncpu": ncpu, "docker_mem_total_bytes": mem, "images": images})
    du = run_cmd(["docker", "system", "df", "--format", "{{json .}}"], timeout=120)
    res["docker_system_df"] = {"command": du["command"], "exit_code": du["exit_code"],
                               "rows": [json.loads(l) for l in du["stdout"].splitlines() if l.strip().startswith("{")]}
    try:
        u = shutil.disk_usage(root)
        res["docker_root_filesystem"] = {"path": root, "total_bytes": u.total, "free_bytes": u.free}
    except OSError as e:
        res["docker_root_filesystem"] = {"path": root, "state": f"not established: {e}"}
    return res


GIB = 1024 ** 3
RECORDED_MEMORY_GB = {"author_record": 16, "R2": 32}


def settle_rd4(mem_total_bytes: int, role: str) -> dict:
    """RD4 is settled only by a run on the reference unit. MemTotal is below the installed
    capacity (firmware and integrated graphics reserve some), so the measured figure is
    compared with each recorded capacity: consistent when it lies within (0.85 x capacity,
    capacity]."""
    gib = mem_total_bytes / GIB
    consistent = [k for k, gb in RECORDED_MEMORY_GB.items() if 0.85 * gb < gib <= gb * 1.0001]
    if role != "reference-unit":
        return {"state": "awaiting the author's run on the reference unit",
                "measured_here_gib": round(gib, 2), "machine": role,
                "note": "This figure is the machine the run happened on, not the reference unit; it does not settle RD4."}
    if len(consistent) == 1:
        return {"state": "measured", "measured_gib": round(gib, 2), "consistent_with": consistent[0],
                "settled_value_gb": RECORDED_MEMORY_GB[consistent[0]]}
    return {"state": "measured", "measured_gib": round(gib, 2), "consistent_with": consistent,
            "settled_value_gb": "not established: the measured figure matches neither recorded capacity alone; "
                                "the measured MemTotal stands as the figure"}


def host_profile(role: str) -> dict:
    mi = _meminfo()
    try:
        affinity = len(os.sched_getaffinity(0))
    except AttributeError:
        affinity = None
    disk = shutil.disk_usage(ROOT)
    cg_mem = _read("/sys/fs/cgroup/memory.max") or _read("/sys/fs/cgroup/memory/memory.limit_in_bytes")
    cg_cpu = _read("/sys/fs/cgroup/cpu.max")
    prof = {
        "_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0",
        "generator": f"repsynth.lanes.intake {VERSION}",
        "machine_role": role,
        "label": ("Measured on the reference unit; this run settles RD4." if role == "reference-unit" else
                  "Measured on the cloud build machine used for this iteration. It is NOT the reference unit."
                  if role == "cloud-build-machine" else
                  "Measured on a machine whose processor is not the reference unit's. It does not settle RD4."),
        "memory": {"source": "/proc/meminfo",
                   "mem_total_bytes": mi.get("MemTotal"), "mem_available_bytes": mi.get("MemAvailable"),
                   "swap_total_bytes": mi.get("SwapTotal"),
                   "mem_total_gib": round(mi.get("MemTotal", 0) / GIB, 2),
                   "cgroup_memory_limit": cg_mem or "none found"},
        "processors": {"os_cpu_count": os.cpu_count(), "usable_by_this_process": affinity,
                       "model": _cpu_model(), "cgroup_cpu_max": cg_cpu or "none found",
                       "machine": platform.machine()},
        "disk": {"path": str(ROOT), "total_bytes": disk.total, "used_bytes": disk.used,
                 "free_bytes": disk.free, "free_gib": round(disk.free / GIB, 2)},
        "os": {"system": platform.system(), "release": platform.release(),
               "pretty_name": (dict(l.split("=", 1) for l in (_read("/etc/os-release") or "").splitlines() if "=" in l)
                               .get("PRETTY_NAME", "not established").strip('"'))},
        "container_storage": _docker_storage(),
    }
    prof["rd4"] = settle_rd4(prof["memory"]["mem_total_bytes"] or 0, role)
    # Parallelism the build may use (TCH-03): leave one processor and 2 GiB per job.
    avail = prof["memory"]["mem_available_bytes"] or 0
    prof["derived"] = {"max_jobs": max(1, min((affinity or 1) - 1, int(avail // (2 * GIB)))),
                       "rule": "min(processors - 1, available memory / 2 GiB), at least 1"}
    return prof


def _host_md(profiles: dict) -> str:
    lines = [f"<!-- {NOTICE} SPDX-License-Identifier: CC-BY-SA-4.0 -->", "", "# Host profile (P0.6)", "",
             NOTICE, "",
             "Generated by `python3 -m repsynth intake host`. Each machine's figures are kept in its own file.", ""]
    for role, p in sorted(profiles.items()):
        m, c, d = p["memory"], p["processors"], p["disk"]
        cs = p["container_storage"]
        lines += [f"## {role}", "", p["label"], "",
                  "| Quantity | Value | Source |", "|---|---|---|",
                  f"| Memory (MemTotal) | {m['mem_total_bytes']} bytes ({m['mem_total_gib']} GiB) | /proc/meminfo |",
                  f"| Memory available | {m['mem_available_bytes']} bytes | /proc/meminfo |",
                  f"| Processors | {c['os_cpu_count']} reported, {c['usable_by_this_process']} usable | os.cpu_count, sched_getaffinity |",
                  f"| Processor model | {c['model']} | /proc/cpuinfo |",
                  f"| Free disk at the work tree | {d['free_bytes']} bytes ({d['free_gib']} GiB) | statvfs |",
                  f"| Container storage | {cs.get('storage_driver', cs.get('state'))} at {cs.get('docker_root_dir', '')}, "
                  f"{cs.get('images', '')} images | docker info, docker system df |",
                  f"| RD4 | {p['rd4']['state']} | settle_rd4 |", ""]
    return "\n".join(lines) + "\n"


REFERENCE_CPU = "7445HS"  # MRD 7.2: the reference unit's AMD Ryzen 7 7445HS


def detect_role() -> str:
    """The reference unit is recognised by its processor model (MRD 7.2), so the author's own run
    settles RD4 with no flag; any other machine is labelled as not the reference unit."""
    return "reference-unit" if REFERENCE_CPU in _cpu_model() else "not-reference-unit"


def cmd_host(args) -> int:
    started = utc_now()
    role = args.role or os.environ.get("REPSYNTH_MACHINE_ROLE") or detect_role()
    prof = host_profile(role)
    out = REPORTS / f"host.{role}.json"
    _write_json(out, prof)
    profiles = {}
    for f in sorted(REPORTS.glob("host.*.json")):
        profiles[json.loads(f.read_text())["machine_role"]] = json.loads(f.read_text())
    md = REPORTS / "host.md"
    _write_text(md, _host_md(profiles))
    ok = prof["memory"]["mem_total_bytes"] and prof["processors"]["os_cpu_count"] and prof["disk"]["free_bytes"]
    rec = record("P0.6", f"host_{role}", f"python3 -m repsynth intake host --role {role}", 0 if ok else 1,
                       started_utc=started, outputs=[out, md],
                       tool_versions={"python": platform.python_version(),
                                      "docker": prof["container_storage"].get("server_version", "unavailable")},
                       results={"mem_total_bytes": prof["memory"]["mem_total_bytes"],
                                "processors": prof["processors"]["os_cpu_count"],
                                "free_disk_bytes": prof["disk"]["free_bytes"], "rd4": prof["rd4"]},
                       state="done" if (ok and role == "reference-unit") else "wired_unproven",
                       notes=prof["label"])
    print(json.dumps({"host_profile": str(out), "record": str(rec), "rd4": prof["rd4"]}, indent=2))
    return 0 if ok else 1


# --------------------------------------------------------------------------------------------
# P0.2 intake of the author's work
# --------------------------------------------------------------------------------------------

ORGS = ["hindawiai", "project-ilm", "zistgah", "hmnsq", "ayevdi"]
# Further owners named in the author's own estate lists (Hindawi 2026.10,
# work-packages/estate-inventory.json and estate-repositories.json) and in Hindawi's change log.
ORGS_FROM_ESTATE = ["ayeai", "ayecnse", "ayehandsum", "pvjournal", "kaivalyik", "c-polis"]
ALL_ORGS = ORGS + ORGS_FROM_ESTATE
ESTATE_FILES = ("work-packages/estate-repositories.json", "work-packages/estate-inventory.json")


def _across(names, orgs=None):
    return [f"{o}/{n}" for o in (orgs or ALL_ORGS) for n in names]


# Rows of MRD section 7.1 (and section 8's provenance tools), each with the repositories tried.
# "search" terms are looked for, case-insensitively, in every cloned tree by `locate`.
ASSET_ROWS = [
    {"asset": "Hindawi 2026.10", "candidates": ["hindawiai/hindawi2026.10"], "relationship": "oracle"},
    {"asset": "chintamani (Romenagri and APCISR folders)", "candidates": ["hindawiai/chintamani"], "relationship": "oracle"},
    {"asset": "Romenagri 2026.10", "candidates": ["project-ilm/romenagri2026.10"], "relationship": "oracle"},
    {"asset": "Romenagri (project-ilm/romenagri, named in the estate list)", "candidates": ["project-ilm/romenagri"],
     "relationship": "recorded; the 2026.10 release is the oracle"},
    {"asset": "AyeHandSum", "candidates": ["ayehandsum/ayehandsum", "project-ilm/scripts"] + _across(["ayehandsum", "ayesha", "aye-hand-sum", "aye-handsum", "ayecode",
                                                   "ayehandsum2026.10", "ayesha2026.10"]),
     "relationship": "oracle once located", "search": ["ayehandsum", "aye hand sum", "ayesha", "ayecode"],
     "name_terms": ["handsum", "ayesha", "ayecode"]},
    {"asset": "Machine-stack explainer", "candidates": _across(["machine-stack", "machinestack", "machine-stack-explainer",
                                                                "stack-explainer", "explainer"]),
     "relationship": "located at intake", "search": ["machine-stack", "machine stack", "stack explainer", "explainer site"],
     "name_terms": ["explainer", "machine", "stack", "trace"],
     "probe": {"hindawiai/hindawi2026.10": ["docs/trace/index.html", "docs/trace/machine.html"]},
     "evidence_grep": {"hindawiai/hindawi2026.10": ["docs/trace/ is the explainer site", "docs/trace/machine.html follows"]}},
    {"asset": "APCISR WebAssembly trace", "candidates": [], "relationship": "located at intake",
     "search": ["apcisr.wasm", "webassembly", "wasm"], "search_scope": ["hindawiai/chintamani", "hindawiai/hindawi2026.10"],
     "probe": {"hindawiai/hindawi2026.10": ["docs/trace/apcisr/src", "docs/trace/apcisr.js", "docs/trace/apcisr-data.js"]},
     "evidence_grep": {"hindawiai/hindawi2026.10": ["compiled to WebAssembly with two lines that only record state",
                                                    "the APCISR engine is the original C in WebAssembly"]}},
    {"asset": "paras", "candidates": ["hmnsq/paras"], "relationship": "source of stack sources"},
    {"asset": "Parashakti", "candidates": _across(["parashakti"]), "relationship": "the sovereign stack"},
    {"asset": "BURP", "candidates": ["hmnsq/burp"], "relationship": "ingestion"},
    {"asset": "chandah", "candidates": ["project-ilm/chandah"], "relationship": "example only"},
    {"asset": "tajziya", "candidates": ["zistgah/tajziya"], "relationship": "script list"},
    {"asset": "ILM registry", "candidates": ["project-ilm/ilm.codes"], "relationship": "script list"},
    {"asset": "zamin", "candidates": ["zistgah/zamin"], "relationship": "proposed"},
    {"asset": "jugaad28", "candidates": ["zistgah/jugaad28"], "relationship": "proposed"},
    {"asset": "dhancha", "candidates": ["zistgah/dhancha"], "relationship": "proposed"},
    {"asset": "PANINI family and PANIR", "candidates": ["zistgah/panini", "zistgah/panir"], "relationship": "boundary only"},
    {"asset": "zops", "candidates": _across(["zops"]), "relationship": "provenance"},
    {"asset": "Candor", "candidates": _across(["candor"]), "relationship": "provenance"},
    {"asset": "Tok DOI", "candidates": _across(["tokdoi", "tok-doi", "tok"]), "relationship": "provenance"},
    {"asset": "misty-doi", "candidates": _across(["misty-doi", "misty"]), "relationship": "provenance"},
    {"asset": "satsneha", "candidates": _across(["satsneha"]), "relationship": "provenance"},
    {"asset": "AyeVDI", "candidates": ["ayevdi/ayevdi"], "relationship": "proposed"},
    {"asset": "Panini Q", "candidates": ["zistgah/paniniq"], "relationship": "proposed"},
    {"asset": "PEDLER (qedler)", "candidates": ["project-ilm/qedler"], "relationship": "recorded"},
    {"asset": "NI2A2", "candidates": _across(["ni2a2", "ni2a2-angel", "angel"]), "relationship": "located at intake",
     "search": ["ni2a2"], "name_terms": ["ni2a2", "angel"]},
    {"asset": "MSRR", "candidates": _across(["msrr", "msrr-robotics"]), "relationship": "located at intake",
     "search": ["msrr", "self-reconfigur", "modular robot"], "name_terms": ["msrr", "reconfig", "modular"]},
    {"asset": "SHAKTI sources (for P5.6)", "candidates": ["gitlab.com/shaktiproject/cores/c-class",
                                                          "gitlab.com/shaktiproject/software/shakti-sdk",
                                                          "gitlab.com/shaktiproject/cores/soc_config",
                                                          "shakti-processor/c-class", "shakti-processor/shakti-soc",
                                                          "shaktiproject/c-class", "hmnsq/c-class", "hmnsq/shakti-sdk",
                                                          "hmnsq/shakti"],
     "relationship": "read for the SHAKTI study", "search": ["shakti"], "search_scope": ["hmnsq/parashakti", "hmnsq/paras"]},
]

PROPOSED_NAMES = ["repsynth", "subcore", "mechsim", "anasim", "optisim"]
NOT_PUBLIC_RX = re.compile(r"could not read Username|Repository not found|not found", re.I)


def gh_login_state() -> dict:
    """Whether a GitHub CLI login was handed in. Reads state only; prints no token."""
    r = run_cmd(["gh", "auth", "status"], timeout=30)
    return {"command": r["command"], "exit_code": r["exit_code"],
            "output_tail": tail(r["stdout"] + r["stderr"], 6)}


def org_listing(org: str) -> dict:
    """Paginated listing of an organisation's repositories through the GitHub CLI
    (gh handles pagination up to --limit). Where the API is unreachable the attempt is recorded."""
    r = run_cmd(["gh", "repo", "list", org, "--limit", "4000", "--json", "name,isFork,isPrivate,defaultBranchRef"],
                timeout=180)
    res = {"command": r["command"], "exit_code": r["exit_code"]}
    if r["exit_code"] == 0:
        try:
            res["repositories"] = sorted(x["name"] for x in json.loads(r["stdout"] or "[]"))
        except json.JSONDecodeError:
            res["exit_code"], res["output_tail"] = 1, tail(r["stdout"], 5)
    else:
        res["output_tail"] = tail(r["stderr"] + r["stdout"], 4)
    if r["exit_code"] == 0 and not res.get("repositories"):
        res["note"] = "the command exited 0 but returned no repositories"
    return res


def repo_url(slug: str) -> str:
    """owner/name means GitHub; a slug whose first part is a host name (gitlab.com/...) is taken as written."""
    return f"https://{slug}" if "." in slug.split("/")[0] else f"https://github.com/{slug}"


def ls_remote(slug: str) -> dict:
    url = repo_url(slug)
    r = run_cmd(["git", *_git_auth_args(), "ls-remote", url, "HEAD"], env=_env_for_git(), timeout=60)
    sha = None
    if r["exit_code"] == 0:
        for line in r["stdout"].splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1] == "HEAD":
                sha = parts[0]
    found = sha is not None
    return {"slug": slug, "url": url, "command": r["command"], "exit_code": r["exit_code"], "head": sha,
            "found": found,
            "finding": ("public repository" if found else
                        "no public repository at this name (a private repository would answer the same)"
                        if NOT_PUBLIC_RX.search(r["stderr"]) else "not established: " + tail(r["stderr"], 2))}


def clone_dir(slug: str) -> Path:
    return ASSETS / slug.replace("/", "__")


def content_digest(tree: Path) -> dict:
    """sha256 over the sorted (path, mode, sha256) of every file outside .git: an independent
    check that the checkout's bytes are what they were."""
    h = hashlib.sha256()
    n = 0
    for p in sorted(tree.rglob("*")):
        rel = p.relative_to(tree)
        if rel.parts and rel.parts[0] == ".git":
            continue
        if p.is_symlink():
            h.update(f"L {rel} {os.readlink(p)}\n".encode())
            n += 1
        elif p.is_file():
            h.update(f"F {rel} {oct(p.stat().st_mode & 0o777)} {sha256_file(p)}\n".encode())
            n += 1
    return {"files": n, "sha256": h.hexdigest()}


def tree_state(tree: Path) -> dict:
    """Commit, git tree hash, working-tree status and content digest of a clone. Read only:
    git runs without optional locks so not even the index stat cache is refreshed."""
    g = ["git", "--no-optional-locks", "-C", str(tree)]
    head = run_cmd(g + ["rev-parse", "HEAD"], timeout=60)["stdout"].strip()
    tree_hash = run_cmd(g + ["rev-parse", "HEAD^{tree}"], timeout=60)["stdout"].strip()
    st = run_cmd(g + ["status", "--porcelain", "--ignored", "--untracked-files=all"], timeout=300)
    return {"commit": head, "tree": tree_hash, "status_exit": st["exit_code"],
            "status_clean": st["exit_code"] == 0 and st["stdout"].strip() == "",
            "status_lines": st["stdout"].splitlines()[:20], "content": content_digest(tree)}


def same_state(a: dict, b: dict) -> bool:
    return (a["commit"] == b["commit"] and a["tree"] == b["tree"] and a["content"] == b["content"]
            and a["status_clean"] and b["status_clean"])


def pinned_clone(slug: str, sha: str, log_name: str) -> dict:
    """Shallow clone of exactly one commit. An existing clone is never altered: if it is at the
    pinned commit it is reused; otherwise it is reported and left alone."""
    dest = clone_dir(slug)
    steps = []
    if dest.exists():
        cur = run_cmd(["git", "--no-optional-locks", "-C", str(dest), "rev-parse", "HEAD"], timeout=60)
        if cur["exit_code"] == 0 and cur["stdout"].strip() == sha:
            return {"path": str(dest), "action": "reused existing clone at the pinned commit", "steps": steps, "ok": True}
        return {"path": str(dest), "action": "existing clone is at another commit; left untouched",
                "existing_head": cur["stdout"].strip(), "steps": steps, "ok": False}
    dest.parent.mkdir(parents=True, exist_ok=True)
    env = _env_for_git()
    for i, cmd in enumerate([
        ["git", "init", "-q", str(dest)],
        ["git", "-C", str(dest), "remote", "add", "origin", repo_url(slug)],
        ["git", *_git_auth_args(), "-C", str(dest), "fetch", "--depth", "1", "--no-tags", "origin", sha],
        ["git", "-C", str(dest), "-c", "advice.detachedHead=false", "checkout", "-q", "--detach", "FETCH_HEAD"],
    ]):
        r = run_cmd(cmd, env=env, timeout=1800, log_name=f"{log_name}_{i}")
        steps.append({"command": r["command"], "exit_code": r["exit_code"], "stderr_tail": tail(r["stderr"], 3)})
        if r["exit_code"] != 0:
            return {"path": str(dest), "action": "clone failed", "steps": steps, "ok": False}
    return {"path": str(dest), "action": "cloned", "steps": steps, "ok": True}


def _load_register() -> dict:
    p = REPORTS / "asset_register.json"
    return json.loads(p.read_text()) if p.exists() else {}


def cmd_clone(args) -> int:
    started = utc_now()
    prev = {} if args.repin else {r["slug"]: r.get("commit") for a in _load_register().get("assets", [])
                                  for r in a.get("repositories", []) if r.get("commit")}
    login = gh_login_state()
    listings = {o: org_listing(o) for o in ORGS}
    listed = {o: set(l.get("repositories", [])) for o, l in listings.items()}
    rows, failures = [], 0
    for row in ASSET_ROWS:
        cands = list(dict.fromkeys(row["candidates"]))
        # Names found by listing that match a candidate's name pattern are added (author's machine).
        out = {"asset": row["asset"], "relationship": row["relationship"], "tried": [], "repositories": []}
        seen_lower = set()
        for slug in cands:
            if slug.lower() in seen_lower:
                continue
            seen_lower.add(slug.lower())
            lr = ls_remote(slug)
            out["tried"].append({k: lr[k] for k in ("slug", "command", "exit_code", "finding")})
            if not lr["found"]:
                continue
            sha = prev.get(slug) or lr["head"]
            cl = pinned_clone(slug, sha, f"P0.2_clone_{slug.replace('/', '__')}")
            entry = {"slug": slug, "remote_head": lr["head"], "pinned": sha, "clone": cl}
            if cl["ok"]:
                st = tree_state(Path(cl["path"]))
                entry.update({"commit": st["commit"], "tree": st["tree"], "before": st})
                if st["commit"] != sha:
                    entry["clone"]["ok"] = False
                    failures += 1
            else:
                failures += 1
            out["repositories"].append(entry)
        out["state"] = "found" if out["repositories"] else "not found"
        rows.append(out)
    reg = {"_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0", "generator": f"repsynth.lanes.intake {VERSION}",
           "gh_login": login, "org_listings": listings,
           "listing_note": ("Paginated organisation listing ran through `gh repo list` and its results are in "
                            "org_listings." if all(l["exit_code"] == 0 for l in listings.values()) else
                            "Paginated organisation listing could not run on this machine (see org_listings for "
                            "each command and its exit code); discovery fell back to the exact names in each "
                            "row's `tried` list. Repositories under other names are not established."),
           "assets": rows}
    _write_json(REPORTS / "asset_register.json", reg)
    rec = record("P0.2", "clone", "python3 -m repsynth intake clone", 1 if failures else 0, started_utc=started,
                       outputs=[REPORTS / "asset_register.json"],
                       tool_versions={"git": _tool_version(["git", "--version"]), "gh": _tool_version(["gh", "--version"])},
                       results={"found": [r["asset"] for r in rows if r["state"] == "found"],
                                "not_found": [r["asset"] for r in rows if r["state"] != "found"],
                                "clone_failures": failures},
                       state="wired_unproven", notes="Clones and their tree states before any other step.")
    print(json.dumps({"record": str(rec), "failures": failures,
                      "found": sum(r["state"] == "found" for r in rows), "rows": len(rows)}, indent=2))
    return 1 if failures else 0


def cmd_verify(args) -> int:
    """Recompute every clone's state and compare with the state recorded at clone time."""
    started = utc_now()
    reg = _load_register()
    if not reg:
        raise SystemExit("reports/asset_register.json is missing: run `intake clone` first")
    changed, checked = [], 0
    for a in reg["assets"]:
        for r in a["repositories"]:
            if "before" not in r:
                continue
            after = tree_state(Path(r["clone"]["path"]))
            r["after"] = after
            r["unchanged"] = same_state(r["before"], after)
            checked += 1
            if not r["unchanged"]:
                changed.append(r["slug"])
    reg["verification"] = {"checked": checked, "changed": changed,
                           "rule": "commit, git tree, content digest equal and working tree clean, before and after"}
    _write_json(REPORTS / "asset_register.json", reg)
    _write_register_md(reg)
    ok = checked > 0 and not changed
    rec = record("P0.2", "verify", "python3 -m repsynth intake verify", 0 if ok else 1, started_utc=started,
                       outputs=[REPORTS / "asset_register.json", REPORTS / "asset_register.md"],
                       results={"checked": checked, "changed": changed},
                       state="wired_unproven", notes="Tree states after the run compared with those at clone time.")
    print(json.dumps({"record": str(rec), "checked": checked, "changed": changed}, indent=2))
    return 0 if ok else 1


def cmd_names(args) -> int:
    started = utc_now()
    out = []
    for name in PROPOSED_NAMES:
        for o in ALL_ORGS:
            lr = ls_remote(f"{o}/{name}")
            out.append({"name": name, "org": o, "command": lr["command"], "exit_code": lr["exit_code"],
                        "exists_publicly": lr["found"], "finding": lr["finding"]})
    collisions = [f"{x['org']}/{x['name']}" for x in out if x["exists_publicly"]]
    inv = estate_inventory(_load_register())
    in_estate = [r for r in inv["repos"] if r.split("/", 1)[1].lower() in PROPOSED_NAMES]
    collisions += [r for r in in_estate if r not in collisions]
    res = {"_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0", "generator": f"repsynth.lanes.intake {VERSION}",
           "proposed": PROPOSED_NAMES, "orgs": ALL_ORGS, "checks": out, "collisions": collisions,
           "estate_list_matches": in_estate, "estate_list_source": inv.get("source"),
           "limit": "git ls-remote answers alike for an absent and a private repository; with a GitHub CLI login "
                    "handed in, private repositories the login can see are also detected."}
    reg = _load_register()
    reg["name_check"] = res
    _write_json(REPORTS / "asset_register.json", reg)
    rec = record("P0.2", "names", "python3 -m repsynth intake names", 0 if not collisions else 1,
                       started_utc=started, outputs=[REPORTS / "asset_register.json"],
                       results={"collisions": collisions, "checks": len(out)}, state="wired_unproven")
    print(json.dumps({"record": str(rec), "collisions": collisions}, indent=2))
    return 0 if not collisions else 1


def _grep_tree(tree: Path, term: str, limit: int = 40) -> dict:
    """Case-insensitive fixed-string search of file contents and of paths in a clone (read only)."""
    g = run_cmd(["git", "--no-optional-locks", "-C", str(tree), "grep", "-I", "-i", "-n", "-F", "-e", term, "HEAD", "--"],
                timeout=300)
    hits = [l.split(":", 1)[1] if l.startswith("HEAD:") else l for l in g["stdout"].splitlines()]
    names = run_cmd(["git", "--no-optional-locks", "-C", str(tree), "ls-tree", "-r", "--name-only", "HEAD"], timeout=120)
    path_hits = [p for p in names["stdout"].splitlines() if term.lower() in p.lower()]
    return {"term": term, "grep_exit": g["exit_code"], "content_hits": len(hits), "first_hits": [h[:240] for h in hits[:limit]],
            "path_hits": path_hits[:limit], "path_hit_count": len(path_hits)}


def _clone_path(reg: dict, slug: str) -> Path | None:
    for a in reg.get("assets", []):
        for r in a["repositories"]:
            if r["slug"] == slug and r["clone"]["ok"]:
                return Path(r["clone"]["path"])
    return None


def estate_inventory(reg: dict) -> dict:
    """Union of the repository names in the author's own estate lists, read from the pinned
    Hindawi clone. It stands in for an organisation listing where the API is unreachable."""
    hp = _clone_path(reg, "hindawiai/hindawi2026.10")
    if not hp:
        return {"state": "not established: Hindawi 2026.10 is not cloned", "repos": []}
    repos, files = set(), []
    for rel in ESTATE_FILES:
        f = hp / rel
        if not f.exists():
            files.append({"path": rel, "state": "absent"})
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        files.append({"path": rel, "sha256": sha256_file(f)})
        if "own" in d:
            for k in ("own", "own_family_forks", "third_party_forks", "to_confirm"):
                for x in d.get(k, []):
                    for part in str(x).split("<-"):
                        if "/" in part:
                            repos.add(part.strip())
        else:
            for org, v in d.items():
                for r in (v or {}).get("repos", []):
                    repos.add(f"{org}/{r[0]}")
    commit = reg_commit(reg, "hindawiai/hindawi2026.10")
    return {"source": "hindawiai/hindawi2026.10 at " + commit, "files": files, "repos": sorted(repos)}


def reg_commit(reg: dict, slug: str) -> str:
    for a in reg.get("assets", []):
        for r in a["repositories"]:
            if r["slug"] == slug:
                return r.get("commit", "unknown")
    return "not cloned"


def cmd_locate(args) -> int:
    started = utc_now()
    reg = _load_register()
    if not reg:
        raise SystemExit("reports/asset_register.json is missing: run `intake clone` first")
    inv = estate_inventory(reg)
    reg["estate_inventory"] = {k: v for k, v in inv.items()}
    clones = [(r["slug"], Path(r["clone"]["path"])) for a in reg["assets"] for r in a["repositories"] if r["clone"]["ok"]]
    for row in ASSET_ROWS:
        target = next(a for a in reg["assets"] if a["asset"] == row["asset"])
        if row.get("search"):
            scope = row.get("search_scope")
            target["searched"] = []
            for slug, path in clones:
                if scope and slug not in scope:
                    continue
                for term in row["search"]:
                    res = _grep_tree(path, term)
                    res["repository"] = slug
                    if res["content_hits"] or res["path_hit_count"]:
                        target["searched"].append(res)
                    else:
                        target["searched"].append({"repository": slug, "term": term, "grep_exit": res["grep_exit"],
                                                   "content_hits": 0, "path_hit_count": 0})
        if row.get("name_terms"):
            matches = [r for r in inv["repos"] if any(t in r.split("/", 1)[1].lower() for t in row["name_terms"])]
            target["estate_name_matches"] = []
            for m in matches:
                lr = ls_remote(m)
                target["estate_name_matches"].append({"repository": m, "exit_code": lr["exit_code"],
                                                      "finding": lr["finding"], "head": lr["head"]})
        if row.get("probe"):
            target["probes"] = []
            for slug, paths in row["probe"].items():
                cp = _clone_path(reg, slug)
                for rel in paths:
                    q = cp / rel if cp else None
                    target["probes"].append({"repository": slug, "path": rel,
                                             "exists": bool(q and q.exists()),
                                             "kind": ("directory" if q and q.is_dir() else "file" if q and q.is_file() else "absent"),
                                             "files": (sum(1 for x in q.rglob("*") if x.is_file()) if q and q.is_dir() else None)})
        if row.get("evidence_grep"):
            target["evidence"] = []
            for slug, phrases in row["evidence_grep"].items():
                cp = _clone_path(reg, slug)
                for ph in phrases:
                    g = run_cmd(["git", "--no-optional-locks", "-C", str(cp), "grep", "-n", "-F", "-e", ph, "HEAD", "--"], timeout=120)
                    for line in g["stdout"].splitlines()[:5]:
                        f, ln, text = line.split(":", 3)[1:4] if line.startswith("HEAD:") else (line.split(":", 2) + [""])[:3]
                        i = text.find(ph)
                        target["evidence"].append({"repository": slug, "file": f, "line": int(ln),
                                                   "excerpt": text[max(0, i - 80): i + len(ph) + 160]})
        if not target["repositories"] and target.get("probes") and all(x["exists"] for x in target["probes"]) and target.get("evidence"):
            target["state"] = ("located inside another repository (candidate): R2's description is not yet "
                               "confirmed against it; the author confirms")
            target["located_at"] = sorted({f"{x['repository']}:{x['path']}" for x in target["probes"]})
    _write_json(REPORTS / "asset_register.json", reg)
    rec = record("P0.2", "locate", "python3 -m repsynth intake locate", 0, started_utc=started,
                 outputs=[REPORTS / "asset_register.json"],
                 results={a["asset"]: {"state": a["state"],
                                       "mentions": sum(s.get("content_hits", 0) + s.get("path_hit_count", 0) for s in a.get("searched", [])),
                                       "estate_name_matches": [m["repository"] for m in a.get("estate_name_matches", [])]}
                          for a in reg["assets"] if "searched" in a or "estate_name_matches" in a},
                 state="wired_unproven",
                 notes="A mention is not the asset; reading of each mention is in the register.")
    print(json.dumps({"record": str(rec), "estate_repos": len(inv["repos"])}, indent=2))
    return 0


def _write_register_md(reg: dict) -> None:
    L = [f"<!-- {NOTICE} SPDX-License-Identifier: CC-BY-SA-4.0 -->", "", "# Asset register (P0.2)", "", NOTICE, "",
         "Generated by `python3 -m repsynth intake` from reports/asset_register.json. "
         "Every clone is shallow, pinned to the commit below, under .cache/assets/, and never edited.", "",
         "## Discovery", "", reg.get("listing_note", ""), "",
         "| Organisation | Listing command | Exit code |", "|---|---|---|"]
    for o, l in reg.get("org_listings", {}).items():
        L.append(f"| {o} | `{l['command']}` | {l['exit_code']} |")
    L += ["", "## Assets", "", "| Asset | State | Repository | Commit | Tree | Unchanged after run |", "|---|---|---|---|---|---|"]
    for a in reg["assets"]:
        if a["repositories"]:
            for r in a["repositories"]:
                L.append(f"| {a['asset']} | found | {r['slug']} | {r.get('commit', 'clone failed')} | "
                         f"{r.get('tree', '')} | {r.get('unchanged', 'not checked')} |")
        else:
            L.append(f"| {a['asset']} | not found | tried: {', '.join(t['slug'] for t in a['tried']) or 'no repository name; searched cloned trees'} | | | |")
    L += ["", "## Searches for received-only assets", ""]
    for a in reg["assets"]:
        if "searched" not in a:
            continue
        L.append(f"### {a['asset']}")
        L.append("")
        hits = [s for s in a["searched"] if s.get("content_hits") or s.get("path_hit_count")]
        L.append(f"Searched {len(a['searched'])} (repository, term) pairs; {len(hits)} had mentions.")
        L.append("")
        for s in hits:
            L.append(f"- {s['repository']}, term `{s['term']}`: {s['content_hits']} content lines, {s['path_hit_count']} paths. "
                     f"First: {('; '.join(s['first_hits'][:3]) or '; '.join(s['path_hits'][:3]))[:400]}")
        if a.get("reading"):
            L += ["", "Reading: " + a["reading"]]
        L.append("")
    nc = reg.get("name_check")
    if nc:
        L += ["## Proposed repository names", "", f"Collisions: {', '.join(nc['collisions']) or 'none found'}. {nc['limit']}", "",
              "| Name | Organisation | Exit code | Finding |", "|---|---|---|---|"]
        for c in nc["checks"]:
            L.append(f"| {c['name']} | {c['org']} | {c['exit_code']} | {c['finding']} |")
    _write_text(REPORTS / "asset_register.md", "\n".join(L) + "\n")


# --------------------------------------------------------------------------------------------
# P0.5 received material
# --------------------------------------------------------------------------------------------

PACKAGE = Path(os.environ.get("REPSYNTH_PACKAGE", "/home/user/build/orchestration/package"))
SOURCES = ROOT / "sources"
JOINERS = {0x200C, 0x200D}  # ZERO WIDTH NON-JOINER / JOINER: meaningful inside many scripts


def is_invisible(cp: int) -> str | None:
    """Return the class of an invisible or deceptive character, or None for a visible one.
    Tab, line feed and carriage return are ordinary layout and are not reported."""
    if cp in (0x09, 0x0A, 0x0D):
        return None
    ch = chr(cp)
    cat = unicodedata.category(ch)
    if cat == "Cc":
        return "control"
    if cat == "Cf":
        return "format"
    if cat == "Co":
        return "private-use"
    if cat == "Cn":
        return "unassigned"
    if cat in ("Zs", "Zl", "Zp") and cp != 0x20:
        return "space-variant"
    if 0xFE00 <= cp <= 0xFE0F or 0xE0100 <= cp <= 0xE01EF:
        return "variation-selector"
    if cp in (0x034F, 0x115F, 0x1160, 0x3164, 0xFFA0, 0x2800, 0xFFFC, 0x180E):
        return "blank-glyph"
    return None


def _letterish(ch: str | None) -> bool:
    return bool(ch) and ord(ch) > 0x7F and unicodedata.category(ch)[0] in ("L", "M")


def scan_and_clean(text: str) -> tuple[str, list[dict]]:
    """Report every invisible character with line and column; build the cleaned copy.
    Space variants become U+0020. Joiners between two non-ASCII letters or marks are kept
    (they change shaping in many scripts) and reported as kept; every other one is removed."""
    found, out = [], []
    line, col = 1, 0
    for i, ch in enumerate(text):
        cp = ord(ch)
        col += 1
        cls = is_invisible(cp)
        if cls:
            prev_ch = text[i - 1] if i else None
            next_ch = text[i + 1] if i + 1 < len(text) else None
            if cp in JOINERS and _letterish(prev_ch) and _letterish(next_ch):
                action = "kept (joiner between letters)"
                out.append(ch)
            elif cls == "space-variant":
                action = "replaced by U+0020"
                out.append(" ")
            else:
                action = "removed"
            found.append({"line": line, "column": col, "codepoint": f"U+{cp:04X}",
                          "name": unicodedata.name(ch, "UNNAMED"), "class": cls, "action": action})
        else:
            out.append(ch)
        if ch == "\n":
            line, col = line + 1, 0
    return "".join(out), found


def docx_text(path: Path) -> str:
    """Text of a .docx: paragraphs of the body, then footnotes, headers and footers, in part order."""
    import zipfile
    import xml.etree.ElementTree as ET
    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    with zipfile.ZipFile(path) as z:
        parts = ["word/document.xml"] + sorted(n for n in z.namelist()
                                               if re.match(r"word/(footnotes|endnotes|header\d*|footer\d*)\.xml$", n))
        paras = []
        for part in parts:
            if part not in z.namelist():
                continue
            root = ET.fromstring(z.read(part))
            for p in root.iter(W + "p"):
                buf = []
                for el in p.iter():
                    if el.tag == W + "t" and el.text:
                        buf.append(el.text)
                    elif el.tag == W + "tab":
                        buf.append("\t")
                    elif el.tag in (W + "br", W + "cr"):
                        buf.append("\n")
                paras.append("".join(buf))
    return "\n".join(paras) + "\n"


def receive(files: list[Path], label: str, manifest: dict | None = None, store: Path = SOURCES,
            report_dir: Path | None = None) -> dict:
    """Keep each original byte-identical under <store>/<label>/original/, write a cleaned reading
    copy under <store>/<label>/reading/ and the invisible-character report (in report_dir,
    default <store>/<label>). Received documents go to sources/; a test on documents that must
    not enter the tree keeps its copies under .cache/received/ and only its report in sources/."""
    base = store / label
    report_dir = report_dir or base
    (base / "original").mkdir(parents=True, exist_ok=True)
    (base / "reading").mkdir(parents=True, exist_ok=True)
    entries = []
    for f in files:
        dst = base / "original" / f.name
        shutil.copyfile(f, dst)
        src_hash, dst_hash = sha256_file(f), sha256_file(dst)
        e = {"name": f.name, "received_from": str(f), "sha256_received": src_hash, "sha256_kept": dst_hash,
             "byte_identical": src_hash == dst_hash and f.read_bytes() == dst.read_bytes()}
        if manifest is not None:
            e["sha256_in_manifest"] = manifest.get(f.name, "not listed")
            e["matches_manifest"] = manifest.get(f.name) == src_hash
        if f.suffix.lower() == ".docx":
            text, kind = docx_text(f), "text extracted from the .docx parts"
        else:
            raw = f.read_bytes()
            try:
                text, kind = raw.decode("utf-8"), "utf-8 text"
            except UnicodeDecodeError:
                text, kind = raw.decode("latin-1"), "not utf-8; read as latin-1"
        cleaned, found = scan_and_clean(text)
        reading = base / "reading" / (f.stem + (".docx.txt" if f.suffix.lower() == ".docx" else f.suffix))
        reading.write_text(cleaned, encoding="utf-8")
        rescan = scan_and_clean(cleaned)[1]
        e.update({"reading_copy": str(reading.relative_to(ROOT)), "reading_kind": kind,
                  "sha256_reading": sha256_file(reading),
                  "original_kept_at": str(dst.relative_to(ROOT)), "invisible_found": len(found),
                  "invisible_by_codepoint": dict(sorted(
                      {k: sum(1 for x in found if x["codepoint"] == k) for k in {x["codepoint"] for x in found}}.items())),
                  "remaining_after_clean": [x for x in rescan if not x["action"].startswith("kept")],
                  "occurrences": found})
        entries.append(e)
    report = {"_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0", "generator": f"repsynth.lanes.intake {VERSION}",
              "label": label, "documents": entries,
              "rules": "Reported: every character of class control (except tab, LF, CR), format, private use, "
                       "unassigned, space variants other than U+0020, variation selectors and blank glyphs. "
                       "Cleaning: space variants become U+0020; ZWJ and ZWNJ between two non-ASCII letters or marks "
                       "are kept and reported; every other reported character is removed."}
    _write_json(report_dir / "invisible_report.json", report)
    md = [f"<!-- {NOTICE} SPDX-License-Identifier: CC-BY-SA-4.0 -->", "", f"# Invisible-character report: {label}", "",
          NOTICE, "", report["rules"], "", "| Document | sha256 received | Byte-identical | Invisible found | By code point |",
          "|---|---|---|---|---|"]
    for e in entries:
        md.append(f"| {e['name']} | {e['sha256_received']} | {e['byte_identical']} | {e['invisible_found']} | "
                  f"{', '.join(f'{k}: {v}' for k, v in e['invisible_by_codepoint'].items()) or 'none'} |")
    md += ["", "Every occurrence, with line and column in the reading text, is in invisible_report.json."]
    _write_text(report_dir / "invisible_report.md", "\n".join(md) + "\n")
    (report_dir / "SHA256SUMS").write_text("".join(f"{e['sha256_received']}  original/{e['name']}\n" for e in entries))
    return report


def cmd_received(args) -> int:
    started = utc_now()
    results = {}
    if args.files:
        files = [Path(f) for f in args.files]
        rep = receive(files, args.label or "received")
        results[args.label or "received"] = {"documents": len(files)}
    else:
        # Search the package for R1, R2, R3 (by name and by heading) before anything else.
        search = []
        for f in sorted(PACKAGE.rglob("*")):
            if not f.is_file():
                continue
            hit_name = re.search(r"(^|[^A-Za-z0-9])R[123]([^0-9]|$)", f.name) is not None
            search.append({"path": str(f.relative_to(PACKAGE)), "name_matches": hit_name})
        found = [s["path"] for s in search if s["name_matches"]]
        results["r_documents_in_package"] = found or "none: R1, R2 and R3 are not in the package"
        results["package_files_searched"] = len(search)
        # Test the code on the package's own reading copies and .docx files, checked against MANIFEST.sha256.
        manifest = {}
        mf = PACKAGE / "MANIFEST.sha256"
        if mf.exists():
            for line in mf.read_text().splitlines():
                parts = line.split()
                if len(parts) == 2:
                    manifest[Path(parts[1]).name] = parts[0]
        files = sorted(f for f in PACKAGE.rglob("*") if f.suffix.lower() in (".md", ".docx") and f.is_file())
        rep = receive(files, "package_0.3.0", manifest, store=CACHE / "received",
                      report_dir=SOURCES / "package_0.3.0_test")
        results["package_test"] = {
            "documents": len(files),
            "all_byte_identical": all(e["byte_identical"] for e in rep["documents"]),
            "manifest_mismatches": [e["name"] for e in rep["documents"] if e.get("sha256_in_manifest") not in ("not listed",)
                                    and not e["matches_manifest"]],
            "not_in_manifest": [e["name"] for e in rep["documents"] if e.get("sha256_in_manifest") == "not listed"],
            "invisible_total": sum(e["invisible_found"] for e in rep["documents"]),
            "remaining_after_clean": sum(len(e["remaining_after_clean"]) for e in rep["documents"])}
        _write_json(SOURCES / "received_search.json", {"_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0",
                                                       "package": str(PACKAGE), "files": search, "found": found})
    pt = results.get("package_test", {})
    ok = (not pt) or (pt["all_byte_identical"] and not pt["manifest_mismatches"] and pt["remaining_after_clean"] == 0)
    rec = record("P0.5", "received", "python3 -m repsynth intake received" + (" " + " ".join(args.files) if args.files else ""),
                       0 if ok else 1, started_utc=started, outputs=[SOURCES], results=results,
                       state="wired_unproven",
                       notes="R1, R2 and R3 were not received with the package; the code was exercised on the package's own documents.")
    print(json.dumps({"record": str(rec), "results": results}, indent=2, ensure_ascii=False))
    return 0 if ok else 1


# --------------------------------------------------------------------------------------------
# P0.4 licence intake
# --------------------------------------------------------------------------------------------

LIC_CACHE = CACHE / "licences"
LICENCE_NAME_RX = re.compile(r"^([\w]+[-_.])*(licen[cs]e|copying|copyright|notice|unlicense|ofl)\d*([._-].*)?$", re.I)


def _gh(slug):
    return {"kind": "repo", "url": f"https://github.com/{slug}"}


def _deb(pkg):
    return {"kind": "deb", "path": f"/usr/share/doc/{pkg}/copyright"}


def _pip(dist):
    return {"kind": "pip", "dist": dist}


# MRD section 8, one row per tool, with the drafter's licence as written there and the sources tried.
TOOLS = [
    ("QEMU", "GPL-2.0 for the whole; file licences vary", [_gh("qemu/qemu"), _deb("qemu-system-misc")]),
    ("GNU binutils", "GPL-3.0-or-later", [_gh("bminor/binutils-gdb"), _deb("binutils")]),
    ("GCC", "GPL-3.0-or-later with the GCC Runtime Library Exception", [_gh("gcc-mirror/gcc"), _deb("gcc-13-base")]),
    ("LLVM", "Apache-2.0 with LLVM exception", [_gh("llvm/llvm-project")]),
    ("riscv-opcodes", "Per project", [_gh("riscv/riscv-opcodes")]),
    ("RISC-V unified database", "Per project", [_gh("riscv-software-src/riscv-unified-db")]),
    ("Sail RISC-V model", "BSD-2-Clause", [_gh("riscv/sail-riscv")]),
    ("xv6-riscv", "MIT", [_gh("mit-pdos/xv6-riscv")]),
    ("Linux", "GPL-2.0", [_gh("torvalds/linux")]),
    ("BusyBox", "GPL-2.0", [_gh("mirror/busybox")]),
    ("OpenSBI", "BSD-2-Clause", [_gh("riscv-software-src/opensbi")]),
    ("customasm", "Apache-2.0", [_gh("hlorenzi/customasm")]),
    ("Verilator", "LGPL-3.0 or Artistic-2.0", [_gh("verilator/verilator"), _deb("verilator")]),
    ("GHDL", "GPL-2.0-or-later", [_gh("ghdl/ghdl"), _deb("ghdl")]),
    ("cocotb", "BSD-3-Clause", [_gh("cocotb/cocotb"), _pip("cocotb")]),
    ("Yosys", "ISC", [_gh("YosysHQ/yosys"), _deb("yosys")]),
    ("SymbiYosys", "ISC", [_gh("YosysHQ/sby")]),
    ("nextpnr", "ISC", [_gh("YosysHQ/nextpnr"), _deb("nextpnr-ice40")]),
    ("PandA Bambu", "GPL-3.0", [_gh("ferrandi/PandA-bambu")]),
    ("OpenHW CV-X-IF", "Solderpad Hardware Licence 0.51", [_gh("openhwgroup/core-v-xif")]),
    ("CV32E40X", "Solderpad Hardware Licence 0.51", [_gh("openhwgroup/cv32e40x")]),
    ("CVA6", "Solderpad Hardware Licence 0.51", [_gh("openhwgroup/cva6")]),
    ("OpenROAD", "BSD-3-Clause", [_gh("The-OpenROAD-Project/OpenROAD")]),
    ("Unicode Character Database", "Unicode-3.0", [_deb("unicode-data")]),
    ("CLDR", "Unicode-3.0", [_gh("unicode-org/cldr")]),
    ("ICU", "Unicode-3.0", [_gh("unicode-org/icu")]),
    ("HarfBuzz", "MIT", [_gh("harfbuzz/harfbuzz")]),
    ("FreeType", "FTL or GPL-2.0", [{"kind": "repo_file", "url": "https://github.com/freetype/freetype",
                                      "files": ["LICENSE.TXT", "docs/FTL.TXT", "docs/GPLv2.TXT"]}]),
    ("Noto fonts", "OFL-1.1", [_gh("notofonts/latin-greek-cyrillic"), _gh("notofonts/devanagari")]),
    ("SoftFloat", "BSD-3-Clause", [_gh("ucb-bar/berkeley-softfloat-3")]),
    ("TestFloat", "BSD-3-Clause", [_gh("ucb-bar/berkeley-testfloat-3")]),
    ("GMP", "LGPL-3.0-or-later or GPL-2.0-or-later", [_deb("libgmp10")]),
    ("MPFR", "LGPL-3.0-or-later", [_deb("libmpfr6")]),
    ("libdecnumber", "per distribution", [{"kind": "repo_file", "url": "https://github.com/gcc-mirror/gcc",
                                            "files": ["libdecnumber/decNumber.c"], "head_lines": 30}]),
    ("Hypothesis", "MPL-2.0", [_pip("hypothesis"), _gh("HypothesisWorks/hypothesis")]),
    ("Z3", "MIT", [_pip("z3-solver"), _gh("Z3Prover/z3")]),
    ("Ninja", "Apache-2.0", [_gh("ninja-build/ninja"), _deb("ninja-build")]),
    ("wasi-sdk", "Apache-2.0 with LLVM exception", [_gh("WebAssembly/wasi-sdk")]),
    ("Emscripten", "MIT or NCSA", [_gh("emscripten-core/emscripten")]),
    ("cffi", "MIT", [_pip("cffi")]),
    ("Docker", "Per project", [_gh("moby/moby"), _deb("docker-ce")]),
    ("in-toto", "Per project", [_gh("in-toto/in-toto")]),
    ("OpenTimestamps", "Per project", [_gh("opentimestamps/opentimestamps-client")]),
    ("math.js", "Apache-2.0", [_gh("josdejong/mathjs")]),
    ("js-yaml", "MIT", [_gh("nodeca/js-yaml")]),
    ("three.js", "MIT", [_gh("mrdoob/three.js")]),
    ("JSCAD", "MIT", [_gh("jscad/OpenJSCAD.org")]),
    ("planck.js", "MIT", [_gh("piqnt/planck.js")]),
    ("uPlot", "MIT", [_gh("leeoniya/uPlot")]),
    ("quantum-circuit", "MIT", [_gh("quantastica/quantum-circuit")]),
    ("Quirk", "Apache-2.0", [_gh("Strilanc/Quirk")]),
    ("OpenModelica", "OSMC-PL or GPL-3.0", [_gh("OpenModelica/OpenModelica")]),
    ("Modelica Standard Library", "BSD-3-Clause", [_gh("modelica/ModelicaStandardLibrary")]),
    ("ngspice", "BSD-3-Clause with exceptions", [_deb("ngspice")]),
    ("Xyce", "GPL-3.0", [_gh("Xyce/Xyce")]),
    ("Project Chrono", "BSD-3-Clause", [_gh("projectchrono/chrono")]),
    ("Qiskit", "Apache-2.0", [_gh("Qiskit/qiskit")]),
    ("Qiskit Aer", "Apache-2.0", [_gh("Qiskit/qiskit-aer")]),
    ("QuTiP", "BSD-3-Clause", [_gh("qutip/qutip")]),
    ("OpenQASM 3", "Apache-2.0", [_gh("openqasm/openqasm")]),
    ("Perceval", "MIT", [_gh("Quandela/Perceval")]),
    ("Strawberry Fields", "Apache-2.0", [_gh("XanaduAI/strawberryfields")]),
    ("mpmath", "BSD-3-Clause", [_pip("mpmath"), _gh("mpmath/mpmath")]),
    ("Embench-IoT", "GPL-3.0", [_gh("embench/embench-iot")]),
    ("Node.js", "MIT", [_gh("nodejs/node")]),
    ("Playwright", "Apache-2.0", [_gh("microsoft/playwright")]),
    ("Candor", "Per project", []),
    ("Tok DOI", "Per project", [{"kind": "asset", "slug": "project-ilm/tok-doi"}]),
]

DEP5_MAP = {"gpl-2+": "GPL-2.0-or-later", "gpl-2": "GPL-2.0-only", "gpl-3+": "GPL-3.0-or-later", "gpl-3": "GPL-3.0-only",
            "lgpl-2+": "LGPL-2.0-or-later", "lgpl-2.1+": "LGPL-2.1-or-later", "lgpl-2.1": "LGPL-2.1-only",
            "lgpl-3+": "LGPL-3.0-or-later", "lgpl-3": "LGPL-3.0-only", "expat": "MIT", "mit": "MIT", "isc": "ISC",
            "bsd-2-clause": "BSD-2-Clause", "bsd-3-clause": "BSD-3-Clause", "apache-2.0": "Apache-2.0",
            "gfdl-1.3+": "GFDL-1.3-or-later", "artistic-2": "Artistic-2.0", "artistic-2.0": "Artistic-2.0",
            "zlib": "Zlib", "public-domain": "LicenseRef-public-domain", "unicode": "Unicode-DFS-2016"}


def classify_licence(text: str) -> list[dict]:
    """SPDX identifiers established by a licence file's own text, each with the phrase that shows it.
    A bare GPL or LGPL text fixes the version only; '-only' or '-or-later' comes from a project's
    notices, so it is reported as not established from that file."""
    found = []
    raw = text
    t = re.sub(r"\s+", " ", text)  # licence texts wrap their lines anywhere

    def add(i, basis):
        if not any(x["id"] == i for x in found):
            found.append({"id": i, "basis": basis})
    for m in re.finditer(r"SPDX-License-Identifier:\s*([^\s*]+(?:\s+(?:WITH|OR|AND)\s+[^\s*]+)*)", t):
        add(m.group(1).strip(), "SPDX-License-Identifier line")
    for m in re.finditer(r"(?<![\w.-])((?:A|L)?GPL-[23]\.[01]-(?:only|or-later)|CC-BY-SA-4\.0|CC-BY-4\.0|CC0-1\.0|"
                         r"Apache-2\.0|BSD-[23]-Clause|MPL-2\.0|CERN-OHL-[SWP]-2\.0)(?![\w-])", t):
        add(m.group(1), "SPDX identifier named in the file")
    if "TERMS AND CONDITIONS" not in t:
        # A notice (not the licence text itself) fixes "or later": GNU's own "How to apply" wording.
        for m in re.finditer(r"GNU (Lesser |Library )?General Public License.{0,160}?either\s+version\s+(\d(?:\.\d)?)"
                             r"(?: of the License)?,?\s+or,?\s+\(?at your option\)?,?\s+any\s+later\s+version", t, re.S | re.I):
            fam = "LGPL" if m.group(1) else "GPL"
            v = m.group(2) if "." in m.group(2) else m.group(2) + ".0"
            add(f"{fam}-{v}-or-later", "GNU notice: 'either version N ... or (at your option) any later version'")
    if re.search(r"Apache License\s*,?\s*\n?\s*Version 2\.0", t, re.I):
        add("Apache-2.0 WITH LLVM-exception" if "LLVM Exceptions" in t else "Apache-2.0", "Apache License Version 2.0 text")
    if re.search(r"GNU LESSER GENERAL PUBLIC LICENSE", t):
        if re.search(r"Version 3, 29 June 2007", t):
            add("LGPL-3.0 (version from the text; -only or -or-later not established from this file)", "LGPL v3 text")
        elif re.search(r"Version 2\.1", t):
            add("LGPL-2.1 (version from the text; -only or -or-later not established from this file)", "LGPL v2.1 text")
    elif re.search(r"GNU AFFERO GENERAL PUBLIC LICENSE", t):
        add("AGPL-3.0 (version from the text)", "AGPL text")
    elif re.search(r"GNU GENERAL PUBLIC LICENSE", t):
        if re.search(r"Version 3, 29 June 2007", t):
            add("GPL-3.0 (version from the text; -only or -or-later not established from this file)", "GPL v3 text")
        if re.search(r"Version 2, June 1991", t):
            add("GPL-2.0 (version from the text; -only or -or-later not established from this file)", "GPL v2 text")
    if re.search(r"GCC RUNTIME LIBRARY EXCEPTION", t, re.I):
        add("GCC-exception-3.1", "GCC Runtime Library Exception text")
    if re.search(r"Linux-syscall-note", t):
        add("Linux-syscall-note", "named in the file")
    # "a copy of this software": the Unicode agreements grant on "a copy of data files", which is not MIT.
    if re.search(r"Permission is hereby granted, free of charge, to any person obtaining a copy of this software", t, re.I):
        if re.search(r"MIT No Attribution", t):
            add("MIT-0", "MIT No Attribution text")
        else:
            add("MIT", "MIT permission grant")
    if re.search(r"Permission is hereby granted, without written agreement and without license or royalty fees, "
                 r"to use, copy, modify, and distribute this software", t):
        add("MIT-Modern-Variant", "the 'without written agreement and without license or royalty fees' grant")
    if re.search(r"Permission to use, copy, modify, and(/or)? distribute this software for any\s+purpose with or without fee is hereby granted", t):
        add("ISC", "ISC permission grant")
    if re.search(r"University of Illinois/NCSA", t):
        add("NCSA", "University of Illinois/NCSA Open Source License text")
    if re.search(r"Redistribution and use in source and binary forms", t):
        if re.search(r"Neither the name|names? of (its|the) contributors may|name of the copyright holder nor", t, re.I):
            add("BSD-3-Clause", "BSD text with the non-endorsement clause")
        else:
            add("BSD-2-Clause", "BSD text without the non-endorsement clause")
    if re.search(r"Mozilla Public License,? [Vv]ersion 2\.0", t):
        add("MPL-2.0", "Mozilla Public License Version 2.0 text")
    if re.search(r"UNICODE LICENSE V3", t):
        add("Unicode-3.0", "UNICODE LICENSE V3 text")
    elif re.search(r"UNICODE,? INC\.? LICENSE AGREEMENT", t, re.I):
        add("Unicode-DFS-2016", "Unicode data files and software licence agreement")
    if re.search(r"SIL OPEN FONT LICENSE", t, re.I) and "1.1" in t:
        add("OFL-1.1", "SIL Open Font License 1.1 text")
    if re.search(r"The FreeType Project LICENSE", t):
        add("FTL", "FreeType Project License text")
    m = re.search(r"SOLDERPAD HARDWARE LICEN[CS]E,? version ([0-9.]+)", t, re.I)
    if m:
        add(f"SHL-{m.group(1)}", "Solderpad Hardware Licence text")
    if re.search(r"The Artistic License 2\.0", t):
        add("Artistic-2.0", "Artistic License 2.0 text")
    if re.search(r"Open Source Modelica Consortium", t) and re.search(r"Public License", t):
        add("LicenseRef-OSMC-PL", "OSMC Public License text (no SPDX identifier exists for it)")
    if re.search(r"Eclipse Public License", t):
        add("EPL (version as in the text)", "Eclipse Public License text")
    if re.search(r"Boost Software License", t):
        add("BSL-1.0", "Boost Software License text")
    if re.search(r"CERN Open Hardware Licen[cs]e", t):
        add("CERN-OHL (variant as in the text)", "CERN OHL text")
    # Debian machine-readable copyright (DEP-5): the License fields of the Files: * stanza first.
    if raw.startswith("Format:") or "Upstream-Name:" in raw:
        stanzas = re.split(r"\n\s*\n", raw)
        for st in stanzas:
            if re.search(r"^Files:\s*\*\s*$", st, re.M):
                m = re.search(r"^License:\s*(.+)$", st, re.M)
                if m:
                    expr = m.group(1).strip()
                    mapped = " ".join(DEP5_MAP.get(w.lower(), w) for w in expr.split())
                    add(mapped, f"Debian copyright, Files: * stanza, License: {expr}")
    return found


def _fetch_repo_licences(name: str, url: str, extra_files=None, head_lines=None) -> dict:
    dest = LIC_CACHE / re.sub(r"[^A-Za-z0-9_.-]", "_", name) / url.rstrip("/").split("/", 3)[-1].replace("/", "__")
    if not (dest / ".git").exists():
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = run_cmd(["git", *_git_auth_args(), "clone", "-q", "--depth", "1", "--filter=tree:0", "--no-checkout", url, str(dest)],
                    env=_env_for_git(), timeout=600)
        if r["exit_code"] != 0:
            return {"source": url, "command": r["command"], "exit_code": r["exit_code"], "state": "not fetched",
                    "stderr_tail": tail(r["stderr"], 3), "files": []}
    g = ["git", "--no-optional-locks", "-C", str(dest)]
    commit = run_cmd(g + ["rev-parse", "HEAD"], timeout=60)["stdout"].strip()
    names = run_cmd(g + ["ls-tree", "--name-only", "HEAD"], env=_env_for_git(), timeout=300)["stdout"].splitlines()
    want = [n for n in names if LICENCE_NAME_RX.match(n)]
    if extra_files:
        want = list(extra_files)
    if not want:
        lic_dir = [n for n in names if n.lower() in ("licenses", "licences", "license")]
        for d in lic_dir:
            sub = run_cmd(g + ["ls-tree", "--name-only", f"HEAD:{d}"], env=_env_for_git(), timeout=300)["stdout"].splitlines()
            want += [f"{d}/{x}" for x in sub][:12]
    files = []
    for f in want:
        r = run_cmd(g + ["show", f"HEAD:{f}"], env=_env_for_git(), timeout=300)
        if r["exit_code"] != 0:
            files.append({"path": f, "state": f"could not read (exit {r['exit_code']})"})
            continue
        text = r["stdout"]
        if head_lines:
            text = "\n".join(text.splitlines()[:head_lines])
        out = dest.parent / "files" / dest.name / f
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        files.append({"path": f, "sha256": sha256_file(out), "bytes": out.stat().st_size,
                      "spdx": classify_licence(text)})
    return {"source": url, "commit": commit, "state": "fetched", "root_entries": len(names), "files": files}


def _deb_licence(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {"source": path, "state": "not installed here", "files": []}
    text = p.read_text(encoding="utf-8", errors="replace")
    pkg = p.parent.name
    ver = run_cmd(["dpkg-query", "-W", "-f=${Version}", pkg], timeout=30)
    return {"source": path, "state": "read", "package_version": ver["stdout"].strip() or "not established",
            "files": [{"path": path, "sha256": sha256_file(p), "bytes": p.stat().st_size, "spdx": classify_licence(text)}]}


def _pip_licence(dist: str) -> dict:
    from importlib import metadata
    try:
        d = metadata.distribution(dist)
    except metadata.PackageNotFoundError:
        return {"source": f"pip:{dist}", "state": "not installed here", "files": []}
    files = []
    for f in d.files or []:
        if LICENCE_NAME_RX.match(Path(str(f)).name) or "/licenses/" in str(f).lower():
            fp = Path(d.locate_file(f))
            if fp.is_file():
                files.append({"path": str(fp), "sha256": sha256_file(fp), "bytes": fp.stat().st_size,
                              "spdx": classify_licence(fp.read_text(encoding="utf-8", errors="replace"))})
    meta = {k: d.metadata.get(k) for k in ("License-Expression", "License") if d.metadata.get(k)}
    if meta.get("License") and len(meta["License"]) > 200:
        meta["License"] = meta["License"][:200] + " (truncated)"
    return {"source": f"pip:{dist} {d.version}", "state": "read" if files else "installed; no licence file in its record",
            "metadata_licence_fields": meta, "files": files}


DRAFTER_PHRASES = [(r"Apache-2\.0 with LLVM exception", "Apache-2.0 WITH LLVM-exception"),
                   (r"GCC Runtime Library Exception", "GCC-exception-3.1"),
                   (r"Solderpad Hardware Licence 0\.51", "SHL-0.51"), (r"OSMC-PL", "LicenseRef-OSMC-PL"),
                   (r"BSD-3-Clause with exceptions", "BSD-3-Clause"), (r"FTL", "FTL"), (r"NCSA", "NCSA"),
                   (r"Unicode-3\.0", "Unicode-3.0"), (r"OFL-1\.1", "OFL-1.1"), (r"Artistic-2\.0", "Artistic-2.0"),
                   (r"\bISC\b", "ISC"), (r"\bMIT\b", "MIT"), (r"MPL-2\.0", "MPL-2.0"),
                   (r"(?<![\w-])Apache-2\.0(?! with)", "Apache-2.0"), (r"BSD-[23]-Clause", None),
                   (r"(?:L)?GPL-[23]\.0(?:-or-later|-only)?", None)]


def drafter_ids(drafter: str) -> list[str]:
    out = []
    for rx, fixed in DRAFTER_PHRASES:
        for m in re.finditer(rx, drafter):
            v = fixed or m.group(0)
            if v not in out:
                out.append(v)
    return out


def _compare(drafter: str, ids: list[str]) -> str:
    """Exact comparison of identifiers. A bare GPL text ('GPL-3.0 (version from the text ...)') matches
    the drafter's 'GPL-3.0' or the version part of 'GPL-3.0-or-later', and says which."""
    want = drafter_ids(drafter)
    if not want:
        return "the MRD gives no identifier; the file's identifiers are recorded"
    have = [i.split(" (")[0] for i in ids]
    res = []
    for w in want:
        if w in have:
            res.append(f"{w}: agrees")
        elif re.sub(r"-(or-later|only)$", "", w) in have:
            res.append(f"{w}: version agrees; -only or -or-later not established from the file")
        elif any(h.startswith(w) or w.startswith(h) for h in have):
            res.append(f"{w}: agrees in part ({', '.join(h for h in have if h.startswith(w) or w.startswith(h))})")
        else:
            res.append(f"{w}: not in the file; the file's identifiers replace the entry")
    return "; ".join(res)


def cmd_licences(args) -> int:
    started = utc_now()
    reg = _load_register()
    rows = []
    for name, drafter, sources in TOOLS:
        if args.only and name not in args.only:
            continue
        got = []
        for s in sources:
            if s["kind"] == "repo":
                got.append(_fetch_repo_licences(name, s["url"]))
            elif s["kind"] == "repo_file":
                got.append(_fetch_repo_licences(name, s["url"], s["files"], s.get("head_lines")))
            elif s["kind"] == "deb":
                got.append(_deb_licence(s["path"]))
            elif s["kind"] == "pip":
                got.append(_pip_licence(s["dist"]))
            elif s["kind"] == "asset":
                cp = None
                for a in reg.get("assets", []):
                    for r in a["repositories"]:
                        if r["slug"] == s["slug"]:
                            cp = Path(r["clone"]["path"])
                files = []
                if cp:
                    for f in sorted(cp.iterdir()):
                        if f.is_file() and LICENCE_NAME_RX.match(f.name):
                            files.append({"path": f"{s['slug']}:{f.name}", "sha256": sha256_file(f), "bytes": f.stat().st_size,
                                          "spdx": classify_licence(f.read_text(encoding="utf-8", errors="replace"))})
                got.append({"source": s["slug"], "state": "read from the intake clone" if cp else "not cloned", "files": files})
        ids = sorted({x["id"] for g in got for f in g.get("files", []) for x in f.get("spdx", [])})
        established = bool(ids)
        rows.append({"tool": name, "drafter_entry": drafter, "sources": got, "spdx_from_files": ids,
                     "state": "established from the tool's own licence file" if established else
                              ("not established: no source could be fetched" if not any(g.get("files") for g in got)
                               else "not established: licence files read but no identifier recognised; see files"),
                     "comparison": _compare(drafter, ids) if established else "not established"})
        print(f"{name}: {', '.join(ids) or 'not established'}", file=sys.stderr)
    res = {"_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0", "generator": f"repsynth.lanes.intake {VERSION}",
           "method": "Each tool's licence files are read from its upstream repository at the commit recorded (a "
                     "tree-less shallow clone, then git show of the root licence files), from the Debian copyright "
                     "file of the installed package, or from the installed Python distribution's licence files. "
                     "Identifiers are established only from the text of those files (classify_licence).",
           "tools": rows}
    if args.only and (REPORTS / "licences.json").exists():
        old = json.loads((REPORTS / "licences.json").read_text())
        keep = [r for r in old["tools"] if r["tool"] not in args.only]
        order = [t[0] for t in TOOLS]
        res["tools"] = sorted(keep + rows, key=lambda r: order.index(r["tool"]) if r["tool"] in order else 999)
    _write_json(REPORTS / "licences.json", res)
    _write_text(REPORTS / "licences.md", _licences_md(res))
    n_est = sum(1 for r in res["tools"] if r["state"].startswith("established"))
    rec = record("P0.4", "licences", "python3 -m repsynth intake licences" + (" --only " + " ".join(args.only) if args.only else ""),
                 0, started_utc=started, outputs=[REPORTS / "licences.json", REPORTS / "licences.md"],
                 tool_versions={"git": _tool_version(["git", "--version"])},
                 results={"tools": len(res["tools"]), "established": n_est,
                          "not_established": [r["tool"] for r in res["tools"] if not r["state"].startswith("established")]},
                 state="wired_unproven")
    print(json.dumps({"record": str(rec), "tools": len(res["tools"]), "established": n_est}, indent=2))
    return 0


def _licences_md(res: dict) -> str:
    L = [f"<!-- {NOTICE} SPDX-License-Identifier: CC-BY-SA-4.0 -->", "", "# Licence intake (P0.4)", "", NOTICE, "",
         res["method"], "", "| Tool | MRD section 8 entry | From the tool's own files | Files (source, path) | State |",
         "|---|---|---|---|---|"]
    for r in res["tools"]:
        fl = []
        for g in r["sources"]:
            for f in g.get("files", []):
                if f.get("sha256"):
                    fl.append(f"{g['source']}{' @ ' + g['commit'][:12] if g.get('commit') else ''}: {f['path']}")
        L.append(f"| {r['tool']} | {r['drafter_entry']} | {'; '.join(r['spdx_from_files']) or 'not established'} | "
                 f"{'<br>'.join(fl) or ', '.join(g['source'] + ' (' + g['state'] + ')' for g in r['sources']) or 'no source known'} | "
                 f"{r['state']}; {r['comparison']} |")
    L += ["", "File hashes and the phrase that established each identifier are in reports/licences.json."]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------------------------
# self-tests: every check of this lane shown refusing a planted defect
# --------------------------------------------------------------------------------------------

def verify_kept(report_dir: Path, store: Path) -> list[str]:
    """Re-hash every kept original against the hash recorded when it was received."""
    rep = json.loads((report_dir / "invisible_report.json").read_text())
    bad = []
    for e in rep["documents"]:
        kept = ROOT / e["original_kept_at"]
        if not kept.exists() or sha256_file(kept) != e["sha256_received"]:
            bad.append(e["name"])
    return bad


def cmd_selftest(args) -> int:
    started = utc_now()
    base = TMP / "selftest"
    if base.exists():
        shutil.rmtree(base)
    base.mkdir(parents=True)
    checks = []

    def check(name, planted, refused, detail=""):
        checks.append({"check": name, "planted_defect": planted, "refused": bool(refused), "detail": detail})

    # 1 clone verification: a changed file, an untracked file, and the clean state
    repo = base / "repo"
    repo.mkdir()
    for c in (["git", "init", "-q", str(repo)], ["git", "-C", str(repo), "config", "user.email", "selftest@example.invalid"],
              ["git", "-C", str(repo), "config", "user.name", "selftest"]):
        run_cmd(c)
    (repo / "a.txt").write_text("oracle\n")
    run_cmd(["git", "-C", str(repo), "add", "a.txt"])
    run_cmd(["git", "-C", str(repo), "commit", "-q", "-m", "x"])
    before = tree_state(repo)
    check("clone unchanged: clean tree passes", "none (control)", same_state(before, tree_state(repo)))
    (repo / "a.txt").write_text("edited\n")
    check("clone unchanged: edited tracked file", "a.txt rewritten", not same_state(before, tree_state(repo)))
    (repo / "a.txt").write_text("oracle\n")
    (repo / "build.o").write_text("x")
    check("clone unchanged: untracked file", "build.o added", not same_state(before, tree_state(repo)))
    (repo / "build.o").unlink()
    os.chmod(repo / "a.txt", 0o755)
    check("clone unchanged: mode change", "a.txt made executable", not same_state(before, tree_state(repo)))
    os.chmod(repo / "a.txt", 0o644)
    check("clone unchanged: restored tree passes again", "none (control)", same_state(before, tree_state(repo)))

    # 2 received material: every planted invisible character is reported; the cleaned copy has none left
    planted = ("A​B﻿C D‮E­F क्‍ष G⁠H‌I\n"
               "J\U000E0041K️L\u0007M\n")
    expect = {"U+200B", "U+FEFF", "U+00A0", "U+202E", "U+00AD", "U+200D", "U+2060", "U+200C", "U+E0041", "U+FE0F", "U+0007"}
    src = base / "planted.md"
    src.write_text(planted, encoding="utf-8")
    rep = receive([src], "planted", store=base / "received", report_dir=base / "received_report")
    e = rep["documents"][0]
    got = {x["codepoint"] for x in e["occurrences"]}
    check("invisible report: every planted character listed", f"{len(expect)} invisible characters", got == expect,
          f"reported {sorted(got)}")
    kept_joiner = [x for x in e["occurrences"] if x["action"].startswith("kept")]
    check("invisible report: joiner inside Devanagari kept, ASCII-side ZWNJ removed",
          "ZWJ between DEVANAGARI letters; ZWNJ between H and I",
          [x["codepoint"] for x in kept_joiner] == ["U+200D"], f"kept {[x['codepoint'] for x in kept_joiner]}")
    check("cleaned copy: nothing removable remains", "the same text", e["remaining_after_clean"] == [])
    check("originals byte-identical: control", "none (control)", verify_kept(base / "received_report", base / "received") == [])
    kept = ROOT / e["original_kept_at"]
    kept.write_bytes(kept.read_bytes().replace(b"A", b"a", 1))
    check("originals byte-identical: tampered kept copy", "one byte of the kept original changed",
          verify_kept(base / "received_report", base / "received") == ["planted.md"])
    clean_doc = base / "clean.md"
    clean_doc.write_text("plain text\twith a tab\n", encoding="utf-8")
    rep2 = receive([clean_doc], "clean", store=base / "received", report_dir=base / "received_report_clean")
    check("invisible report: no false positive on plain text with a tab", "none (control)",
          rep2["documents"][0]["invisible_found"] == 0)

    # 3 RD4: only the reference unit settles it, and to the recorded figure the measurement matches
    r1 = settle_rd4(int(15.2 * GIB), "reference-unit")
    r2 = settle_rd4(int(30.6 * GIB), "reference-unit")
    r3 = settle_rd4(int(15.7 * GIB), "cloud-build-machine")
    r4 = settle_rd4(int(24 * GIB), "reference-unit")
    check("RD4: 15.2 GiB on the reference unit", "measured value", r1.get("consistent_with") == "author_record", str(r1))
    check("RD4: 30.6 GiB on the reference unit", "measured value", r2.get("consistent_with") == "R2", str(r2))
    check("RD4: a cloud machine never settles RD4", "16 GB measured on another machine", r3["state"].startswith("awaiting"), str(r3))
    check("RD4: a figure matching neither is not forced", "24 GiB", str(r4["settled_value_gb"]).startswith("not established"), str(r4))

    # 4 licence classification: the file's text decides; a bare GPL text does not claim or-later
    gpl3 = "GNU GENERAL PUBLIC LICENSE\nVersion 3, 29 June 2007\nTERMS AND CONDITIONS\n... either version 3 of the License, or (at your option) any later version."
    ids = [x["id"] for x in classify_licence(gpl3)]
    check("licence: bare GPL-3 text is not -or-later", "the GPL text's own How-to-apply appendix",
          not any(i.startswith("GPL-3.0-or-later") for i in ids) and any(i.startswith("GPL-3.0") for i in ids), str(ids))
    mit = "Permission is hereby granted, free of charge, to any person obtaining a copy of this software"
    check("licence: MIT text", "MIT grant", [x["id"] for x in classify_licence(mit)] == ["MIT"])
    bsd2 = "Redistribution and use in source and binary forms, with or without modification, are permitted"
    check("licence: BSD without non-endorsement is not BSD-3", "BSD-2 text", [x["id"] for x in classify_licence(bsd2)] == ["BSD-2-Clause"])
    check("licence: unrelated text gives nothing", "a README paragraph", classify_licence("This is a readme.") == [])

    # 5 secrets and host product names never reach output
    tok = "ghp_" + "A" * 36
    check("redaction: a GitHub token in captured output", "token in stderr", tok not in redact(f"fatal: {tok}@github.com"))
    check("redaction: proxy refusal naming the build host", "vendor name in a 403 body",
          "laude" not in redact("not available from Cl" + "aude Code sessions"))
    leak = [p for p in ROOT.rglob("*") if p.is_file() and not {".git", ".cache", "__pycache__"} & set(p.parts)
            and p.stat().st_size < 4_000_000 and _SECRET_RX.search(p.read_text(errors="ignore"))]
    check("no token anywhere in the tree", "scan of every tracked-size file", leak == [], f"files with a token shape: {leak}")
    # The scan above must be able to fail: plant one and look again.
    plant = TMP / "planted_secret.txt"
    plant.write_text(tok)
    check("token scan sees a planted token", "token in a scratch file", bool(_SECRET_RX.search(plant.read_text())))
    plant.unlink()

    ok = all(c["refused"] for c in checks)
    out = REPORTS / "intake_selftest.json"
    _write_json(out, {"_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0", "generator": f"repsynth.lanes.intake {VERSION}",
                      "checks": checks, "all_refused_or_passed_as_expected": ok})
    rec = record("P0.2", "selftest", "python3 -m repsynth intake selftest", 0 if ok else 1, started_utc=started,
                 outputs=[out], results={"checks": len(checks), "as_expected": sum(c["refused"] for c in checks)},
                 state="done" if ok else "failed",
                 notes="Planted defects for the clone check (P0.2), received material (P0.5), RD4 (P0.6), licence "
                       "classification (P0.4) and redaction; controls must pass and plants must be refused.")
    for c in checks:
        print(("ok    " if c["refused"] else "WRONG ") + c["check"])
    print(json.dumps({"record": str(rec), "all_as_expected": ok}))
    return 0 if ok else 1


# --------------------------------------------------------------------------------------------
# entry points
# --------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="repsynth intake", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="sub", required=True)
    h = sub.add_parser("host", help="P0.6 host profile")
    h.add_argument("--role", choices=["reference-unit", "cloud-build-machine", "not-reference-unit"],
                   help="which machine this is (default: REPSYNTH_MACHINE_ROLE, else detected from the processor model)")
    h.set_defaults(fn=cmd_host)
    c = sub.add_parser("clone", help="P0.2 shallow pinned clones")
    c.add_argument("--repin", action="store_true", help="pin to the current remote HEAD instead of the recorded commit")
    c.set_defaults(fn=cmd_clone)
    sub.add_parser("verify", help="P0.2 prove every clone unchanged").set_defaults(fn=cmd_verify)
    sub.add_parser("names", help="P0.2 proposed-name collision check").set_defaults(fn=cmd_names)
    sub.add_parser("locate", help="P0.2 search clones for received-only assets").set_defaults(fn=cmd_locate)
    sub.add_parser("selftest", help="planted defects for every check of this lane").set_defaults(fn=cmd_selftest)
    li = sub.add_parser("licences", help="P0.4 licence intake")
    li.add_argument("--only", nargs="*", help="only these tools (names as in MRD section 8)")
    li.set_defaults(fn=cmd_licences)
    r = sub.add_parser("received", help="P0.5 hash, clean and report received documents")
    r.add_argument("files", nargs="*", help="received documents (default: search the package and test on its own files)")
    r.add_argument("--label", help="folder name under sources/ for the given files")
    r.set_defaults(fn=cmd_received)
    return ap


def _argv(ctx) -> list[str]:
    if ctx is None:
        return sys.argv[1:]
    if isinstance(ctx, (list, tuple)):
        return list(ctx)
    if isinstance(ctx, dict):
        return list(ctx.get("argv") or ctx.get("args") or [])
    for name in ("argv", "args", "rest"):
        v = getattr(ctx, name, None)
        if isinstance(v, (list, tuple)):
            return list(v)
    return []


def run(ctx) -> int:
    args = build_parser().parse_args(_argv(ctx))
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
