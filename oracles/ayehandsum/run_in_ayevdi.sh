#!/usr/bin/env bash
# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
# Runs AyeHandSum through its own drivers inside AyeVDI's sourcefrom environment, activated with the command the
# statutory header of every AyeHandSum script prints:
#   ayesh=$(tempfile) && wget https://bit.ly/ayevdi-sfrom-init -O${ayesh} -q && . ${ayesh}
# HOME is a scratch folder (AyeVDI writes ~/.ayevdi); wget is the stand-in beside this file, which serves the
# pinned trees. Modes:
#   test       echo ayeai | sourcefrom .../ayehandsum-test
#   samples    ayesha encode and decode for every alphabet (ayecode-base-*) on the inputs ayeai, ayelearn, ayevdi;
#              TSV: alphabet input encoded decoded sha3-256 decoded_equals_digest
#   test-all   sourcefrom .../ayehandsum-test-all
# No `set -u`: AyeVDI's scripts are not written for nounset.
mode="${1:?mode}"
HERE=$(cd "$(dirname "$0")" && pwd)
export HOME="${ORACLE_SCRATCH:?}/home"; mkdir -p "$HOME"
export PATH="$HERE:$PATH"
shopt -s expand_aliases
R=https://raw.githubusercontent.com/ayehandsum/ayehandsum/master
ayesh=$(tempfile) && wget https://bit.ly/ayevdi-sfrom-init -O${ayesh} -q && . ${ayesh}
echo "== activation: ayevdi_sourcefrom=${ayevdi_sourcefrom:-unset}"
case "$mode" in
  test)
    echo ayeai | sourcefrom $R/ayehandsum-test ;;
  samples)
    printf 'alphabet\tinput\tencoded\tdecoded\tsha3_256\tdecoded_equals_digest\n'
    for b in "${ORACLE_WORK:?}"/ayecode-base-*; do
      a=${b##*/ayecode-base-}
      for i in ayeai ayelearn ayevdi; do
        enc=$(echo "$i" | sourcefrom $R/ayesha encode "$a")
        dec=$(echo "$enc" | sourcefrom $R/ayesha decode "$a")
        ref=$(echo "$i" | sha3sum -a 256 | cut -d' ' -f1)
        [ "$dec" = "$ref" ] && eq=yes || eq=no
        printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$a" "$i" "$enc" "$dec" "$ref" "$eq"
      done
    done ;;
  test-all)
    sourcefrom $R/ayehandsum-test-all ;;
  *) echo "unknown mode $mode"; exit 2 ;;
esac
