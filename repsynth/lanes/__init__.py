# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""Lane registry. Each lane appends one line: LANES["<subcommand>"] = "repsynth.lanes.<module>"."""
LANES: dict[str, str] = {}
LANE_ERRORS: dict[str, str] = {}


def load_lane(name: str):
    """Import a registered lane. A lane that fails to import stops itself and is reported; every other
    lane carries on (MRD 9.1). Returns the module or None."""
    import importlib
    import sys
    try:
        return importlib.import_module(LANES[name])
    except Exception as e:  # reported, never hidden
        msg = f"{type(e).__name__}: {e}"
        if LANE_ERRORS.get(name) != msg:
            print(f"LANE ERROR {name} ({LANES[name]}): {msg}", file=sys.stderr)
        LANE_ERRORS[name] = msg
        return None
LANES["intake"] = "repsynth.lanes.intake"
LANES["oracles"] = "repsynth.lanes.oracles"
LANES["hdl"] = "repsynth.lanes.hdl"
LANES["graph-hdl"] = "repsynth.lanes.graph_hdl"
LANES["selftest-hdl"] = "repsynth.lanes.selftest_hdl"
LANES["graph-tiera"] = "repsynth.lanes.graph_tiera"
LANES["tiera"] = "repsynth.lanes.tiera"
LANES["baseline"] = "repsynth.lanes.baseline"
LANES["paras-rt"] = "repsynth.lanes.paras_rt"
