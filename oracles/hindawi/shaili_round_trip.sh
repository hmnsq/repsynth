#!/usr/bin/env bash
# © 1993–2026 Abhishek Choudhary. All rights reserved. AyeAI.
# SPDX-License-Identifier: GPL-3.0-or-later
# Runs Chintamani's own Hindawi drivers (Hindawi/hindrv: hincc, hin2std, std2hin), as built by Hindawi 2026.10's
# scripts/build.sh in .build/chintamani of the exported work tree, on the shailis' own Hindi samples
# (Hindawi/samples/*.uhin). Each sample runs in its own scratch folder because the drivers write fixed temporary
# names in the current folder. Nothing in the work tree's sources is changed.
#   forward:  hin2std <sample>    -> hin.std   (the shaili's h2X transducer, then acii2hin)
#   reverse:  std2hin <hin.std>   -> hin.uhin  (the shaili's X2h transducer, then rmn2acii and acii2uni)
#   compile:  hincc <sample>      (dispatches on the <shailee ...> line to the shaili's own XXXcc driver)
# Output: one TSV row per sample and stage, then the files themselves under $ORACLE_SCRATCH/shaili/.
set -u
W="${ORACLE_WORK:?}"; B="$W/.build/chintamani"; OUTD="${ORACLE_SCRATCH:?}/shaili"
[ -d "$B/Hindawi/hindrv" ] || { echo "no built Chintamani at $B: run the install step first"; exit 2; }
P="$B/Romenagri:$B/Hindawi/hindrv"
for s in guru shraeni yantra kritrima praatha soochee wyaaka shabda; do P="$P:$B/Hindawi/$s"; done
# fasm and qb2c, where the chintamani_others step built them (Chintamani's install puts them on PATH).
for o in fasm qb2c; do [ -d "$B/Hindawi/others/$o" ] && P="$P:$B/Hindawi/others/$o"; done
export PATH="$P:$PATH"
# Chintamani's install puts libqbX11.a in /usr/lib; here the built folder is given to the linker instead.
[ -f "$B/Hindawi/others/qb2c/libqbX11.a" ] && export LIBRARY_PATH="$B/Hindawi/others/qb2c${LIBRARY_PATH:+:$LIBRARY_PATH}"
unset JAVA_TOOL_OPTIONS
mkdir -p "$OUTD"
printf 'sample\tstage\texit\tbytes_out\tsha256_out\tequal_to_sample_without_cr\n'
fail=0
for f in "$B"/Hindawi/samples/Hindi*.uhin; do
  n=$(basename "$f" .uhin); d="$OUTD/$n"; rm -rf "$d"; mkdir -p "$d"; cp "$f" "$d/sample.uhin"
  ( cd "$d" && timeout 120 bash "$B/Hindawi/hindrv/hin2std" sample.uhin > forward.out 2> forward.err ); e1=$?
  [ -f "$d/hin.std" ] && cp "$d/hin.std" "$d/forward.std" || : > "$d/forward.std"
  printf '%s\tforward_hin2std\t%s\t%s\t%s\t-\n' "$n" "$e1" "$(wc -c < "$d/forward.std")" "$(sha256sum < "$d/forward.std" | cut -c1-64)"
  mkdir -p "$d/rev"; cp "$d/forward.std" "$d/rev/std.in"
  ( cd "$d/rev" && timeout 120 bash "$B/Hindawi/hindrv/std2hin" std.in > reverse.out 2> reverse.err ); e2=$?
  [ -f "$d/rev/hin.uhin" ] && cp "$d/rev/hin.uhin" "$d/reverse.uhin" || : > "$d/reverse.uhin"
  if cmp -s <(tr -d '\r' < "$d/sample.uhin") "$d/reverse.uhin"; then eq=yes; else eq=no; fi
  printf '%s\treverse_std2hin\t%s\t%s\t%s\t%s\n' "$n" "$e2" "$(wc -c < "$d/reverse.uhin")" "$(sha256sum < "$d/reverse.uhin" | cut -c1-64)" "$eq"
  mkdir -p "$d/cc"; cp "$f" "$d/cc/sample.uhin"
  ( cd "$d/cc" && timeout 300 bash "$B/Hindawi/hindrv/hincc" sample.uhin > compile.out 2> compile.err ); e3=$?
  produced=$(cd "$d/cc" && ls | grep -v -E '^(sample.uhin|compile.out|compile.err)$' | tr '\n' ',')
  printf '%s\tcompile_hincc\t%s\t%s\t%s\tproduced=%s\n' "$n" "$e3" "$(wc -c < "$d/cc/compile.out")" "$(sha256sum < "$d/cc/compile.out" | cut -c1-64)" "$produced"
  for x in "$e1" "$e2" "$e3"; do [ "$x" = 0 ] || fail=1; done
  diff <(tr -d '\r' < "$d/sample.uhin") "$d/reverse.uhin" > "$d/reverse.diff"
done
echo "--- differences between each sample and its reverse (first lines; full diffs in $OUTD/<sample>/reverse.diff)"
for f in "$OUTD"/*/reverse.diff; do echo "## $(basename "$(dirname "$f")"): $(grep -c '^<' "$f") lines differ"; head -6 "$f"; done
echo "--- compile output (hincc)"
for f in "$OUTD"/*/cc/compile.out; do echo "## $(basename "$(dirname "$(dirname "$f")")")"; head -8 "$f"; done
exit $fail
