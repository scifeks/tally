#!/bin/bash
# npm-audit-wrapper.sh
# Usage: npm-audit-wrapper.sh <repo_path> [--json]
#
# If a package-lock.json already exists, runs npm audit directly.
# If not, copies the repo to a temp dir, generates a lockfile, then audits.
# The original repo is never modified.

set -euo pipefail

REPO_PATH="${1:?Usage: npm-audit-wrapper.sh <repo_path> [--json]}"
shift
EXTRA_ARGS=("$@")

if [ ! -f "$REPO_PATH/package.json" ]; then
  echo "ERROR: No package.json found in $REPO_PATH" >&2
  exit 1
fi

if [ -f "$REPO_PATH/package-lock.json" ]; then
  # Lockfile exists — audit in place
  cd "$REPO_PATH"
  exec npm audit "${EXTRA_ARGS[@]}"
fi

# No lockfile — work from a temp copy
TMPDIR=$(mktemp -d)
trap 'rm -rf "$TMPDIR"' EXIT

cp -r "$REPO_PATH/." "$TMPDIR/"
cd "$TMPDIR"

echo "INFO: No package-lock.json found, generating one in temp dir..." >&2
npm install --package-lock-only --ignore-scripts 2>&1 >&2

exec npm audit "${EXTRA_ARGS[@]}"
