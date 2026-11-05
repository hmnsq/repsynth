# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Oracle runners (P0.3, ORC-01, ORC-02, GOV-03, GOV-05, GOV-06).

Each oracle is built and run through its own build system and drivers, from its pinned commit as
recorded in reports/asset_register.json. The clone under .cache/assets/ is never touched: the
runner exports the pinned tree (git archive) into .cache/oracles/<asset>/work/ and runs there. The
clone's commit, tree hash, content digest and working-tree status are recorded before and after
every run. Every command, exit code and output is kept: the full log under .cache/oracles/<asset>/
logs/ (hashed in the report) and its tail in reports/oracles/<asset>.json and .md.

  python3 -m repsynth oracles run <asset> [--only STEP ...]
  python3 -m repsynth oracles list
assets: hindawi, romenagri, apcisr, ayehandsum
"""
from __future__ import annotations

import argparse
import json
import re
import os
import shutil
import subprocess
import sys
from pathlib import Path

from repsynth.lanes.intake import (CACHE, NOTICE, REPORTS, VERSION, _load_register, _tool_version, _write_json,
                                   _write_text, record, redact, run_cmd, same_state, scrub, tail, tree_state)
import unicodedata
from repsynth.records import ROOT, sha256_file, utc_now

ORACLE_ROOT = CACHE / "oracles"
OUT = REPORTS / "oracles"
SHIM_DIR = ROOT / "oracles"


def _sh(script: str) -> list[str]:
    return ["bash", "-c", script]


# Each step: name, command (run with bash -c in the work tree unless cwd is given relative to it),
# timeout in seconds, and what the step shows. Commands are taken from each asset's own README,
# VERIFY or Makefile, cited in "source".
ORACLES = {
    "hindawi": {
        "slug": "hindawiai/hindawi2026.10",
        "source": "README.md 'Start here'; VERIFY.md steps 1 to 3; scripts/build.sh; scripts/fetch.sh",
        "steps": [
            {"name": "install", "cmd": 'bash install.sh --prefix "$ORACLE_PREFIX"', "timeout": 3600,
             "shows": "the toolchain built from the pinned Chintamani the original way, and Urdu and Telugu quick_sort.c compiled and run"},
            {"name": "doctor", "cmd": "python3 bin/hindawi doctor", "timeout": 600,
             "shows": "every required tool and the Chintamani toolchain"},
            {"name": "test", "cmd": "python3 bin/hindawi test", "timeout": 7200,
             "shows": "the repository's own regression suite (VERIFY.md step 3)"},
            {"name": "chintamani_others", "cmd": "for d in fasm qb2c; do echo \"== $d\"; make -C .build/chintamani/Hindawi/others/$d all || exit $?; done",
             "timeout": 1800,
             "shows": "fasm and qb2c built with their own Makefiles, as Chintamani's install script does (lines 108 to 118); Hindawi's build.sh does not build them"},
            {"name": "shaili_round_trip", "cmd": "bash \"$ORACLE_RUNNERS/hindawi/shaili_round_trip.sh\"", "timeout": 1800,
             "shows": "each built Chintamani shaili transducer, forward (h2X) and reverse (X2h), on the shaili's own Hindi samples"},
        ],
    },
    "romenagri": {
        "slug": "project-ilm/romenagri2026.10",
        "source": "README.md 'Checking it'; tests/run_all.sh",
        "steps": [
            {"name": "make_all", "cmd": "make -C Romenagri all", "timeout": 900,
             "shows": "the patched Romenagri built with its own Makefile"},
            {"name": "run_all", "cmd": 'RMN_BUILD="$ORACLE_SCRATCH/rmn_build" bash tests/run_all.sh', "timeout": 3600,
             "shows": "the package's own quick test suite"},
        ],
    },
    "apcisr": {
        "slug": "hindawiai/chintamani",
        "source": "APCISR/Makefile (targets all, libapcisr, filters); APCISR/test.aci",
        "steps": [
            {"name": "make_all", "cmd": "make -C APCISR all", "timeout": 600,
             "shows": "libapcisr.a and the acii2csr filter built with APCISR's own Makefile"},
            {"name": "render_test_aci", "cmd": "cd APCISR && ./acii2csr < test.aci", "timeout": 120,
             "shows": "the filter run on APCISR's own sample, test.aci"},
        ],
    },
    "ayehandsum": {
        "slug": "ayehandsum/ayehandsum",
        "needs": ["ayevdi/ayevdi"],
        "source": "ayesha (encode, decode, test, test-all); ayehandsum, ayehandsum-test, ayehandsum-test-all; "
                  "AyeVDI ost/ayevdi-sfrom-init and utils/ayevdi-sourcefrom",
        "steps": [
            {"name": "activate_and_test", "cmd": "bash \"$ORACLE_RUNNERS/ayehandsum/run_in_ayevdi.sh\" test", "timeout": 600,
             "shows": "AyeVDI activated from its pinned init; `ayesha test hands` on the input ayeai"},
            {"name": "encode_decode_samples", "cmd": "bash \"$ORACLE_RUNNERS/ayehandsum/run_in_ayevdi.sh\" samples", "timeout": 1800,
             "shows": "ayehandsum encode and decode of the inputs ayeai, ayelearn and ayevdi (the inputs of ayecode-test-all) for every alphabet"},
            {"name": "test_all", "cmd": "bash \"$ORACLE_RUNNERS/ayehandsum/run_in_ayevdi.sh\" test-all", "timeout": 3600,
             "shows": "`ayesha test-all hands`: the author's own test matrix over hash algorithms and inputs"},
        ],
    },
}


def clone_of(reg: dict, slug: str) -> dict:
    for a in reg.get("assets", []):
        for r in a["repositories"]:
            if r["slug"] == slug and r["clone"]["ok"]:
                return r
    raise SystemExit(f"{slug} is not cloned at a pinned commit: run `python3 -m repsynth intake clone` first")


def run_bytes(cmd: list[str], cwd: Path, env: dict, timeout: int, raw_out: Path) -> dict:
    """Run a step keeping its raw standard output bytes (some oracles print code-page bytes)."""
    started = utc_now()
    try:
        p = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, timeout=timeout)
        code, out, err = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired as e:
        code, out, err = 124, e.stdout or b"", (e.stderr or b"") + f"\ntimeout after {timeout} s".encode()
    raw_out.write_bytes(out)
    try:
        text, enc = out.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        text, enc = out.decode("cp437"), "cp437 (not valid UTF-8; shown as code page 437)"
    return {"exit_code": code, "started_utc": started, "finished_utc": utc_now(), "stdout": redact(text),
            "stdout_encoding": enc, "stderr": redact(err.decode("utf-8", "replace"))}


def export_tree(clone: Path, dest: Path) -> dict:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    r = run_cmd(["bash", "-c", f'git --no-optional-locks -C "{clone}" archive --format=tar HEAD | tar -x -C "{dest}"'],
                timeout=1800)
    return {"command": r["command"], "exit_code": r["exit_code"], "stderr_tail": tail(r["stderr"], 5)}


def run_oracle(name: str, only: list[str] | None = None) -> int:
    started = utc_now()
    spec = ORACLES[name]
    reg = _load_register()
    main = clone_of(reg, spec["slug"])
    deps = {s: clone_of(reg, s) for s in spec.get("needs", [])}
    base = ORACLE_ROOT / name
    work, scratch, logs = base / "work", base / "scratch", base / "logs"
    # A full run starts with empty scratch and log folders; a partial run (--only) keeps the other steps' files.
    for d in (scratch, logs):
        if d.exists() and not only:
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)
    states_before = {s: tree_state(Path(c["clone"]["path"])) for s, c in [(spec["slug"], main), *deps.items()]}
    # A full run starts from a fresh export; a partial run (--only) reuses the work tree of the
    # last full run at the same commit, so steps that depend on an earlier step's build can rerun.
    marker = base / "work.commit"
    reuse = bool(only) and work.exists() and marker.exists() and marker.read_text().strip() == main["commit"]
    if reuse:
        exp = {"command": "reused the exported work tree of the last full run", "exit_code": 0, "commit": main["commit"]}
    else:
        exp = export_tree(Path(main["clone"]["path"]), work)
        marker.write_text(main["commit"] + "\n")
    dep_paths = {}
    for s, c in deps.items():
        dp = base / ("dep__" + s.replace("/", "__"))
        if not (reuse and dp.exists()):
            export_tree(Path(c["clone"]["path"]), dp)
        dep_paths[s] = dp
    env = dict(os.environ)
    env.update({"ORACLE_WORK": str(work), "ORACLE_SCRATCH": str(scratch), "ORACLE_PREFIX": str(base / "prefix"),
                "ORACLE_RUNNERS": str(SHIM_DIR), "TMPDIR": str(scratch), "PYTHONDONTWRITEBYTECODE": "1",
                "ORACLE_COMMIT": main["commit"], "LC_ALL": "C.UTF-8"})
    for s, p in dep_paths.items():
        env["ORACLE_DEP_" + s.split("/")[1].upper().replace("-", "_").replace(".", "_")] = str(p)
    env["ORACLE_DEP_AYEHANDSUM_SELF"] = str(work)
    steps = []
    for st in spec["steps"]:
        if only and st["name"] not in only:
            continue
        raw = logs / f"{st['name']}.stdout"
        r = run_bytes(_sh(st["cmd"]), cwd=work, env=env, timeout=st["timeout"], raw_out=raw)
        full = f"$ {st['cmd']}\n# cwd {work}\n# exit {r['exit_code']}\n--- stdout\n{r['stdout']}\n--- stderr\n{r['stderr']}\n"
        lf = logs / f"{st['name']}.log"
        lf.write_text(redact(full), encoding="utf-8")
        steps.append({"name": st["name"], "command": st["cmd"], "cwd": "the exported work tree",
                      "exit_code": r["exit_code"], "started_utc": r["started_utc"], "finished_utc": r["finished_utc"],
                      "shows": st["shows"], "log": str(lf.relative_to(ROOT)), "log_sha256": sha256_file(lf),
                      "log_lines": full.count("\n"), "stdout_raw": str(raw.relative_to(ROOT)),
                      "stdout_raw_sha256": sha256_file(raw), "stdout_encoding": r["stdout_encoding"],
                      "stdout_tail": tail(r["stdout"], 40), "stderr_tail": tail(r["stderr"], 25)})
        print(f"{name}: {st['name']}: exit {r['exit_code']}", file=sys.stderr)
    states_after = {s: tree_state(Path(c["clone"]["path"])) for s, c in [(spec["slug"], main), *deps.items()]}
    unchanged = {s: same_state(states_before[s], states_after[s]) for s in states_before}
    rep = {"_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0", "generator": f"repsynth.lanes.oracles {VERSION}",
           "oracle": name, "repository": spec["slug"], "commit": main["commit"], "tree": main["tree"],
           "dependencies": {s: {"commit": c["commit"], "tree": c["tree"]} for s, c in deps.items()},
           "driver_source": spec["source"], "export": exp,
           "clone_state_before": {s: {k: v for k, v in x.items() if k != "status_lines"} for s, x in states_before.items()},
           "clone_state_after": {s: {k: v for k, v in x.items() if k != "status_lines"} for s, x in states_after.items()},
           "clones_unchanged": unchanged, "steps": steps,
           "machine": "cloud build machine, native run (ops/run.sh --native); the container run is the author's"}
    OUT.mkdir(parents=True, exist_ok=True)
    # Merge with an earlier report so a partial rerun (--only) keeps the other steps' evidence.
    jf = OUT / f"{name}.json"
    if only and jf.exists():
        old = json.loads(jf.read_text())
        kept = [s for s in old.get("steps", []) if s["name"] not in only]
        rep["steps"] = kept + steps
        rep["steps"].sort(key=lambda s: [x["name"] for x in spec["steps"]].index(s["name"]))
    _write_json(jf, rep)
    _write_text(OUT / f"{name}.md", _md(rep))
    ok_clones = all(unchanged.values())
    exit_code = 0 if ok_clones and all(s["exit_code"] == 0 for s in steps) else 1
    rec = record("P0.3", f"oracle_{name}", f"python3 -m repsynth oracles run {name}" + (f" --only {' '.join(only)}" if only else ""),
                 exit_code, started_utc=started, outputs=[jf, OUT / f"{name}.md"],
                 tool_versions={"gcc": _tool_version(["gcc", "--version"]), "flex": _tool_version(["flex", "--version"]),
                                "make": _tool_version(["make", "--version"]), "python": sys.version.split()[0],
                                "bash": _tool_version(["bash", "--version"]), "awk": _tool_version(["awk", "--version"])},
                 results={"commit": main["commit"], "clones_unchanged": unchanged,
                          "steps": {s["name"]: s["exit_code"] for s in steps}},
                 state="wired_unproven",
                 notes="Exit codes are the oracle's own; a non-zero code is reported with its output, not interpreted.")
    print(json.dumps({"record": str(rec), "steps": {s["name"]: s["exit_code"] for s in steps},
                      "clones_unchanged": unchanged}, indent=2))
    return exit_code


def _md(rep: dict) -> str:
    L = [f"<!-- {NOTICE} SPDX-License-Identifier: CC-BY-SA-4.0 -->", "", f"# Oracle run: {rep['oracle']}", "", NOTICE, "",
         f"Repository {rep['repository']} at commit {rep['commit']} (tree {rep['tree']}), exported with git archive and run "
         f"in .cache/oracles/{rep['oracle']}/work/. Driver: {rep['driver_source']}.", "",
         f"Clones unchanged after the run: {', '.join(f'{k}: {v}' for k, v in rep['clones_unchanged'].items())}.", "",
         "| Step | Command | Exit code | Shows |", "|---|---|---|---|"]
    for s in rep["steps"]:
        L.append(f"| {s['name']} | `{s['command']}` | {s['exit_code']} | {s['shows']} |")
    for s in rep["steps"]:
        L += ["", f"## {s['name']}", "", f"`{s['command']}`, exit code {s['exit_code']}. Full log {s['log']} "
              f"(sha256 {s['log_sha256']}, {s['log_lines']} lines).", "", "Standard output, last lines:", "", "```",
              s["stdout_tail"] or "(empty)", "```", "", "Standard error, last lines:", "", "```", s["stderr_tail"] or "(empty)", "```"]
    return "\n".join(L) + "\n"


# --------------------------------------------------------------------------------------------
# P1.5 Romenagri extraction (ORC-03): tables read with the oracle's own reader, every mapping
# confirmed by executing the oracle's own filters; where they disagree the oracle's output is
# the mapping and the disagreement is recorded.
# --------------------------------------------------------------------------------------------

READINGS = REPORTS / "readings"
SPEC_DIR = ROOT / "spec" / "reps"


def _rmn_bin(name: str) -> Path:
    return ORACLE_ROOT / "romenagri" / "work" / "Romenagri" / name


def rmn_pipe(stage: str, data: bytes) -> tuple[int, bytes]:
    """Run one stage of Romenagri's own chain, exactly as the Hindawi drivers chain them."""
    W = ORACLE_ROOT / "romenagri" / "work" / "Romenagri"
    cmds = {"uni2acii": f'iconv -f utf-8 -t utf-16 | "{W}/uni2acii"',
            "acii2uni": f'"{W}/acii2uni" | iconv -f utf-16 -t utf-8',
            "acii2rmn": f'"{W}/acii2rmn"', "rmn2acii": f'"{W}/rmn2acii"'}
    p = subprocess.run(["bash", "-c", cmds[stage]], input=data, capture_output=True, timeout=300)
    return p.returncode, p.stdout


def _lines_through(stage: str, items: list[bytes]) -> tuple[int, list[bytes]]:
    code, out = rmn_pipe(stage, b"\n".join(items) + b"\n")
    parts = out.split(b"\n")
    return code, parts[:len(items)]


def romenagri_observe(uni_rows, acii_rows) -> dict:
    cps = [chr(c).encode("utf-8") for c, _ in uni_rows]
    e1, to_acii = _lines_through("uni2acii", cps)
    e2, back_uni = _lines_through("acii2uni", [bytes([b]) for _, b in uni_rows])
    keys = [k.encode("latin-1") for k, _ in acii_rows]
    e3, k_to_acii = _lines_through("rmn2acii", keys)
    e4, acii_to_k = _lines_through("acii2rmn", [b for _, b in acii_rows])
    return {"exit_codes": {"uni2acii": e1, "acii2uni": e2, "rmn2acii": e3, "acii2rmn": e4},
            "uni2acii": to_acii, "acii2uni": back_uni, "rmn2acii": k_to_acii, "acii2rmn": acii_to_k}


def extract_romenagri() -> dict:
    started = utc_now()
    reg = _load_register()
    main = clone_of(reg, "project-ilm/romenagri2026.10")
    W = ORACLE_ROOT / "romenagri" / "work"
    marker = ORACLE_ROOT / "romenagri" / "work.commit"
    if not (_rmn_bin("uni2acii").exists() and marker.exists() and marker.read_text().strip() == main["commit"]):
        raise SystemExit("run `python3 -m repsynth oracles run romenagri` first: the built filters at the pinned commit are needed")
    sys.path.insert(0, str(W / "tools"))
    import rmn_tables  # the oracle's own table reader, used read-only
    sys.path.pop(0)
    _, uni = rmn_tables.parse_unicode(str(W / "Romenagri"))
    _, acii = rmn_tables.parse_acii(str(W / "Romenagri"))
    obs = romenagri_observe(uni, acii)
    u_map, a_map, disagreements = [], [], []
    for (cp, b), got, back in zip(uni, obs["uni2acii"], obs["acii2uni"]):
        row = {"unicode": f"U+{cp:04X}", "name": unicodedata.name(chr(cp), "UNNAMED"), "acii": f"{b:02x}",
               "observed_uni2acii": got.hex(), "observed_acii2uni": back.decode("utf-8", "replace")}
        if got != bytes([b]):
            disagreements.append({"table": "unicode.h", "entry": row["unicode"], "table_value": row["acii"],
                                  "oracle_output": got.hex(), "resolution": "the oracle's output is the mapping"})
            row["acii"] = got.hex()
        row["inverse_exact"] = back.decode("utf-8", "replace") == chr(cp)
        u_map.append(row)
    for (k, bs), got_b, got_k in zip(acii, obs["rmn2acii"], obs["acii2rmn"]):
        row = {"romenagri": k, "acii": bs.hex(), "observed_rmn2acii": got_b.hex(),
               "observed_acii2rmn": got_k.decode("latin-1")}
        row["forward_exact"] = got_b == bs
        row["reverse_exact"] = got_k.decode("latin-1") == k
        if not row["forward_exact"] or not row["reverse_exact"]:
            disagreements.append({"table": "acii.h", "entry": k, "table_value": bs.hex(),
                                  "oracle_rmn2acii": got_b.hex(), "oracle_acii2rmn": got_k.decode("latin-1"),
                                  "resolution": "recorded; the spec states the oracle's outputs as observed_*"})
        a_map.append(row)
    # Corpus: the package's own Hindi corpus through the whole chain and back (ORC-02).
    corpus = []
    for name in ("corp_hi.txt", "corp_hi_nums.txt", "test_hi.txt"):
        f = W / "Romenagri" / name
        if not f.exists():
            continue
        raw = f.read_bytes()
        try:
            raw.decode("utf-8")
        except UnicodeDecodeError:
            corpus.append({"file": name, "state": "not UTF-8; not used"})
            continue
        lines = [l for l in raw.replace(b"\r", b"").split(b"\n") if l.strip()]
        _, a1 = _lines_through("uni2acii", lines)
        _, r1 = _lines_through("acii2rmn", a1)
        _, a2 = _lines_through("rmn2acii", r1)
        _, u2 = _lines_through("acii2uni", a2)
        same = sum(1 for x, y in zip(lines, u2) if x == y)
        same_cr = sum(1 for x, y in zip(lines, u2) if x == y.rstrip(b"\r"))
        corpus.append({"file": f"Romenagri/{name}", "sha256": sha256_file(f), "lines": len(lines), "round_trip_exact": same,
                       "round_trip_equal_apart_from_a_trailing_cr": same_cr,
                       "note": "acii2uni ends each line with CR LF; the input lines were compared without their CR",
                       "first_differences": [{"in": x.decode("utf-8", "replace")[:80], "out": y.decode("utf-8", "replace")[:80]}
                                             for x, y in zip(lines, u2) if x != y.rstrip(b"\r")][:8]})
    reading = {"_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0", "generator": f"repsynth.lanes.oracles {VERSION}",
               "oracle": {"repository": "project-ilm/romenagri2026.10", "commit": main["commit"], "tree": main["tree"],
                          "tables": {n: sha256_file(W / "Romenagri" / n) for n in ("unicode.h", "acii.h", "aciihin.h")},
                          "reader_reused": {"path": "tools/rmn_tables.py", "sha256": sha256_file(W / "tools" / "rmn_tables.py")}},
               "exit_codes": obs["exit_codes"], "unicode_to_acii": u_map, "acii_to_romenagri": a_map,
               "disagreements": disagreements, "corpus": corpus}
    READINGS.mkdir(parents=True, exist_ok=True)
    _write_json(READINGS / "romenagri.json", reading)
    spec = romenagri_spec(reading)
    out = SPEC_DIR / "transliteration" / "romenagri_devanagari.yaml"
    _write_yaml(out, spec)
    return {"reading": reading, "spec_path": out, "started": started}


def _write_yaml(path: Path, obj) -> None:
    import yaml
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(scrub(obj), sort_keys=False, allow_unicode=True, width=120)
    path.write_text(text, encoding="utf-8")


def romenagri_spec(r: dict) -> dict:
    o = r["oracle"]
    src = f"project-ilm/romenagri2026.10@{o['commit']}"
    return {
        "_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0",
        "identity": {"id": "romenagri_devanagari", "version": "0.3.0", "family": "transliteration",
                     "title": "Romenagri: Devanagari through ACII to ASCII-7 Romenagri, as the 2026.10 oracle behaves",
                     "equality": "Two texts are equal when their byte sequences in the stated form (UTF-8, ACII or Romenagri) are equal.",
                     "canonical_form": "Unicode text in NFC is not assumed; the oracle's input is UTF-16 from iconv, as the Hindawi drivers feed it."},
        "domain": {"description": "The 85 Unicode code points of Romenagri/unicode.h and the 96 Romenagri keys of Romenagri/acii.h.",
                   "finite": True, "enumerator": "The rows of encoding.unicode_to_acii and encoding.acii_to_romenagri, in table order."},
        "structure": {"chain": ["UTF-8 text", "UTF-16 (iconv)", "ACII bytes (uni2acii)", "Romenagri ASCII (acii2rmn)"],
                      "inverse_chain": ["Romenagri ASCII", "ACII bytes (rmn2acii, a recursive-descent parser)",
                                        "UTF-16 (acii2uni)", "UTF-8 text (iconv)"],
                      "tables": {"unicode.h": "code point to ACII byte", "acii.h": "Romenagri key to ACII bytes",
                                 "aciihin.h": "ACII to saral rendering (not used by this specification)"}},
        "encoding": {"unicode_to_acii": [{"unicode": x["unicode"], "name": x["name"], "acii": x["acii"]} for x in r["unicode_to_acii"]],
                     "acii_to_romenagri": [{"acii": x["acii"], "table_key": x["romenagri"],
                                            "oracle_acii2rmn": x["observed_acii2rmn"]} for x in r["acii_to_romenagri"]]},
        "decoding": {"romenagri_to_acii": [{"romenagri": x["romenagri"], "oracle_rmn2acii": x["observed_rmn2acii"]}
                                           for x in r["acii_to_romenagri"]],
                     "acii_to_unicode": [{"acii": x["acii"], "oracle_acii2uni": x["observed_acii2uni"]} for x in r["unicode_to_acii"]],
                     "error_behaviour": "As the oracle: uni2acii writes the low byte of any code point it has no row for "
                                        "(README 'What was found on the way'); this specification does not cover those inputs."},
        "semantics": {"statement": "Romenagri is defined by its implementation; each mapping here is what the oracle's filters "
                                   "output for the isolated element, one per line.",
                      "reference_sources": ["reports/readings/romenagri.json", "repsynth/lanes/oracles.py"],
                      "oracle_sources": [f"{src}:Romenagri/uni2acii.c", f"{src}:Romenagri/acii2uni.c",
                                         f"{src}:Romenagri/acii2rmn.c", f"{src}:Romenagri/rmn2acii.c"],
                      "oracle": f"{src}, filters built with Romenagri/Makefile"},
        "operations": [],
        "composition": {"rule": "Words compose by the parser of rmn2acii; its grammar is TRANSLITERATION.md section 5.3 of the oracle."},
        "transformations": [{"name": "to_romenagri", "to": "romenagri_ascii", "preserves": "text, lossless on the domain where inverse_exact holds"},
                            {"name": "to_unicode", "to": "unicode_devanagari", "preserves": "text, as observed in decoding"}],
        "constraints": [{"name": "in_domain", "statement": "Only code points listed in encoding.unicode_to_acii are covered."}],
        "substrate": {"logical": "other", "register_widths": []},
        "interfaces": {"imports": [], "exports": ["Romenagri forms used by Hindawi's compiler front end"]},
        "verification": {"properties": [
            {"name": "table_reproduced", "method": "python3 -m repsynth oracles check romenagri: executes uni2acii, acii2uni, "
                                                   "rmn2acii and acii2rmn on every row and compares with this file"},
            {"name": "corpus_round_trip", "method": "the oracle's own Hindi corpus through the whole chain and back; counts recorded in reports/readings/romenagri.json"}]},
        "generation": {"software": "none: the legacy source stays the implementation (GEN-01)"},
        "evolution": {"changes": [{"version": "0.3.0", "class": "initial", "summary": "Extracted from Romenagri 2026.10"}]},
        "provenance": {"oracle": {"value": src, "evidence": "measured", "source": "reports/readings/romenagri.json"},
                       "extraction": "Tables read with the oracle's own reader tools/rmn_tables.py; every row confirmed by "
                                     "executing the oracle's filters; disagreements recorded in the reading, the oracle winning.",
                       "evidence_state": "extracted"},
    }


def check_romenagri(spec_path: Path) -> dict:
    """Acceptance for P1.5: execute the oracle on every mapping of the specification."""
    import yaml
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    enc, dec = spec["encoding"], spec["decoding"]
    uni = [(int(x["unicode"][2:], 16), int(x["acii"], 16)) for x in enc["unicode_to_acii"]]
    keys = [x["romenagri"] for x in dec["romenagri_to_acii"]]
    acii_rows = [(k, bytes.fromhex(x["acii"])) for k, x in zip(keys, enc["acii_to_romenagri"])]
    obs = romenagri_observe(uni, acii_rows)
    bad = []
    for (cp, b), got in zip(uni, obs["uni2acii"]):
        if got != bytes([b]):
            bad.append(f"uni2acii U+{cp:04X}: spec {b:02x}, oracle {got.hex()}")
    for x, got in zip(dec["acii_to_unicode"], obs["acii2uni"]):
        if got.decode("utf-8", "replace") != x["oracle_acii2uni"]:
            bad.append(f"acii2uni {x['acii']}: spec {x['oracle_acii2uni']!r}, oracle {got.decode('utf-8', 'replace')!r}")
    for x, got in zip(dec["romenagri_to_acii"], obs["rmn2acii"]):
        if got.hex() != x["oracle_rmn2acii"]:
            bad.append(f"rmn2acii {x['romenagri']!r}: spec {x['oracle_rmn2acii']}, oracle {got.hex()}")
    for x, got in zip(enc["acii_to_romenagri"], obs["acii2rmn"]):
        if got.decode("latin-1") != x["oracle_acii2rmn"]:
            bad.append(f"acii2rmn {x['acii']}: spec {x['oracle_acii2rmn']!r}, oracle {got.decode('latin-1')!r}")
    n = len(uni) * 2 + len(acii_rows) * 2
    return {"mappings_checked": n, "mismatches": bad, "exit_codes": obs["exit_codes"]}


# --------------------------------------------------------------------------------------------
# P1.6 APCISR Devanagari grid (ORC-03): the chart read from apcisr.h as data; every cell assignment
# confirmed by executing acii2cisr() through the author's traced build, which records the working map.
# --------------------------------------------------------------------------------------------

APCISR_TRACE_DIR = ORACLE_ROOT / "apcisr" / "trace"
ROW_NAMES, COL_NAMES = ("urdha", "madhya", "nimna"), ("matrik", "lipik", "purak")


def _strip_trace(text: str) -> str:
    return "\n".join(l for l in text.replace("\r", "").split("\n")
                     if "APCISR_TRACE" not in l and '#include "trace_apcisr.h"' not in l)


def build_apcisr_trace() -> dict:
    """Build the chart dumper and the trace driver from the author's traced sources, after showing that those
    sources are the pinned APCISR's apart from the trace lines."""
    src = ORACLE_ROOT / "hindawi" / "work" / "docs" / "trace" / "apcisr" / "src"
    orig = ORACLE_ROOT / "apcisr" / "work" / "APCISR"
    if not src.exists() or not orig.exists():
        raise SystemExit("run `oracles run hindawi` and `oracles run apcisr` first")
    same = {}
    for f in ("apcisr.h", "cisr2asc.h", "acii2csr.h"):
        same[f] = (src / f).read_bytes() == (orig / f).read_bytes()
    same["acii2csr.c (trace lines removed, CR ignored)"] = (
        _strip_trace((src / "acii2csr.c").read_text("latin-1")) == _strip_trace((orig / "acii2csr.c").read_text("latin-1")))
    if not all(same.values()):
        raise SystemExit(f"the traced sources differ from the pinned APCISR beyond the trace lines: {same}")
    if APCISR_TRACE_DIR.exists():
        shutil.rmtree(APCISR_TRACE_DIR)
    shutil.copytree(src, APCISR_TRACE_DIR)
    b1 = run_cmd(["gcc", "-w", "-O0", "-I", ".", "-o", "dump_chart", str(SHIM_DIR / "apcisr" / "dump_chart.c")],
                 cwd=APCISR_TRACE_DIR, timeout=300)
    b2 = run_cmd(["gcc", "-w", "-O0", "-I", ".", "-o", "trace_drv", str(SHIM_DIR / "apcisr" / "trace_drv.c"), "acii2csr.c"],
                 cwd=APCISR_TRACE_DIR, timeout=300)
    if b1["exit_code"] or b2["exit_code"]:
        raise SystemExit(f"build failed: {b1['stderr']}{b2['stderr']}")
    return {"identical_to_pinned_apart_from_trace_lines": same,
            "builds": [{"command": b["command"], "exit_code": b["exit_code"]} for b in (b1, b2)]}


def apcisr_chart() -> list[dict]:
    r = run_cmd([str(APCISR_TRACE_DIR / "dump_chart")], timeout=60)
    return [json.loads(l) for l in r["stdout"].splitlines() if l.strip()]


def apcisr_trace(inputs: list[str]) -> list[dict]:
    p = subprocess.run([str(APCISR_TRACE_DIR / "trace_drv")], input="\n".join(inputs) + "\n", capture_output=True,
                       text=True, timeout=600)
    return [json.loads(l) for l in p.stdout.splitlines() if l.strip()]


BASE_CONSONANT = "b3"  # ACII for DEVANAGARI LETTER KA: the carrier for signs (purna 0) when run in isolation


def _cells(final: dict) -> list[list[int]]:
    cur = [final["matrik"], final["lipik"], final["purak"]]
    wm = final["wm"]
    return [[(wm[c][r] if c < len(wm) else 0) for c in cur] for r in range(3)]


def apcisr_observe(chart: list[dict]) -> list[dict]:
    inputs = [(row["acii"] if row["purna"] else BASE_CONSONANT + row["acii"]) for row in chart]
    traces = apcisr_trace(inputs)
    out = []
    for row, inp, tr in zip(chart, inputs, traces):
        final = tr["trace"][-1]
        cells = _cells(final)
        grid = [row["grid"][0:3], row["grid"][3:6], row["grid"][6:9]]
        contained = all((cells[r][c] & grid[r][c]) == grid[r][c] for r in range(3) for c in range(3))
        out.append({"input": inp, "cursors": {"matrik": final["matrik"], "lipik": final["lipik"], "purak": final["purak"]},
                    "observed_cells": cells, "grid_bits_present": contained, "entry_seen": final["entry"]})
    return out


def extract_apcisr() -> dict:
    started = utc_now()
    reg = _load_register()
    chint = clone_of(reg, "hindawiai/chintamani")
    hind = clone_of(reg, "hindawiai/hindawi2026.10")
    build = build_apcisr_trace()
    chart = apcisr_chart()
    obs = apcisr_observe(chart)
    rows, disagreements = [], []
    for row, o in zip(chart, obs):
        grid = [row["grid"][0:3], row["grid"][3:6], row["grid"][6:9]]
        rows.append({"index": row["index"], "romenagri": row["rmn"], "acii": row["acii"], "purna": row["purna"],
                     "grid": grid, "run_input": o["input"], "observed_cells": o["observed_cells"],
                     "rule_governed": not o["grid_bits_present"]})
        if not o["grid_bits_present"]:
            disagreements.append({"index": row["index"], "romenagri": row["rmn"], "acii": row["acii"], "grid": grid,
                                  "observed_cells": o["observed_cells"],
                                  "resolution": "a dynamic rule of acii2cisr() places this entry (grid_job = 0); "
                                                "the observed cells are the oracle's and stand"})
    # Corpus: APCISR's own sample test.aci, every token step checked.
    corpus = []
    ta = ORACLE_ROOT / "apcisr" / "work" / "APCISR" / "test.aci"
    lines = [l for l in ta.read_bytes().replace(b"\r", b"").split(b"\n") if l]
    rule_entries = {r["index"] for r in rows if r["rule_governed"]}
    steps = ok = skipped = 0
    absent = []
    for tr in apcisr_trace([l.hex() for l in lines]):
        recs = tr["trace"]
        for k in range(1, len(recs)):
            e = recs[k]["entry"]
            if not (0 <= e < len(chart)) or not recs[k]["flag"]:
                continue
            steps += 1
            if e in rule_entries or recs[k]["prev_hal"] or recs[k - 1]["prev_hal"]:
                skipped += 1
                continue
            cells = _cells(recs[k])
            g = chart[e]["grid"]
            if all((cells[r][c] & g[r * 3 + c]) == g[r * 3 + c] for r in range(3) for c in range(3)):
                ok += 1
            else:
                absent.append({"input": tr["input"], "step": k, "entry": e, "romenagri": chart[e]["rmn"],
                               "grid": g, "cells_at_cursors": cells, "cursors": [recs[k]["matrik"], recs[k]["lipik"], recs[k]["purak"]]})
    corpus.append({"file": "APCISR/test.aci", "sha256": sha256_file(ta), "lines": len(lines), "token_steps": steps,
                   "grid_bits_present": ok, "not_checked_rule_or_conjunct_context": skipped,
                   "grid_bits_absent": len(absent), "absent_steps": absent})
    reading = {"_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0", "generator": f"repsynth.lanes.oracles {VERSION}",
               "oracle": {"repository": "hindawiai/chintamani", "commit": chint["commit"], "tree": chint["tree"],
                          "path": "APCISR/", "apcisr_h_sha256": sha256_file(ORACLE_ROOT / "apcisr" / "work" / "APCISR" / "apcisr.h")},
               "traced_build": {"repository": "hindawiai/hindawi2026.10", "commit": hind["commit"],
                                "path": "docs/trace/apcisr/src", **build,
                                "drivers": {"oracles/apcisr/dump_chart.c": sha256_file(SHIM_DIR / "apcisr" / "dump_chart.c"),
                                            "oracles/apcisr/trace_drv.c": sha256_file(SHIM_DIR / "apcisr" / "trace_drv.c")}},
               "chart_rows": len(chart), "rows": rows, "disagreements": disagreements, "corpus": corpus}
    READINGS.mkdir(parents=True, exist_ok=True)
    _write_json(READINGS / "apcisr.json", reading)
    out = SPEC_DIR / "script" / "apcisr_devanagari.yaml"
    _write_yaml(out, apcisr_spec(reading))
    return {"reading": reading, "spec_path": out, "started": started}


def apcisr_spec(r: dict) -> dict:
    o = r["oracle"]
    src = f"hindawiai/chintamani@{o['commit']}"
    return {
        "_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0",
        "identity": {"id": "apcisr_devanagari", "version": "0.3.0", "family": "script_structure",
                     "title": "APCISR 9-grid instance for Devanagari, as the oracle's chart and acii2cisr() define it",
                     "equality": "Two renditions are equal when their working maps (urdha, madhya, nimna per column) are equal.",
                     "canonical_form": {"not_established": "APCISR defines no canonical form of a rendition; P6.1 asks the author"}},
        "domain": {"description": f"The {r['chart_rows']} entries of apcisr_chrt (APCISR/apcisr.h), keyed by ACII byte sequences.",
                   "finite": True, "enumerator": "encoding.grid_table in chart order (lookup takes the first entry whose ACII prefixes the input)."},
        "structure": {"grid": {"rows": list(ROW_NAMES), "columns": list(COL_NAMES),
                               "row_offsets": {"urdha": 0, "madhya": 3, "nimna": 6}, "column_offsets": {"matrik": 0, "lipik": 1, "purak": 2},
                               "source": f"{src}:APCISR/apcisr.h, static ints _urdha, _madhya, _nimna, _matrik, _lipik, _purak"},
                      "cell": "An 8-bit value; its bits select glyph parts that the font substitution (cisr2asc.h) maps to "
                              "the code points of devnagri.f08 and devnagri.f16.",
                      "purna": "0: a sign that joins the current varna; 1 and 2: a new varna (values as in the chart)"},
        "encoding": {"grid_table": [{"index": x["index"], "romenagri": x["romenagri"], "acii": x["acii"], "purna": x["purna"],
                                     "grid": x["grid"], "run_input": x["run_input"], "observed_cells": x["observed_cells"],
                                     "rule_governed": x["rule_governed"]} for x in r["rows"]]},
        "decoding": {"inverse": {"not_established": "APCISR renders and does not decode; the inverse is outside the oracle"}},
        "semantics": {"statement": "Each chart entry ORs its nine grid values into the working map at the current matrik, "
                                   "lipik and purak columns, unless a dynamic rule of acii2cisr() places it (rule_governed).",
                      "reference_sources": ["reports/readings/apcisr.json", "repsynth/lanes/oracles.py"],
                      "oracle_sources": [f"{src}:APCISR/apcisr.h", f"{src}:APCISR/acii2csr.c", f"{src}:APCISR/cisr2asc.h"],
                      "oracle": f"{src}, APCISR/Makefile; traced build from hindawiai/hindawi2026.10 docs/trace/apcisr/src"},
        "operations": [],
        "composition": {"rule": "acii2cisr(): cursor rules for purna entries, delayed hal, ra+hal, and the special rules "
                                "listed in reports/readings/apcisr_9grid_reading.md"},
        "transformations": [{"name": "render", "to": "apcisr_font_codes", "preserves": "cluster boundaries as columns (to be measured at P6.4)"}],
        "constraints": [{"name": "chart_lookup", "statement": "Input bytes with no chart entry are rendered as non-ISCII (madhya 192)."}],
        "substrate": {"logical": "other", "register_widths": []},
        "interfaces": {"imports": ["romenagri_devanagari (ACII bytes)"], "exports": ["working map for text-mode rendering"]},
        "verification": {"properties": [
            {"name": "cells_reproduced", "method": "python3 -m repsynth oracles check apcisr: the chart re-read and every entry re-run "
                                                   "through the traced acii2cisr(); observed cells must equal this file"},
            {"name": "corpus", "method": "APCISR/test.aci token by token; counts in reports/readings/apcisr.json"}]},
        "generation": {"apcisr_tables": {"not_established": "generation of grid tables for other scripts starts at P6.3, after the author confirms the reading (P6.1)"}},
        "evolution": {"changes": [{"version": "0.3.0", "class": "initial", "summary": "Extracted from APCISR in hindawiai/chintamani"}]},
        "provenance": {"oracle": {"value": src + ":APCISR/", "evidence": "measured", "source": "reports/readings/apcisr.json"},
                       "extraction": "Chart dumped from apcisr.h by oracles/apcisr/dump_chart.c; cells observed through the "
                                     "author's traced build of acii2cisr(); disagreements recorded, the oracle winning.",
                       "evidence_state": "extracted"},
    }


def check_apcisr(spec_path: Path) -> dict:
    import yaml
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    build_apcisr_trace()
    chart = {r["index"]: r for r in apcisr_chart()}
    rows = spec["encoding"]["grid_table"]
    traces = apcisr_trace([x["run_input"] for x in rows])
    bad = []
    for x, tr in zip(rows, traces):
        c = chart.get(x["index"])
        flat = [v for rr in x["grid"] for v in rr]
        if not c or c["acii"] != x["acii"] or c["grid"] != flat or c["purna"] != x["purna"]:
            bad.append(f"entry {x['index']} ({x['romenagri']}): spec differs from the oracle's chart")
        cells = _cells(tr["trace"][-1])
        if cells != x["observed_cells"]:
            bad.append(f"entry {x['index']} ({x['romenagri']}): oracle cells {cells}, spec {x['observed_cells']}")
        contained = all((cells[r][k] & x["grid"][r][k]) == x["grid"][r][k] for r in range(3) for k in range(3))
        if contained == x["rule_governed"]:
            bad.append(f"entry {x['index']} ({x['romenagri']}): rule_governed {x['rule_governed']} but grid bits present {contained}")
    return {"mappings_checked": len(rows) * 9, "mismatches": bad, "exit_codes": {}}


def _mutate_apcisr(spec: dict) -> str:
    row = next(x for x in spec["encoding"]["grid_table"] if not x["rule_governed"] and x["grid"][1][1])
    row["grid"][1][1] ^= 1
    return f"entry {row['index']} madhya-lipik changed to {row['grid'][1][1]}"


# --------------------------------------------------------------------------------------------
# P1.7 AyeHandSum (ORC-03): the encoding rules read from ayecode-config and ayecode-encode, the
# alphabets read by sourcing each ayecode-base-* file as ayesha does; every rule confirmed by
# re-encoding the oracle's corpus from the extracted rules and comparing with the oracle's output.
# --------------------------------------------------------------------------------------------

AYE_SRC = "ayehandsum/ayehandsum"


def aye_alphabet(work: Path, name: str) -> dict:
    f = work / f"ayecode-base-{name}"
    text = f.read_text(encoding="utf-8", errors="replace")
    base_lines = [l for l in text.splitlines() if l.lstrip().startswith("base=")]
    if any("curl" in l or "wget" in l for l in base_lines):
        return {"alphabet": name, "state": "not established: the alphabet is fetched from the network at run time "
                                             "(unpinned)", "fetch_lines": [l.strip()[:200] for l in text.splitlines()
                                                                          if l.lstrip().startswith("base=") and ("curl" in l or "wget" in l)][:3]}
    env = dict(os.environ, HOME=str(ORACLE_ROOT / "ayehandsum" / "scratch" / "home"))
    env["ayevdi_sourcefrom"] = env["HOME"] + "/.ayevdi/ayevdi-sourcefrom"
    p = subprocess.run(["bash", "-c", f'source "{f}" >/dev/null; printf "%s" "$base"'], capture_output=True, env=env, timeout=60)
    base = p.stdout.decode("utf-8")
    # ayecode-config: symbols=$(echo ${base} | awk '{print NF}') -- word splitting of the unquoted expansion
    words = base.split()
    return {"alphabet": name, "state": "read", "exit_code": p.returncode, "symbols": len(words), "base_words": words}


def bc_digits(value: int, obase: int) -> str:
    """bc's output of value in obase: for obase <= 16 the hex digits 0-9A-F; above, each digit as a
    zero-padded decimal of the width of obase-1, each preceded by a space."""
    if value == 0:
        return "0" if obase <= 16 else " " + "0" * len(str(obase - 1))
    ds = []
    while value:
        ds.append(value % obase)
        value //= obase
    ds.reverse()
    if obase <= 16:
        return "".join("0123456789ABCDEF"[d] for d in ds)
    w = len(str(obase - 1))
    return "".join(" " + str(d).zfill(w) for d in ds)


def awk_num(s: str) -> int:
    m = re.match(r"\s*[+-]?\d+", s)
    return int(m.group(0)) if m else 0


def aye_rules(alpha: dict, hash_hex_len: int) -> dict:
    n = alpha["symbols"]
    nb = n - 2
    terms = len(bc_digits(4294967295, nb).split()) if nb > 0 else 0
    codewidth = len("symbols")  # ayecode-config: codewidth=$(echo symbols | awk '{print length($1)}'), the literal word
    symbols = [w.replace("#", "") for w in alpha["base_words"]]  # ayecode-encode: $(cat | tr -d '#\n')
    index_of = {n - 1 - k: symbols[k] for k in range(n)}         # cntr counts down from symbols-1
    return {"symbols": n, "digit_base": nb, "terms_per_word": terms, "codewidth": codewidth,
            "words": hash_hex_len // 8, "pad_index": n - 1, "pad_symbol": index_of.get(n - 1),
            "unused_index": n - 2, "index_to_symbol": index_of}


def aye_encode(rules: dict, digest_hex: str) -> str:
    """The encoder's pipeline, step by step, from the extracted rules."""
    nb, tl, cw = rules["digit_base"], rules["terms_per_word"], rules["codewidth"]
    lines = []
    for n in range(rules["words"]):
        fields = bc_digits(int(digest_hex[n * 8:(n + 1) * 8], 16), nb).split()
        out = ""
        nf = len(fields)
        k = nf
        while k < tl:                      # awk: pad with symbols-1 up to terms fields
            out += " " + str(nb + 1).zfill(cw)
            k += 1
        for f in fields:
            out += " " + str(awk_num(f)).zfill(cw)
        lines.append(out)
    text = re.sub(" +", " ", "\n".join(lines) + "\n")          # tr -s ' '
    for idx in sorted(rules["index_to_symbol"], reverse=True):  # sed script, in base order
        sym = rules["index_to_symbol"][idx]
        if sym is None:
            continue
        text = text.replace(str(idx).zfill(cw), sym.replace("\\", "").replace("&", str(idx).zfill(cw)))
    return text.replace("\n", "").replace(" ", "")


def _aye_samples() -> list[dict]:
    rep = json.loads((OUT / "ayehandsum.json").read_text())
    step = next((s for s in rep["steps"] if s["name"] == "encode_decode_samples"), None)
    if not step or step["exit_code"] != 0:
        raise SystemExit("run `oracles run ayehandsum` first: the oracle's samples are the corpus")
    raw = (ROOT / step["stdout_raw"]).read_text(encoding="utf-8")
    rows = []
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) == 6 and parts[0] != "alphabet":
            rows.append(dict(zip(["alphabet", "input", "encoded", "decoded", "sha3_256", "decoded_equals_digest"], parts)))
    return rows, step


def extract_ayehandsum() -> dict:
    started = utc_now()
    reg = _load_register()
    main = clone_of(reg, AYE_SRC)
    work = ORACLE_ROOT / "ayehandsum" / "work"
    samples, step = _aye_samples()
    names = sorted({r["alphabet"] for r in samples})
    alphabets, results = [], []
    for name in names:
        a = aye_alphabet(work, name)
        if a["state"] == "read":
            a["rules"] = aye_rules(a, 64)
        alphabets.append(a)
    for r in samples:
        a = next(x for x in alphabets if x["alphabet"] == r["alphabet"])
        if a["state"] != "read":
            results.append({**r, "rules_reproduce_oracle": "not established: alphabet not pinned"})
            continue
        mine = aye_encode(a["rules"], r["sha3_256"])
        results.append({**r, "encoded_from_rules": mine, "rules_reproduce_oracle": mine == r["encoded"]})
    reading = {"_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0", "generator": f"repsynth.lanes.oracles {VERSION}",
               "oracle": {"repository": AYE_SRC, "commit": main["commit"], "tree": main["tree"],
                          "driver": "ayesha encode|decode <alphabet>, inside AyeVDI (oracles/ayehandsum/run_in_ayevdi.sh)",
                          "corpus": {"source": step["stdout_raw"], "sha256": step["stdout_raw_sha256"],
                                     "inputs": "ayeai, ayelearn, ayevdi (the inputs of ayecode-test-all)"}},
               "rules_read_from": {"ayecode-config": sha256_file(work / "ayecode-config"),
                                   "ayecode-encode": sha256_file(work / "ayecode-encode"),
                                   "ayecode-decode": sha256_file(work / "ayecode-decode")},
               "alphabets": alphabets, "results": results}
    READINGS.mkdir(parents=True, exist_ok=True)
    _write_json(READINGS / "ayehandsum.json", reading)
    out = SPEC_DIR / "numeric" / "ayehandsum.yaml"
    _write_yaml(out, ayehandsum_spec(reading))
    return {"reading": {"disagreements": [x for x in results if x["rules_reproduce_oracle"] is False],
                        "exit_codes": {}, "corpus": []}, "spec_path": out, "started": started}


def ayehandsum_spec(r: dict) -> dict:
    o = r["oracle"]
    src = f"{AYE_SRC}@{o['commit']}"
    pinned = [a for a in r["alphabets"] if a["state"] == "read"]
    return {
        "_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0",
        "identity": {"id": "ayehandsum", "version": "0.3.0", "family": "numeric",
                     "title": "AyeHandSum (AyeCode): a hash digest written in a dynamic base over a chosen alphabet",
                     "equality": "Two encodings are equal when their strings are equal; they are equal exactly when the digests are.",
                     "canonical_form": "The encoder's output: no separators, every 32-bit word written with terms_per_word symbols."},
        "domain": {"description": "Digests of the hash named by algo (default sha3sum -a 256: 64 hexadecimal digits, 8 words of 32 bits).",
                   "finite": True, "enumerator": "All 256-bit values; the corpus uses the digests of ayeai, ayelearn and ayevdi."},
        "structure": {"word": "8 hexadecimal digits of the digest, in order (awk substr((n-1)*8+1, 8))",
                      "digit_base": "symbols - 2 (ayecode-config and ayecode-encode: obase=symbols-2)",
                      "terms_per_word": "the number of base-(symbols-2) digits of 4294967295 as bc prints them",
                      "padding": "each word is left-padded to terms_per_word digits with the value symbols-1",
                      "codewidth": "7, the length of the literal word 'symbols' (ayecode-config computes length of the word, not of a variable)"},
        "encoding": {"alphabets": [{"alphabet": a["alphabet"], "symbols": a["rules"]["symbols"],
                                    "digit_base": a["rules"]["digit_base"], "terms_per_word": a["rules"]["terms_per_word"],
                                    "pad_symbol": a["rules"]["pad_symbol"],
                                    "symbols_by_index": [a["rules"]["index_to_symbol"][i] for i in range(a["rules"]["symbols"])]}
                                   for a in pinned],
                     "not_pinned": [{"alphabet": a["alphabet"], "reason": a["state"]} for a in r["alphabets"] if a["state"] != "read"],
                     "symbol_order": "the first symbol of the base list has index symbols-1 (the padding), the last has index 0; "
                                     "index symbols-2 never occurs as a digit"},
        "decoding": {"rule": "ayecode-decode: symbols back to indices (longest symbols first), padding dropped, "
                             "each word read in base symbols-2 and printed as 8 hexadecimal digits"},
        "semantics": {"statement": "A reversible writing of a digest: decode(encode(d)) = d for every pinned alphabet in the corpus.",
                      "reference_sources": ["reports/readings/ayehandsum.json", "repsynth/lanes/oracles.py"],
                      "oracle_sources": [f"{src}:ayesha", f"{src}:ayecode-config", f"{src}:ayecode-encode", f"{src}:ayecode-decode"],
                      "oracle": f"{src} inside AyeVDI (ayevdi/ayevdi, pinned)"},
        "operations": [],
        "composition": {"words": "Words are written one after another with no separator."},
        "transformations": [{"name": "decode", "to": "digest", "preserves": "the digest, lossless for the 12 pinned alphabets on the corpus"}],
        "constraints": [{"name": "large_base", "statement": "The rules assume symbols - 2 > 16 (bc prints digits as decimals above base 16)."}],
        "substrate": {"logical": "other", "register_widths": [{"digits": 8, "register_bits": 32}]},
        "interfaces": {"imports": ["a hash command (sha3sum, shasum, md5sum)"], "exports": ["the encoded string"]},
        "verification": {"properties": [
            {"name": "rules_reproduce_oracle", "method": "python3 -m repsynth oracles check ayehandsum: every corpus digest "
                                                        "re-encoded from these rules equals the oracle's encoding"},
            {"name": "round_trip", "method": "the oracle's own decode returns the digest (reports/oracles/ayehandsum.json)"}]},
        "generation": {"software": "none: the legacy source stays the implementation (GEN-01)"},
        "evolution": {"changes": [{"version": "0.3.0", "class": "initial", "summary": "Extracted from ayehandsum/ayehandsum"}]},
        "provenance": {"oracle": {"value": src, "evidence": "measured", "source": "reports/readings/ayehandsum.json"},
                       "extraction": "Rules read from ayecode-config and ayecode-encode; alphabets read by sourcing each "
                                     "ayecode-base file; confirmed by re-encoding the oracle's corpus.",
                       "evidence_state": "extracted"},
    }


def check_ayehandsum(spec_path: Path) -> dict:
    import yaml
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    samples, _ = _aye_samples()
    by = {a["alphabet"]: a for a in spec["encoding"]["alphabets"]}
    bad, n = [], 0
    for r in samples:
        a = by.get(r["alphabet"])
        if not a:
            continue
        n += 1
        rules = {"symbols": a["symbols"], "digit_base": a["digit_base"], "terms_per_word": a["terms_per_word"],
                 "codewidth": 7, "words": 8, "index_to_symbol": dict(enumerate(a["symbols_by_index"]))}
        mine = aye_encode(rules, r["sha3_256"])
        if mine != r["encoded"]:
            bad.append(f"{r['alphabet']} {r['input']}: rules give {mine[:40]}..., oracle {r['encoded'][:40]}...")
        if r["decoded_equals_digest"] != "yes":
            bad.append(f"{r['alphabet']} {r['input']}: the oracle's decode does not return the digest")
    return {"mappings_checked": n, "mismatches": bad, "exit_codes": {}}


def _mutate_ayehandsum(spec: dict) -> str:
    a = spec["encoding"]["alphabets"][0]
    a["symbols_by_index"][0], a["symbols_by_index"][1] = a["symbols_by_index"][1], a["symbols_by_index"][0]
    return f"alphabet {a['alphabet']}: symbols of index 0 and 1 swapped"


# --------------------------------------------------------------------------------------------
# P1.8 Hindawi pipeline descriptor: each shaili's composing pipeline as opaque transforms, read
# from Chintamani's own drivers (Hindawi/hindrv) as built by Hindawi 2026.10, each transform named
# with the driver file and line that applies it. Acceptance re-composes the forward pipeline from the
# descriptor and compares it with the driver's own output on Hindawi's samples.
# --------------------------------------------------------------------------------------------

HIN_BUILD = ORACLE_ROOT / "hindawi" / "work" / ".build" / "chintamani"
SHAILIS = ["guru", "shraeni", "yantra", "kritrima", "praatha", "soochee", "wyaaka", "shabda"]


def _awk_system_strings(path: Path) -> list[dict]:
    """The `cc=="<name>"` branches of a hindrv awk driver and the command each passes to system()."""
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for i, l in enumerate(lines):
        m = re.search(r'cc=="([^"]+)"', l)
        if not m:
            continue
        for j in range(i + 1, min(i + 3, len(lines))):
            s = re.search(r"system\((.*)\);\s*$", lines[j])
            if s:
                out.append({"header": m.group(1), "line": j + 1, "awk_expr": s.group(1).strip()})
                break
    return out


def _awk_to_shell(expr: str, cc: str) -> str:
    parts = []
    for m in re.finditer(r'"((?:\\.|[^"\\])*)"|\b(cc)\b', expr):
        if m.group(2):
            parts.append(cc)
        else:
            parts.append(m.group(1).replace('\\"', '"').replace("\\\\", "\\"))
    return "".join(parts)


def _transforms(cmd: str) -> list[str]:
    m = re.search(r"cat tempfil012345\.temphin \| (.*?)\)", cmd)
    return [t.strip() for t in m.group(1).split("|")] if m else []


def _driver_prefix(name: str) -> tuple[str, int]:
    f = HIN_BUILD / "Hindawi" / "hindrv" / name
    for i, l in enumerate(f.read_text(encoding="utf-8").splitlines()):
        if l.startswith("cat $1"):
            return l, i + 1
    raise SystemExit(f"no pipeline line in {f}")


def _transform_source(t: str) -> str:
    exe = t.split()[0]
    for s in SHAILIS:
        if (HIN_BUILD / "Hindawi" / s / f"{exe}.uhin").exists():
            return f"Hindawi/{s}/{exe}.uhin, built by Hindawi/{s}/Makefile (flex)"
    if (HIN_BUILD / "Romenagri" / exe).exists():
        return f"Romenagri/{exe}, built by Romenagri/Makefile"
    return {"sed": "POSIX sed, arguments as written", "tr": "POSIX tr, arguments as written",
            "iconv": "glibc iconv"}.get(exe, "not established: no source found in the build")


def hindawi_descriptor() -> dict:
    hd = HIN_BUILD / "Hindawi" / "hindrv"
    fwd = {x["header"]: x for x in _awk_system_strings(hd / "hin2std.awk")}
    rev = {x["header"]: x for x in _awk_system_strings(hd / "std2hin.awk")}
    cmp_ = {x["header"]: x for x in _awk_system_strings(hd / "hincc.awk")}
    fpre, fl = _driver_prefix("hin2std")
    rpre, rl = _driver_prefix("std2hin")
    shailis = []
    for h in fwd:
        f, r, c = fwd[h], rev.get(h), cmp_.get(h)
        fcmd, rcmd = _awk_to_shell(f["awk_expr"], h), _awk_to_shell(r["awk_expr"], h) if r else ""
        entry = {"header": h.rstrip(">"),
                 "forward": {"driver": "Hindawi/hindrv/hin2std", "common_prefix": {"command": fpre, "line": fl},
                             "dispatch": {"file": "Hindawi/hindrv/hin2std.awk", "line": f["line"], "command": fcmd},
                             "transforms": [{"transform": t, "source": _transform_source(t)} for t in _transforms(fcmd)]},
                 "reverse": ({"driver": "Hindawi/hindrv/std2hin", "common_prefix": {"command": rpre, "line": rl},
                              "dispatch": {"file": "Hindawi/hindrv/std2hin.awk", "line": r["line"], "command": rcmd},
                              "transforms": [{"transform": t, "source": _transform_source(t)} for t in _transforms(rcmd)]}
                             if r else {"not_established": "std2hin.awk has no branch for this header"}),
                 "compile": ({"driver": "Hindawi/hindrv/hincc", "dispatch": {"file": "Hindawi/hindrv/hincc.awk", "line": c["line"],
                                                                            "command": _awk_to_shell(c["awk_expr"], h)}}
                             if c else {"not_established": "hincc.awk has no branch for this header"})}
        shailis.append(entry)
    return {"shailis": shailis,
            "files": {n: sha256_file(hd / n) for n in ("hin2std", "hin2std.awk", "std2hin", "std2hin.awk", "hincc", "hincc.awk")}}


def recompose_forward(desc: dict, sample: Path, work: Path) -> tuple[bytes, str]:
    """Run the descriptor's forward pipeline: the common prefix, the header split, then the dispatched command."""
    env = dict(os.environ)
    env["PATH"] = ":".join([str(HIN_BUILD / "Romenagri"), str(HIN_BUILD / "Hindawi" / "hindrv")] +
                           [str(HIN_BUILD / "Hindawi" / s) for s in SHAILIS] + [env.get("PATH", "")])
    work.mkdir(parents=True, exist_ok=True)
    pre = desc["shailis"][0]["forward"]["common_prefix"]["command"].replace("| hin2std.awk", "").replace("$1", f'"{sample}"')
    p = subprocess.run(["bash", "-c", pre], capture_output=True, env=env, cwd=work, timeout=120)
    lines = p.stdout.split(b"\n")
    cc, body = None, []
    for l in lines[:-1] if lines and lines[-1] == b"" else lines:
        f = l.split()
        if f and f[0] == b"<shailee" and not body:
            cc = f[1].decode("latin-1") if len(f) > 1 else ""
        else:
            body.append(l)
    (work / "tempfil012345.temphin").write_bytes(b"".join(x + b"\n" for x in body))
    entry = next((s for s in desc["shailis"] if cc and s["header"] + ">" == cc), None)
    if entry is None:
        return b"", f"no descriptor entry for header {cc!r}"
    subprocess.run(["bash", "-c", entry["forward"]["dispatch"]["command"]], env=env, cwd=work, timeout=120)
    out = work / "hin.std"
    return (out.read_bytes() if out.exists() else b""), cc


def extract_hindawi() -> dict:
    started = utc_now()
    reg = _load_register()
    main = clone_of(reg, "hindawiai/hindawi2026.10")
    if not (HIN_BUILD / "Hindawi" / "hindrv" / "hin2std.awk").exists():
        raise SystemExit("run `oracles run hindawi` first")
    desc = hindawi_descriptor()
    rep = json.loads((OUT / "hindawi.json").read_text())
    rt = next((s for s in rep["steps"] if s["name"] == "shaili_round_trip"), None)
    rows = []
    if rt:
        for l in (ROOT / rt["stdout_raw"]).read_text(encoding="utf-8").splitlines():
            p = l.split("\t")
            if len(p) == 6 and p[0] != "sample":
                rows.append(dict(zip(["sample", "stage", "exit", "bytes_out", "sha256_out", "note"], p)))
    chint_pin = (ORACLE_ROOT / "hindawi" / "work" / ".build" / "chintamani")
    pin = run_cmd(["git", "-C", str(chint_pin), "rev-parse", "HEAD"], timeout=30)["stdout"].strip()
    reading = {"_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0", "generator": f"repsynth.lanes.oracles {VERSION}",
               "oracle": {"repository": "hindawiai/hindawi2026.10", "commit": main["commit"], "tree": main["tree"],
                          "chintamani_pinned_by_hindawi": pin, "fetched_by": "scripts/fetch.sh", "built_by": "scripts/build.sh"},
               "descriptor": desc, "round_trip_runs": {"record": "reports/oracles/hindawi.json, step shaili_round_trip",
                                                      "exit_code": rt["exit_code"] if rt else None, "rows": rows}}
    READINGS.mkdir(parents=True, exist_ok=True)
    _write_json(READINGS / "hindawi_pipeline.json", reading)
    out = SPEC_DIR / "pipeline" / "hindawi_shaili_pipeline.yaml"
    _write_yaml(out, hindawi_spec(reading))
    return {"reading": {"disagreements": [], "exit_codes": {}, "corpus": []}, "spec_path": out, "started": started}


def hindawi_spec(r: dict) -> dict:
    o = r["oracle"]
    src = f"hindawiai/hindawi2026.10@{o['commit']}"
    ch = f"hindawiai/chintamani@{o['chintamani_pinned_by_hindawi']}"
    return {
        "_notice": NOTICE + " SPDX-License-Identifier: CC0-1.0",
        "identity": {"id": "hindawi_shaili_pipeline", "version": "0.3.0", "family": "symbolic_pipeline",
                     "title": "Hindawi's composing pipeline per shaili, as opaque transforms run by Chintamani's drivers",
                     "equality": "Two pipelines are equal when every stage names the same transform with the same arguments in the same order.",
                     "canonical_form": "Stages in the order the driver applies them."},
        "domain": {"description": "Hindawi programs in UTF-8 whose first line names a shaili (<शैली ...>).", "finite": False},
        "structure": {"stages": ["common prefix of the driver (Unicode to ACII)", "header split (the awk driver)",
                                 "the shaili's transducer and its post-processing (dispatched by header)"],
                      "transducers": "Opaque: each is the shaili's flex program built from its .uhin file; the harness never reads "
                                     "or regenerates them (GOV-03, GOV-17)."},
        "encoding": {"shailis": r["descriptor"]["shailis"]},
        "decoding": {"rule": "The reverse pipeline of each shaili (encoding.shailis[*].reverse), run by std2hin."},
        "semantics": {"statement": "The pipeline composes transforms as the drivers do; their meanings are the transducers' own.",
                      "reference_sources": ["reports/readings/hindawi_pipeline.json", "repsynth/lanes/oracles.py"],
                      "oracle_sources": [f"{ch}:Hindawi/hindrv/hin2std", f"{ch}:Hindawi/hindrv/hin2std.awk",
                                         f"{ch}:Hindawi/hindrv/std2hin", f"{ch}:Hindawi/hindrv/std2hin.awk",
                                         f"{ch}:Hindawi/hindrv/hincc", f"{ch}:Hindawi/hindrv/hincc.awk"],
                      "oracle": f"{src} scripts/build.sh, which builds {ch}"},
        "operations": [],
        "composition": {"rule": "Unix pipes, in driver order; the awk driver writes the body to tempfil012345.temphin and "
                                "runs the dispatched command with system()."},
        "transformations": [{"name": "to_host_language", "to": "host source (C, C++, Java, BASIC, assembly, Python, yacc, lex)",
                             "preserves": "program text as the transducer maps it; the round trip is measured, not assumed"}],
        "constraints": [{"name": "header_first", "statement": "The shaili line must be first (hincc.awk prints an error otherwise)."}],
        "substrate": {"logical": "other", "register_widths": []},
        "interfaces": {"imports": ["romenagri_devanagari"], "exports": ["host-language sources for the host compilers"]},
        "verification": {"properties": [
            {"name": "descriptor_from_drivers", "method": "python3 -m repsynth oracles check hindawi: the descriptor is read "
                                                          "again from the driver files and must equal this file"},
            {"name": "recomposed_forward", "method": "each sample is run through the descriptor's forward stages and must give "
                                                     "the driver's own hin2std output byte for byte"},
            {"name": "round_trips_recorded", "method": "forward and reverse runs on every sample, with exit codes, in reports/oracles/hindawi.json"}]},
        "generation": {"construct_lists": {"not_established": "new mnemonics go to Hindawi as construct lists (ISA-11), not built here"}},
        "evolution": {"changes": [{"version": "0.3.0", "class": "initial", "summary": "Read from Chintamani's drivers as Hindawi 2026.10 builds them"}]},
        "provenance": {"oracle": {"value": f"{src}; {ch}", "evidence": "measured", "source": "reports/readings/hindawi_pipeline.json"},
                       "extraction": "Dispatch branches parsed from the hindrv awk drivers; transforms named with file and line.",
                       "evidence_state": "extracted"},
    }


def check_hindawi(spec_path: Path) -> dict:
    import yaml
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    desc = hindawi_descriptor()
    bad = []
    fresh = json.loads(json.dumps(scrub(desc["shailis"]), ensure_ascii=False))
    if fresh != spec["encoding"]["shailis"]:
        for a, b in zip(fresh, spec["encoding"]["shailis"]):
            if a != b:
                bad.append(f"shaili {a['header']}: the descriptor read from the drivers differs from the specification")
        if len(fresh) != len(spec["encoding"]["shailis"]):
            bad.append("the number of shailis differs")
    n = 0
    sdesc = {"shailis": spec["encoding"]["shailis"]}
    for s in sorted((ORACLE_ROOT / "hindawi" / "scratch" / "shaili").glob("Hindi*")):
        ref = s / "forward.std"
        if not ref.exists() or ref.stat().st_size == 0:
            continue
        n += 1
        got, cc = recompose_forward(sdesc, s / "sample.uhin", CACHE / "tmp" / "recompose" / s.name)
        if got != ref.read_bytes():
            bad.append(f"{s.name}: the descriptor's forward pipeline ({cc}) gives {len(got)} bytes, the driver gave {ref.stat().st_size}")
    rep = json.loads((OUT / "hindawi.json").read_text())
    rt = next((x for x in rep["steps"] if x["name"] == "shaili_round_trip"), None)
    if not rt or rt["exit_code"] != 0:
        bad.append("no recorded forward and reverse run with exit code 0")
    return {"mappings_checked": n, "mismatches": bad, "exit_codes": {"shaili_round_trip": rt["exit_code"] if rt else None}}


def _mutate_hindawi(spec: dict) -> str:
    s = next(x for x in spec["encoding"]["shailis"] if x["header"] == "guru")
    s["forward"]["dispatch"]["command"] = s["forward"]["dispatch"]["command"].replace("h2c", "h2cpp")
    return "guru forward dispatch names h2cpp instead of h2c"


def _mutate_romenagri(spec: dict) -> str:
    row = spec["encoding"]["unicode_to_acii"][0]
    row["acii"] = f"{(int(row['acii'], 16) + 1) & 0xFF:02x}"
    return f"encoding.unicode_to_acii[0].acii changed to {row['acii']}"


EXTRACTIONS = {}  # asset -> (packet, extract, check, spec path, mutate)
EXTRACTIONS["romenagri"] = ("P1.5", extract_romenagri, check_romenagri,
                            SPEC_DIR / "transliteration" / "romenagri_devanagari.yaml", _mutate_romenagri)
EXTRACTIONS["ayehandsum"] = ("P1.7", extract_ayehandsum, check_ayehandsum, SPEC_DIR / "numeric" / "ayehandsum.yaml",
                              _mutate_ayehandsum)
EXTRACTIONS["hindawi"] = ("P1.8", extract_hindawi, check_hindawi, SPEC_DIR / "pipeline" / "hindawi_shaili_pipeline.yaml",
                           _mutate_hindawi)
EXTRACTIONS["apcisr"] = ("P1.6", extract_apcisr, check_apcisr, SPEC_DIR / "script" / "apcisr_devanagari.yaml", _mutate_apcisr)


def cmd_extract(asset: str) -> int:
    packet, ex, _, path, _ = EXTRACTIONS[asset]
    started = utc_now()
    res = ex()
    rd = res["reading"]
    rec = record(packet, f"extract_{asset}", f"python3 -m repsynth oracles extract {asset}", 0, started_utc=started,
                 outputs=[res["spec_path"], READINGS / f"{asset}.json"],
                 results={"disagreements": len(rd.get("disagreements", [])), "exit_codes": rd.get("exit_codes"),
                          "corpus": [{k: v for k, v in c.items() if k != "first_differences"} for c in rd.get("corpus", [])]},
                 state="wired_unproven", notes="Extraction only; acceptance is `oracles check`.")
    print(json.dumps({"record": str(rec), "spec": str(res["spec_path"]),
                      "disagreements": len(rd.get("disagreements", []))}, indent=2))
    return 0


def cmd_check(asset: str) -> int:
    """Acceptance: the oracle reproduces every mapping of the specification; a planted wrong mapping
    is refused; the specification passes the meta-model validator."""
    import yaml
    packet, _, check, path, mutate = EXTRACTIONS[asset]
    started = utc_now()
    real = check(path)
    tmp = CACHE / "tmp" / f"planted_{path.name}"
    spec = yaml.safe_load(path.read_text(encoding="utf-8"))
    what = mutate(spec)
    tmp.write_text(yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8")
    planted = check(tmp)
    val = run_cmd([sys.executable, "-m", "repsynth", "spec", "check", str(path)], cwd=ROOT, timeout=300)
    ok = (not real["mismatches"]) and bool(planted["mismatches"]) and val["exit_code"] == 0
    rec = record(packet, f"check_{asset}", f"python3 -m repsynth oracles check {asset}", 0 if ok else 1,
                 started_utc=started, inputs=[path],
                 results={"mappings_checked": real["mappings_checked"], "mismatches": real["mismatches"][:50],
                          "oracle_exit_codes": real["exit_codes"],
                          "planted_defect": what, "planted_refused": bool(planted["mismatches"]),
                          "planted_mismatches": planted["mismatches"][:5],
                          "spec_check": {"command": val["command"], "exit_code": val["exit_code"],
                                         "output": tail(val["stdout"] + val["stderr"], 15)}},
                 state="done" if ok else "failed",
                 notes="Acceptance run: oracle executed on every extracted mapping.")
    print(json.dumps({"record": str(rec), "ok": ok, "checked": real["mappings_checked"],
                      "mismatches": len(real["mismatches"]), "planted_refused": bool(planted["mismatches"]),
                      "spec_check_exit": val["exit_code"], "spec_check": tail(val["stdout"] + val["stderr"], 8)}, indent=2))
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="repsynth oracles", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="sub", required=True)
    r = sub.add_parser("run", help="build and run an oracle through its own drivers")
    r.add_argument("asset", choices=sorted(ORACLES) + ["all"])
    r.add_argument("--only", nargs="*", help="run only these steps")
    sub.add_parser("list", help="list the oracles and their steps")
    e = sub.add_parser("extract", help="extract a specification from an oracle (P1.5 to P1.8)")
    e.add_argument("asset")
    c = sub.add_parser("check", help="acceptance: execute the oracle on every extracted mapping")
    c.add_argument("asset")
    return ap


def _argv(ctx) -> list[str]:
    from repsynth.lanes.intake import _argv as a
    return a(ctx)


def run(ctx) -> int:
    args = build_parser().parse_args(_argv(ctx))
    if args.sub == "list":
        for k, v in ORACLES.items():
            print(k, v["slug"], [s["name"] for s in v["steps"]])
        return 0
    if args.sub == "extract":
        return cmd_extract(args.asset)
    if args.sub == "check":
        return cmd_check(args.asset)
    names = sorted(ORACLES) if args.asset == "all" else [args.asset]
    return max(run_oracle(n, args.only) for n in names)


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
