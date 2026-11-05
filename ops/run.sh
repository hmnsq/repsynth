#!/usr/bin/env bash
# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
# One command: ops/run.sh --iteration <N> [--native] [--fresh]
#   default  builds the kept containers once (repsynth doctor --build) and runs every step inside them;
#   --native runs on the current machine (used on build machines that already carry the tools).
# Everything stays inside this folder (GOV-02).
set -euo pipefail
cd "$(dirname "$0")/.."
ITERATION="" NATIVE="" FRESH=""
while [ $# -gt 0 ]; do
  case "$1" in
    --iteration) ITERATION="$2"; shift 2 ;;
    --iteration=*) ITERATION="${1#*=}"; shift ;;
    --milestone) ITERATION="$2"; shift 2 ;;
    --native) NATIVE="--native"; shift ;;
    --fresh) FRESH="--fresh"; shift ;;
    -h|--help) sed -n '2,8p' "$0"; exit 0 ;;
    *) echo "unknown argument: $1 (see --help)" >&2; exit 2 ;;
  esac
done
[ -n "$ITERATION" ] || { echo "give --iteration <N>, for example --iteration I1" >&2; exit 2; }
echo "© 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI. repsynth, iteration $ITERATION"
if [ -n "$NATIVE" ]; then
  exec python3 -m repsynth run --iteration "$ITERATION" --native $FRESH
fi
command -v docker >/dev/null || { echo "Docker is required (nothing is installed on this machine by this script)." >&2; exit 2; }
if ! docker image inspect repsynth-base >/dev/null 2>&1; then
  echo "Building the containers once (they are kept)..."
  docker build -t repsynth-base -f containers/Dockerfile.repsynth-base containers
  docker run --rm -v "$PWD":/work -w /work -v /var/run/docker.sock:/var/run/docker.sock repsynth-base python3 -m repsynth doctor --build || true
fi
exec docker run --rm -v "$PWD":/work -w /work -v /var/run/docker.sock:/var/run/docker.sock \
  -e REPSYNTH_HOST_ROOT="$PWD" repsynth-base python3 -m repsynth run --iteration "$ITERATION" $FRESH
