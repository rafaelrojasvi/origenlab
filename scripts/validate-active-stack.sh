#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

section() {
  printf "\n== %s ==\n" "$1"
}

section "email-pipeline"
(cd "$ROOT_DIR/apps/email-pipeline" && ./scripts/validate.sh)

section "api"
(cd "$ROOT_DIR/apps/api" && ./scripts/validate.sh)

section "dashboard"
(cd "$ROOT_DIR/apps/dashboard" && npm run validate)

section "done"
echo "Active operator stack validation passed."
