#!/usr/bin/env bash
# apidocs stage 3 driver: one claude -p invocation per route, skipping done work.
# Usage: enrich-driver.sh --repo REPO [-j N] [-n MAX] [--force] [--app NAME]
set -euo pipefail

REPO="" APIDOCS_DIR="apidocs" JOBS=1 MAX=0 FORCE=0 APP=""
while [[ $# -gt 0 ]]; do case "$1" in
  --repo) REPO="$2"; shift 2;;
  -j) JOBS="$2"; shift 2;;
  -n) MAX="$2"; shift 2;;
  --force) FORCE=1; shift;;
  --app) APP="$2"; shift 2;;
  *) echo "unknown arg: $1" >&2; exit 1;;
esac; done

[[ -n "$REPO" ]] || { echo "--repo is required" >&2; exit 1; }
REPO="$(cd "$REPO" && pwd)"
APIDOCS="$REPO/${APIDOCS_DIR:-apidocs}"

mkdir -p "$APIDOCS/routes"
[[ -f "$APIDOCS/routes.jsonl" ]] || { echo "no $APIDOCS/routes.jsonl — run discovery first" >&2; exit 1; }

enrich_one() {
  local line="$1" id
  id=$(jq -r .id <<<"$line")
  if [[ -f "$APIDOCS/routes/$id.json" && "$FORCE" -eq 0 ]]; then
    echo "skip $id (exists)"; return 0
  fi
  echo "enrich $id: $(jq -r '"\(.method) \(.path)"' <<<"$line")"
  (cd "$REPO" && claude -p --agent apidocs-enrich \
    "Use the apidocs-enrich agent to enrich this route and write $APIDOCS/routes/$id.json$( ((FORCE)) && echo ' --force'). Route entry: $line") \
    || echo "FAILED $id" >> "$APIDOCS/enrich-failures.log"
}
export -f enrich_one
export REPO APIDOCS FORCE

FILTER='.'
[[ -n "$APP" ]] && FILTER="select(.app == \"$APP\")"
SRC=$(jq -c "$FILTER" "$APIDOCS/routes.jsonl")
[[ "$MAX" -gt 0 ]] && SRC=$(head -n "$MAX" <<<"$SRC")

if [[ "$JOBS" -gt 1 ]] && command -v parallel >/dev/null; then
  parallel -j "$JOBS" enrich_one <<<"$SRC"
else
  while IFS= read -r line; do [[ -n "$line" ]] && enrich_one "$line"; done <<<"$SRC"
fi

total=$(wc -l <<<"$SRC" | tr -d ' ')
done_n=$(find "$APIDOCS/routes" -name '*.json' 2>/dev/null | wc -l | tr -d ' ')
echo "---"
echo "routes in scope: $total | fragments on disk: $done_n"
[[ -f "$APIDOCS/enrich-failures.log" ]] && { echo "failures:"; sort -u "$APIDOCS/enrich-failures.log"; }
