#!/usr/bin/env bash
# API-3 Phase 5A: deletion-readiness dry run (report only; does not delete anything).
#
# 1. Runs api3_phase6_grep_gate.sh in strict mode (no WARN_ONLY).
# 2. Prints allowlisted vs unallowlisted hit counts for the same patterns.
# 3. Scans references to apps/email-pipeline/src/origenlab_api (legacy tree path).
#
# Usage:
#   apps/api/scripts/api3_phase5a_deletion_audit.sh
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GATE="${SCRIPT_DIR}/api3_phase6_grep_gate.sh"
ALLOWLIST="${SCRIPT_DIR}/api3_phase6_grep_allowlist.txt"

echo "== API-3 Phase 5A deletion-readiness audit =="
echo "Repo: ${ROOT}"
echo

echo "--- Strict Phase 6 grep gate ---"
set +e
GATE_OUT="$("${GATE}" 2>&1)"
GATE_RC=$?
set -e
echo "${GATE_OUT}"
echo "Strict gate exit code: ${GATE_RC}"
echo

echo "--- Hit inventory (same patterns as gate + legacy tree path) ---"
export ROOT ALLOWLIST
python3 <<'PY'
from __future__ import annotations

import os
import subprocess
from collections import defaultdict
from pathlib import Path

ROOT = Path(os.environ["ROOT"])
ALLOWLIST = Path(os.environ["ALLOWLIST"])

PATTERNS = [
    r"127\.0\.0\.1:8000",
    r"localhost:8000",
    r"port 8000",
    r"port :8000",
    r"/dashboard/summary",
    r"/classification/",
    r"/commercial/purchase-events",
    r"/meta/dashboard-sync",
    r"/outbound/",
    r"smoke:legacy",
    r"legacy-smoke",
    r'apiUrl\("/contacts',
    r'apiUrl\("/organizations',
    r'GET /contacts"',
    r"GET /organizations",
    r'"/contacts"',
    r"/mirror/contacts",
]
LEGACY_TREE = "apps/email-pipeline/src/origenlab_api"

RG_OPTS = [
    "--no-heading",
    "--line-number",
    "--glob",
    "!.venv/**",
    "--glob",
    "!**/.venv/**",
    "--glob",
    "!**/node_modules/**",
    "--glob",
    "!**/dist/**",
    "--glob",
    "!.git/**",
    "--glob",
    "!**/uv.lock",
    "--glob",
    "!**/package-lock.json",
]


def load_allowlist() -> list[str]:
    out: list[str] = []
    for raw in ALLOWLIST.read_text().splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            out.append(line)
    return out


def is_allowlisted(rel: str, prefixes: list[str]) -> bool:
    return any(rel == p or rel.startswith(p) for p in prefixes)


def collect(pat: str) -> list[tuple[str, int, str]]:
    proc = subprocess.run(
        ["rg", *RG_OPTS, "--regexp", pat, str(ROOT)],
        capture_output=True,
        text=True,
    )
    rows: list[tuple[str, int, str]] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        rel, rest = line.split(":", 1)
        rel = rel.removeprefix(str(ROOT) + "/").removeprefix("./")
        line_no, text = rest.split(":", 1)
        rows.append((rel, int(line_no), text.strip()))
    return rows


prefixes = load_allowlist()
seen: set[tuple[str, int, str]] = set()
allow = 0
viol = 0
by_prefix: defaultdict[str, int] = defaultdict(int)
legacy_tree_refs = 0
legacy_tree_outside = 0

for pat in PATTERNS + [LEGACY_TREE.replace("/", r"\/"), LEGACY_TREE]:
    for rel, _ln, _text in collect(pat):
        key = (rel, _ln, pat)
        if key in seen:
            continue
        seen.add(key)
        if LEGACY_TREE in rel or pat == LEGACY_TREE:
            legacy_tree_refs += 1
            if not is_allowlisted(rel, prefixes):
                legacy_tree_outside += 1
        if is_allowlisted(rel, prefixes):
            allow += 1
            for p in prefixes:
                if rel == p or rel.startswith(p):
                    by_prefix[p] += 1
                    break
        else:
            viol += 1

print(f"Unique pattern hits: {len(seen)}")
print(f"Allowlisted hits: {allow}")
print(f"Unallowlisted hits: {viol}")
print(f"References to legacy tree path ({LEGACY_TREE}): {legacy_tree_refs}")
print(f"Legacy tree path refs outside allowlist: {legacy_tree_outside}")
print()
print("Top allowlist prefixes:")
for p, c in sorted(by_prefix.items(), key=lambda x: -x[1])[:12]:
    print(f"  {c:4d}  {p}")

if viol:
    print()
    print("Sample unallowlisted (first 15):")
    # re-walk for samples
    samples = []
    for pat in PATTERNS:
        for rel, ln, text in collect(pat):
            if is_allowlisted(rel, prefixes):
                continue
            samples.append(f"  {rel}:{ln} [{pat}] {text[:72]}")
            if len(samples) >= 15:
                break
        if len(samples) >= 15:
            break
    print("\n".join(samples))

legacy_main = ROOT / LEGACY_TREE / "main.py"
print()
if legacy_main.is_file():
    print(f"Legacy package present: {LEGACY_TREE}/main.py")
else:
    print(f"WARNING: missing {LEGACY_TREE}/main.py")
PY

echo
echo "--- Verdict preview ---"
if [[ "${GATE_RC}" -eq 0 ]]; then
  echo "Mechanical grep gate: PASS (zero unallowlisted route/port hits)."
else
  echo "Mechanical grep gate: FAIL (see unallowlisted hits above)."
fi
echo "Deletion safe now: NO — legacy tree and allowlisted compat refs must remain until Phase 6."
echo "See apps/api/docs/API-3_PHASE5A_DELETION_READINESS.md"
