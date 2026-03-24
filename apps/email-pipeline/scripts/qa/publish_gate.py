#!/usr/bin/env python3
"""**Final combined** publish decision: pack/DB/top20 verify, then operational audit, then evidence.

1. ``verify_client_pack_consistency`` — pack vs DB and top20 consistency only (not full operational
   validation). Cohort partition is **not** run there.
2. ``audit_operational_trust`` — cohort partition, readiness, freshness, taxonomy, merged hunt,
   scorecard, provenance.
3. Evidence step (unless skipped).

Exit non-zero if any critical check fails.

``audit_operational_trust`` embeds a factual ``provenance`` object in
``reports/out/active/operational_trust_scorecard.json`` (paths, DB, ``operational_run_id`` from
``ORIGENLAB_LEADS_OPERATIONAL_RUN_ID`` when the stack exported it, optional stack manifest echo).
Correlate with ``client_pack_latest/summary.json`` ``provenance.operational_run_id`` and
``operational_stack_last_run.json`` ``run_id`` for the same stack run; timestamps alone do not
prove ordering.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _load_qa_module(stem: str):
    path = Path(__file__).resolve().parent / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(f"qa_{stem}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo-root", type=Path, default=REPO)
    p.add_argument(
        "--db",
        type=Path,
        default=None,
        help="SQLite path (passed to scripts that need it)",
    )
    p.add_argument(
        "--max-pack-age-hours",
        type=float,
        default=168.0,
        help="Stale threshold for client_pack (audit script)",
    )
    p.add_argument(
        "--skip-evidence-http",
        action="store_true",
        help="Skip check_evidence_links.py (no live HTTP)",
    )
    p.add_argument(
        "--evidence-timeout",
        type=float,
        default=20.0,
    )
    p.add_argument(
        "--evidence-max-failures",
        type=int,
        default=5,
    )
    p.add_argument(
        "--evidence-max-fail-ratio",
        type=float,
        default=0.15,
    )
    p.add_argument(
        "--json-out",
        type=Path,
        default=None,
        help="Override operational trust scorecard JSON path (audit step)",
    )
    p.add_argument(
        "--md-out",
        type=Path,
        default=None,
        help="Override operational trust scorecard Markdown path (audit step)",
    )
    return p


def main() -> None:
    args = build_parser().parse_args()
    args.repo_root = args.repo_root.resolve()
    if args.db is not None:
        args.db = args.db.resolve()
    # check_evidence_links.run() expects these names
    args.timeout = args.evidence_timeout
    args.max_failures = args.evidence_max_failures
    args.max_fail_ratio = args.evidence_max_fail_ratio

    verify = _load_qa_module("verify_client_pack_consistency")
    audit = _load_qa_module("audit_operational_trust")
    evidence = _load_qa_module("check_evidence_links")

    rc = 0
    steps: list[tuple[str, int]] = []

    print("=== verify_client_pack_consistency ===")
    v = verify.run(args)
    steps.append(("verify_client_pack_consistency", v))
    rc = max(rc, v)

    print("=== audit_operational_trust ===")
    a = audit.run(args)
    steps.append(("audit_operational_trust", a))
    rc = max(rc, a)

    if args.skip_evidence_http:
        print("=== check_evidence_links (skipped) ===")
        steps.append(("check_evidence_links", 0))
    else:
        print("=== check_evidence_links ===")
        e = evidence.run(args)
        steps.append(("check_evidence_links", e))
        rc = max(rc, e)

    print("=== publish_gate summary ===")
    for name, code in steps:
        print(f"  {name}: exit {code}")
    print(f"publish_gate: {'PASS' if rc == 0 else 'FAIL'} (aggregate exit {rc})")
    raise SystemExit(rc)


if __name__ == "__main__":
    main()
