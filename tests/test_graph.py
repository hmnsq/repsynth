# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""P3.1: a generator reading an undeclared path fails its own test, naming the path.
P3.2: touching one slice rebuilds only its dependants, judged by output hashes.
P3.3: every artefact has an implements or validates edge; the rendering regenerates from the list.
Runs against a clone of the repository so the working tree is never disturbed."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent
WORK = SRC / ".cache" / "tmp" / "graphtest"


@pytest.fixture(scope="module")
def clone():
    if WORK.exists():
        shutil.rmtree(WORK)
    WORK.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "clone", "-q", str(SRC), str(WORK)], check=True)
    # carry uncommitted spine files so the test sees the working state
    subprocess.run([sys.executable, "-m", "repsynth", "gen"], cwd=WORK, check=True, capture_output=True)
    return WORK


def _py(clone, code):
    return subprocess.run([sys.executable, "-c", code], cwd=clone, capture_output=True, text=True)


def test_undeclared_read_fails_naming_path(clone):
    r = _py(clone, (
        "from repsynth.accessor import Accessor, UndeclaredRead\n"
        "from repsynth.numeric import spec_of\n"
        "a = Accessor(spec_of('balanced_ternary'), ['/encoding/active'], 'codec-under-test')\n"
        "a('/encoding/active')\n"
        "try:\n    a('/operations/0')\nexcept UndeclaredRead as e:\n    print('REFUSED', e)\n    raise SystemExit(0)\n"
        "raise SystemExit(1)\n"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert "balanced_ternary#/operations/0" in r.stdout


def test_not_established_is_refused_by_generators(clone):
    r = _py(clone, (
        "from repsynth.spec import consume, SpecError\n"
        "from repsynth.numeric import spec_of\n"
        "try:\n    consume(spec_of('balanced_ternary'), '/substrate/limits')\n"
        "except SpecError as e:\n    print('REFUSED', e.path)\n    raise SystemExit(0)\nraise SystemExit(1)\n"))
    assert r.returncode == 0 and "/substrate/limits/hardware_area" in r.stdout, r.stdout + r.stderr


def _hashes(clone):
    r = _py(clone, "import json; from repsynth.graph import all_nodes, artefact_hashes; print(json.dumps(artefact_hashes(all_nodes())))")
    import json
    return json.loads(r.stdout)


def test_touching_one_slice_rebuilds_only_dependants(clone):
    before = _hashes(clone)
    # change one operation's meaning text: only that operation's vectors read /operations/<i>
    spec = clone / "spec/reps/numeric/balanced_ternary.yaml"
    text = spec.read_text()
    spec.write_text(text.replace('meaning: "a * b, low n trits (wrapping modulo 3^n)"', 'meaning: "a times b, low n trits (wrapping modulo 3^n)"'))
    try:
        r = subprocess.run([sys.executable, "-m", "repsynth", "gen"], cwd=clone, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
        after = _hashes(clone)
    finally:
        spec.write_text(text)
        subprocess.run([sys.executable, "-m", "repsynth", "gen"], cwd=clone, capture_output=True)
    changed = {k for k in before if before[k] != after.get(k)}
    # the dependants of the touched slice, read from the graph itself (any lane's nodes included)
    r = _py(clone, "import json; from repsynth.graph import all_nodes; "
                   "print(json.dumps(sorted(o for n in all_nodes() if n.spec == 'balanced_ternary' and "
                   "any(p in ('/operations', '/operations/3') or p.startswith('/operations/3/') for p in n.reads) for o in n.outputs)))")
    import json
    dependants = set(json.loads(r.stdout))
    assert {"conformance/vectors/balanced_ternary/mul.32.vec", "conformance/vectors/balanced_ternary/mul.16.vec"} <= changed, changed
    assert changed <= dependants, sorted(changed - dependants)


def test_edges_cover_every_artefact_and_render_regenerates(clone):
    r = _py(clone, "from repsynth.graph import all_nodes, check_edges, write_edges; n=all_nodes(); write_edges(n); print(check_edges(n))")
    assert r.stdout.strip() == "[]", r.stdout + r.stderr
    dot = (clone / "graph/edges.dot").read_text()
    (clone / "graph/edges.dot").unlink()
    _py(clone, "from repsynth.graph import all_nodes, write_edges; write_edges(all_nodes())")
    assert (clone / "graph/edges.dot").read_text() == dot
