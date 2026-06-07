#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

section() {
  printf "\n== %s ==\n" "$1"
}

check_clean_tree() {
  local phase="$1"
  if ! git -C "$ROOT_DIR" diff --quiet || ! git -C "$ROOT_DIR" diff --cached --quiet; then
    echo "Working tree is dirty ${phase}:"
    git -C "$ROOT_DIR" status --short
    echo
    echo "Clean deliberately before validating:"
    echo "  git restore <path>"
    echo
    echo "If this is lockfile drift, inspect before restoring."
    exit 1
  fi
}

section "preflight working tree check"
check_clean_tree "before validation"

section "email-pipeline"
(cd "$ROOT_DIR/apps/email-pipeline" && ./scripts/validate.sh)

section "api"
(cd "$ROOT_DIR/apps/api" && ./scripts/validate.sh)

section "dashboard"
(cd "$ROOT_DIR/apps/dashboard" && npm run validate)

section "working tree check"
check_clean_tree "after validation"

section "done"
echo "Active operator stack validation passed and working tree is clean."
