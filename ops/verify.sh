#!/usr/bin/env bash
# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
# Release gate, essentials only (GOV-07): the built payload, the repository's own tests, contract
# checks, secrets, oversized files and version agreement refuse; everything else reports.
set -uo pipefail
cd "$(dirname "$0")/.."
fail=0
gate() { if "$@"; then echo "PASS  $GATE"; else echo "FAIL  $GATE"; fail=1; fi; }
report() { if "$@"; then echo "ok    $GATE"; else echo "note  $GATE (reported, not a gate)"; fi; }

GATE="version agreement (VERSION, package, CITATION.cff)"
gate bash -c 'v=$(cat VERSION); python3 -c "import repsynth,sys; sys.exit(repsynth.__version__!=\"$v\")" && grep -q "^version: \"\?$v\"\?" CITATION.cff'
GATE="specifications validate"
gate bash -c 'python3 -m repsynth spec check $(find spec/reps -name "*.yaml" -not -path "*/candidates/*") >/dev/null'
GATE="built payload: the dependency graph has no work left"
gate bash -c 'python3 -m repsynth gen >/dev/null && ninja -f graph/build.ninja -n | grep -q "no work to do"'
GATE="own tests (pytest tests/)"
gate bash -c 'python3 -m pytest -q tests/ >/dev/null 2>&1'
GATE="software conformance"
gate bash -c 'python3 -m repsynth conform --lane software >/dev/null 2>&1'
GATE="mutation self-tests catch every planted defect"
gate bash -c 'python3 -m repsynth selftest >/dev/null 2>&1'
GATE="copyright line on every tracked source file"
gate bash -c 'missing=$(git ls-files "*.py" "*.c" "*.h" "*.mjs" "*.js" "*.sh" "*.yaml" "*.sv" "*.vhd" | while read f; do head -c 600 "$f" | grep -q "© 1993–2026 Abhishek Choudhary" || echo "$f"; done); [ -z "$missing" ] || { echo "$missing" | head -20; false; }'
GATE="no AI named in tracked files"
gate bash -c '! git ls-files -z | xargs -0 grep -IlE "\b(Claude|Anthropic|ChatGPT|OpenAI|Grok|Gemini|Copilot)\b" -- 2>/dev/null | grep -v "^ops/verify.sh$" | grep -q .'
GATE="no secrets"
gate bash -c '! git ls-files -z | xargs -0 grep -IlE "(gh[pousr]_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN (RSA|OPENSSH|EC) PRIVATE KEY-----)" -- 2>/dev/null | grep -q .'
GATE="no tracked file over 20 MB"
gate bash -c '! git ls-files -z | xargs -0 du -k 2>/dev/null | awk "\$1>20480" | grep -q .'
GATE="RESUME.md regenerates from records"
report bash -c 'python3 -m repsynth report >/dev/null'
GATE="status page present"
report test -f docs/index.html
exit $fail
