# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
"""P1.2: a slice hash is unchanged by key order and whitespace and changed by any change of value."""
import random
import sys
from pathlib import Path

import yaml
from hypothesis import given, settings, strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from repsynth.spec import load_spec, slice_hash, walk, canonical  # noqa: E402

SPEC = Path(__file__).resolve().parent.parent / "spec/reps/numeric/balanced_ternary.yaml"
BASE = load_spec(SPEC)
POINTERS = [p for p, _ in walk(BASE) if p]

json_scalars = st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=8))
json_values = st.recursive(json_scalars, lambda c: st.one_of(st.lists(c, max_size=4), st.dictionaries(st.text(max_size=5), c, max_size=4)), max_leaves=12)


def _shuffle(v, rng):
    if isinstance(v, dict):
        items = list(v.items())
        rng.shuffle(items)
        return {k: _shuffle(x, rng) for k, x in items}
    if isinstance(v, list):
        return [_shuffle(x, rng) for x in v]
    return v


@settings(max_examples=200, deadline=None)
@given(st.integers(min_value=0, max_value=2**32), st.sampled_from(POINTERS))
def test_key_order_and_whitespace_do_not_change_slice_hash(seed, ptr):
    rng = random.Random(seed)
    shuffled = _shuffle(BASE, rng)
    text = yaml.safe_dump(shuffled, sort_keys=False, allow_unicode=True, indent=rng.choice([2, 4, 6]),
                          default_flow_style=rng.choice([False, None]), width=rng.choice([40, 80, 200]))
    again = yaml.safe_load(text)
    assert slice_hash(again, ptr) == slice_hash(BASE, ptr)


@settings(max_examples=300, deadline=None)
@given(st.sampled_from(POINTERS), json_values)
def test_any_value_change_changes_slice_hash(ptr, new):
    import copy
    from repsynth.spec import resolve
    old = resolve(BASE, ptr)
    if canonical(new) == canonical(old):
        return
    mutated = copy.deepcopy(BASE)
    parts = ptr.split("/")[1:]
    node = mutated
    for t in parts[:-1]:
        node = node[int(t)] if isinstance(node, list) else node[t.replace("~1", "/").replace("~0", "~")]
    last = parts[-1].replace("~1", "/").replace("~0", "~")
    if isinstance(node, list):
        node[int(last)] = new
    else:
        node[last] = new
    assert slice_hash(mutated, ptr) != slice_hash(BASE, ptr)
    assert slice_hash(mutated, "") != slice_hash(BASE, "")
