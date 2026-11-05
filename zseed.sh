#!/usr/bin/env bash
###############################################################################
#  zseed — the generalized Zistgah seed engine.
#
#  ONE script for every project. Each project carries a small seed.json
#  manifest; zseed does the rest. Extracted from the vgc-health / aab / fiza /
#  zistgah-home builds, which each hand-rolled ~80% identical scripts (and fiza
#  shipped with none — the exact failure a shared engine eliminates).
#
#  seed.json (per project, beside this script or via -m):
#    {
#      "name": "fiza",
#      "repo": "zistgah/fiza",                     // canonical home (fixed)
#      "site": "https://zistgah.org/fiza/",
#      "artifact": "index.html",                   // the DOI-carrying artifact
#      "doi_placeholder": "__FIZA_DOI__",
#      "inject_into": ["index.html","CONTRACT.md","CITATION.cff"],
#      "push_files": ["index.html","CONTRACT.md","CONTEXT.md","README.md",
#                     "BACKLOG.md","LICENSES.md","misty.json","CITATION.cff"],
#      "provenance_dir": "provenance",
#      "backlog": "BACKLOG.md",                    // for --issues
#      "pages": true                               // enable GitHub Pages
#    }
#
#  Commands (safe by default — no flags = validate + offline DOI dry-run):
#    zseed.sh [-m seed.json]                # validate everything, touch nothing
#    zseed.sh --push                        # create/push repo (+Pages)  [typed PUSH]
#    zseed.sh --publish                     # mint DOI, inject, OTS      [typed MINT]
#    zseed.sh --issues                      # open backlog sprint issues [typed YES]
#    zseed.sh --all                         # push + publish (each still gated)
#
#  RULES: in-folder scratch ./.seedwork only — NEVER /tmp, never navigate
#  outside the run folder; tokens/ORCID from env only; logs to ~/work/logs/;
#  every irreversible step behind a typed confirmation.
#
#  © 1993-2026 Abhishek Choudhary. All rights reserved. GPL-3.0-or-later.
###############################################################################
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$SCRIPT_DIR"

MANIFEST="seed.json"
DO_PUSH=0; DO_PUBLISH=0; DO_ISSUES=0
while [ $# -gt 0 ]; do case "$1" in
  -m) MANIFEST="$2"; shift;;
  --push) DO_PUSH=1;; --publish) DO_PUBLISH=1;; --issues) DO_ISSUES=1;;
  --all) DO_PUSH=1; DO_PUBLISH=1;;
  -h|--help) sed -n '2,40p' "$0"; exit 0;;
  *) echo "unknown flag: $1"; exit 2;; esac; shift; done

[ -f "$MANIFEST" ] || { echo "FATAL: manifest $MANIFEST not found"; exit 1; }

# ---- read manifest (single python read, exported as shell vars) ----
eval "$(python3 - "$MANIFEST" <<'PY'
import json,sys,shlex
d=json.load(open(sys.argv[1]))
def q(x): return shlex.quote(str(x))
print("P_NAME="+q(d["name"]))
print("P_REPO="+q(d["repo"]))
print("P_SITE="+q(d.get("site","")))
print("P_ART="+q(d["artifact"]))
print("P_PH="+q(d.get("doi_placeholder","")))
print("P_PROV="+q(d.get("provenance_dir","provenance")))
print("P_BACKLOG="+q(d.get("backlog","BACKLOG.md")))
print("P_PAGES="+q(1 if d.get("pages",True) else 0))
print("P_INJECT=("+" ".join(q(x) for x in d.get("inject_into",[]))+")")
print("P_PUSH=("+" ".join(q(x) for x in d.get("push_files",[]))+")")
PY
)"

WORK="$SCRIPT_DIR/.seedwork"
LOGDIR="${HOME}/work/logs"; mkdir -p "$LOGDIR"
STAMP="$(date +%Y%m%d-%H%M%S)"; LOG="$LOGDIR/zseed-$P_NAME-$STAMP.log"
st(){ echo "  $*" | tee -a "$LOG"; }
hd(){ echo "" | tee -a "$LOG"; echo "=== $* ===" | tee -a "$LOG"; }
die(){ echo "FATAL: $*" | tee -a "$LOG" >&2; exit 1; }
cleanup(){ rm -rf "$WORK" .doi-dryrun 2>/dev/null || true; }
trap cleanup EXIT

hd "zseed · $P_NAME — $STAMP (push=$DO_PUSH publish=$DO_PUBLISH issues=$DO_ISSUES)"
st "dir: $SCRIPT_DIR"; st "repo: $P_REPO"; st "log: $LOG"

# ---- 1. validate ----
hd "1. VALIDATE"
[ -f "$P_ART" ] || die "artifact missing: $P_ART"
mkdir -p "$P_PROV"
case "$P_ART" in
  *.html) python3 - "$P_ART" <<'PY' 2>>"$LOG" || die "artifact HTML parse failed"
import sys,html.parser
class V(html.parser.HTMLParser):
    def error(self,m): raise ValueError(m)
V().feed(open(sys.argv[1],encoding='utf-8').read()); print("   artifact HTML parses OK")
PY
  ;;
  *) st "artifact: $P_ART (no HTML check)";;
esac
[ -f misty.json ] && { python3 -c "import json;json.load(open('misty.json'))" 2>>"$LOG" && st "misty.json OK" || die "misty.json invalid"; } || st "note: no misty.json (publish unavailable)"
[ -f CITATION.cff ] && { python3 -c "import yaml;yaml.safe_load(open('CITATION.cff'))" 2>/dev/null && st "CITATION.cff OK" || st "CITATION.cff: yaml module missing or invalid — review"; }
for f in "${P_PUSH[@]}"; do [ -f "$f" ] || st "warn: push file missing: $f"; done
SHA="$(sha256sum "$P_ART" | cut -d' ' -f1)"; st "artifact sha256: $SHA"
if [ -n "$P_PH" ]; then grep -q "$P_PH" "$P_ART" && st "DOI placeholder present ($P_PH)" || st "note: no placeholder in artifact (minted?)"; fi

# ---- 2. tooling + offline dry-run ----
hd "2. TOOLING + DOI DRY-RUN (offline)"
MISTY=""; command -v misty >/dev/null 2>&1 && MISTY="misty"
st "misty : ${MISTY:-NOT FOUND (pipx install misty-doi)}"
command -v gh >/dev/null 2>&1 && st "gh    : $(command -v gh)" || st "gh    : NOT FOUND (needed for --push/--issues)"
if [ -n "$MISTY" ] && [ -f misty.json ]; then
  "$MISTY" validate -m misty.json 2>&1 | tee -a "$LOG" || st "   (validate flagged — review)"
  "$MISTY" publish -m misty.json -f "$P_ART" --dry-run --package-dir ".doi-dryrun" 2>&1 | tee -a "$LOG" || st "   (dry-run flagged — review)"
  st "dry-run complete — nothing published"
fi

# ---- 3. push ----
if [ "$DO_PUSH" = "1" ]; then
  hd "3. PUSH -> $P_REPO"
  command -v gh >/dev/null 2>&1 || die "gh not found"
  gh auth status >/dev/null 2>&1 || die "gh not authenticated"
  echo "  Will publish to $P_REPO: ${P_PUSH[*]} + $P_PROV/*.ots + this script + $MANIFEST"
  read -r -p "  Type PUSH to proceed: " C
  if [ "$C" = "PUSH" ]; then
    rm -rf "$WORK"; mkdir -p "$WORK/repo/$P_PROV"
    for f in "${P_PUSH[@]}"; do [ -f "$f" ] && { mkdir -p "$WORK/repo/$(dirname "$f")"; cp -f "$f" "$WORK/repo/$f"; }; done
    cp -f "$P_PROV"/*.ots "$WORK/repo/$P_PROV/" 2>/dev/null || true
    touch "$WORK/repo/$P_PROV/.gitkeep"
    cp -f "$(basename "$0")" "$MANIFEST" "$WORK/repo/" 2>/dev/null || true
    ( cd "$WORK/repo"
      git init -q; git add -A; git commit -q -m "$P_NAME: seed via zseed"
      git branch -M main
      if gh repo view "$P_REPO" >/dev/null 2>&1; then
        git remote add origin "https://github.com/$P_REPO.git"
        git push -u origin main --force 2>>"$LOG" && echo "  pushed (existing repo)"
      else
        gh repo create "$P_REPO" --public --source=. --push 2>>"$LOG" && echo "  repo created + pushed"
      fi
      [ "$P_PAGES" = "1" ] && { gh api -X POST "repos/$P_REPO/pages" -f "source[branch]=main" -f "source[path]=/docs" >/dev/null 2>&1 && echo "  Pages enabled" || echo "  (Pages may already be enabled)"; }
    )
    [ -n "$P_SITE" ] && st "live at: $P_SITE"
  else st "push skipped"; fi
fi

# ---- 4. publish DOI + inject + OTS ----
if [ "$DO_PUBLISH" = "1" ]; then
  hd "4. MINT DOI (irreversible)"
  [ -n "$MISTY" ] || die "misty not installed"
  [ -f misty.json ] || die "misty.json missing"
  [ -n "${ZENODO_TOKEN:-}" ] || die "ZENODO_TOKEN not set in env"
  OTS="$(command -v ots || true)"
  [ -n "$OTS" ] || { [ -x "$HOME/.local/bin/ots" ] && OTS="$HOME/.local/bin/ots"; }
  [ -n "$OTS" ] || die "OpenTimestamps client is required; install opentimestamps-client before minting"
  echo "  ============================================================"
  echo "   MINT A PERMANENT DOI ON PRODUCTION ZENODO (irreversible)"
  echo "   Project: $P_NAME   Artifact: $P_ART   SHA-256: $SHA"
  echo "  ============================================================"
  read -r -p "  Type MINT to proceed: " C
  [ "$C" = "MINT" ] || { st "mint aborted"; exit 0; }
  hd "4a. REQUIRED OPENTIMESTAMPS"
  "$OTS" stamp "$P_ART" 2>&1 | tee -a "$LOG" || die "OpenTimestamps stamping failed; DOI was not minted"
  [ -s "$P_ART.ots" ] || die "OpenTimestamps did not produce a proof; DOI was not minted"
  mkdir -p "$P_PROV"
  mv -f "$P_ART.ots" "$P_PROV/" || die "could not preserve the OpenTimestamps proof; DOI was not minted"
  st "OTS proof created: $P_PROV/$(basename "$P_ART").ots"
  hd "4b. MINT DOI"
  "$MISTY" publish -m misty.json -f "$P_ART" --package-dir ".doi-package" --output "misty_result.json" 2>&1 | tee -a "$LOG"
  DOI="$(python3 -c "import json;print(json.load(open('misty_result.json'))['doi'])" 2>/dev/null || true)"
  [ -n "$DOI" ] || die "could not read DOI from misty_result.json"
  st "DOI MINTED: $DOI"; echo "$DOI" > ZENODO_DOI.txt
  if [ -n "$P_PH" ]; then
    for f in "${P_INJECT[@]}"; do
      [ -f "$f" ] && grep -q "$P_PH" "$f" && python3 - "$f" "$P_PH" "$DOI" <<'PY'
import sys;p,ph,doi=sys.argv[1:4];s=open(p,encoding='utf-8').read();open(p,'w',encoding='utf-8').write(s.replace(ph,doi));print("   injected:",p)
PY
    done
  fi
  st "DOI minted; preserve and publish the DOI-injected files and $P_PROV/*.ots using a non-force push"
fi

# ---- 6. backlog issues ----
if [ "$DO_ISSUES" = "1" ]; then
  hd "6. OPEN BACKLOG ISSUES on $P_REPO"
  command -v gh >/dev/null 2>&1 || die "gh not found"
  [ -f "$P_BACKLOG" ] || die "backlog missing: $P_BACKLOG"
  gh repo view "$P_REPO" >/dev/null 2>&1 || die "repo not found — run --push first"
  mapfile -t ITEMS < <(awk '/^## Sprint/{f=1;next}/^## /{f=0}f&&/- \[ \]/{sub(/^- \[ \] /,"");print}' "$P_BACKLOG")
  echo "  ${#ITEMS[@]} open backlog items:"; printf '   • %s\n' "${ITEMS[@]}"
  read -r -p "  Type YES to open these as GitHub issues: " C
  if [ "$C" = "YES" ]; then
    for it in "${ITEMS[@]}"; do
      title="$(echo "$it" | sed -E 's/\*\*//g; s/ — .*//')"
      body="$(echo "$it" | sed -E 's/^.*— //')"
      gh issue create -R "$P_REPO" -t "$title" -b "$body"$'\n\n(From '"$P_BACKLOG"$')' 2>>"$LOG" \
        && echo "   opened: $title" || echo "   FAILED: $title"
    done
  else st "issues skipped"; fi
fi

hd "DONE"
echo "  project : $P_NAME"
[ -f ZENODO_DOI.txt ] && echo "  DOI     : $(cat ZENODO_DOI.txt)"
echo "  log     : $LOG"
echo "  maintain contract and context."
