#!/usr/bin/env bash
# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
# Mutation self-tests of every registered lane (CNF-04).
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -m repsynth selftest --lane "${1:-all}"
