#!/usr/bin/env bash
# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
# lab/run.sh <exercise>: change-encoding | add-operation | add-instruction
set -euo pipefail
cd "$(dirname "$0")/.."
ex="${1:-}"
work=".cache/lab/$ex"
rm -rf "$work"; mkdir -p .cache/lab
git clone -q . "$work"
cd "$work"
python3 -m repsynth gen >/dev/null 2>&1 || true
case "$ex" in
  change-encoding) python3 -m repsynth impact d --confirm ;;
  add-operation)   python3 -m repsynth impact c --confirm ;;
  add-instruction)
    if python3 -c "import repsynth.lanes.tiera" 2>/dev/null; then
      python3 -m repsynth impact c --confirm && python3 -m repsynth tiera lab-add-instruction abs
    else
      echo "The Tier A lane is not present in this tree; exercise 3 needs it (P4.3)."; exit 2
    fi ;;
  *) echo "usage: lab/run.sh change-encoding|add-operation|add-instruction" >&2; exit 2 ;;
esac
