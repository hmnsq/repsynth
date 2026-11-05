# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Construct list of new mnemonics for Hindawi (ISA-11, GOV-17, P4.9).

The form is the one Hindawi's construct tables take (hindawiai/hindawi2026.10,
docs/hindawi/data/standards.json, read at commit b53530f6): {"constructs": {<shaili>: [token, ...]},
"languages": {<language>: {"words": {token: word}, "provenance": {token: source}}}}. The new
mnemonics go under the assembly shaili "yantra"; "languages" is left empty, because localising the
words is Hindawi's own process. Keys starting with "_" are this harness's metadata.

Called through repsynth.lanes.graph_tiera (node hindawi:<sid>)."""
from __future__ import annotations

import json

GENERATOR = "repsynth.gen.hindawi 0.3.0"


def render_spec(ctx: dict, root=None) -> dict:
    sid, ext = ctx["sid"], ctx["ext"]["extension"]
    meaning = {o["name"]: o["meaning"] for _, o in ctx["ops"]}
    tokens = [e["mnemonic"] for e in ctx["entries"]]
    doc = {
        "_notice": "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. SPDX-License-Identifier: CC0-1.0",
        "_generator": GENERATOR,
        "_source": {"spec": sid, "version": ctx["version"], "slice_sha256": ctx["slice_sha256"],
                    "active_encoding": ctx["encoding"], "extension": ext},
        "_meanings": {e["mnemonic"]: meaning[e["op"]] for e in ctx["entries"]},
        "_form": "hindawi2026.10 docs/hindawi/data/standards.json: constructs per shaili, languages with words "
                 "and provenance",
        "constructs": {"yantra": tokens},
        "languages": {},
    }
    return {f"gen/hindawi/out/{sid}/{ext}.constructs.json": json.dumps(doc, indent=2, ensure_ascii=False) + "\n"}
