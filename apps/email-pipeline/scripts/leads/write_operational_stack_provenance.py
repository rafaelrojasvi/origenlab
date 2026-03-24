#!/usr/bin/env python3
"""Write operational stack run manifest: last-run pointer + per-run archive copy.

Updates ``reports/out/active/operational_stack_last_run.json`` and
``reports/out/active/operational_run_manifests/<run_id>.json`` with the same payload.

``run_id`` must match ``ORIGENLAB_LEADS_OPERATIONAL_RUN_ID`` when the stack set it.
``publish_gate.exit_code`` is null when publish_gate was skipped; 0 when passed; non-zero when run and failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.lead_provenance import (
    build_operational_stack_manifest_payload,
    operational_run_manifest_path,
    operational_stack_last_run_path,
    read_operational_run_id_from_env,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--repo-root",
        type=Path,
        default=_ROOT,
        help="Email-pipeline repo root (default: inferred)",
    )
    ap.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Operational run UUID (default: ORIGENLAB_LEADS_OPERATIONAL_RUN_ID)",
    )
    ap.add_argument(
        "--started-at-utc",
        type=str,
        required=True,
        help="Stack start timestamp (ISO UTC, e.g. from run_leads_operational_stack.sh)",
    )
    ap.add_argument(
        "--reconcile-mode",
        choices=("apply", "dry_run"),
        required=True,
        help="How reconcile_lead_upstream was invoked in this stack run",
    )
    ap.add_argument("--skip-fetch", type=int, choices=(0, 1), default=0)
    ap.add_argument("--skip-focus", type=int, choices=(0, 1), default=0)
    ap.add_argument("--skip-pack", type=int, choices=(0, 1), default=0)
    ap.add_argument("--skip-gate", type=int, choices=(0, 1), default=0)
    ap.add_argument(
        "--publish-gate-exit",
        type=int,
        default=None,
        help=(
            "publish_gate.py exit code when executed; use -1 when publish_gate was skipped "
            "(distinct from 0 pass). Ignored when --skip-gate 1."
        ),
    )
    args = ap.parse_args()
    repo = args.repo_root.resolve()
    run_id = (args.run_id or "").strip() or (read_operational_run_id_from_env() or "")
    if not run_id:
        print(
            "error: missing run_id (pass --run-id or set ORIGENLAB_LEADS_OPERATIONAL_RUN_ID)",
            file=sys.stderr,
        )
        return 2

    settings = load_settings()
    db_res = settings.resolved_sqlite_path().resolve()
    skip_gate = bool(args.skip_gate)
    gate_exit: int | None
    if skip_gate:
        gate_exit = None
    else:
        if args.publish_gate_exit is None:
            print(
                "error: --publish-gate-exit required when publish_gate was not skipped",
                file=sys.stderr,
            )
            return 2
        gate_exit = int(args.publish_gate_exit)

    completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = build_operational_stack_manifest_payload(
        repo_root=repo,
        run_id=run_id,
        started_at_utc=args.started_at_utc.strip(),
        completed_at_utc=completed_at,
        reconcile_mode=args.reconcile_mode,
        skip_fetch=bool(args.skip_fetch),
        skip_focus=bool(args.skip_focus),
        skip_pack=bool(args.skip_pack),
        skip_gate=skip_gate,
        publish_gate_exit_code=gate_exit,
        db_path_resolved=db_res,
    )

    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    last_path = operational_stack_last_run_path(repo)
    last_path.parent.mkdir(parents=True, exist_ok=True)
    last_path.write_text(text, encoding="utf-8")

    archive_path = operational_run_manifest_path(repo, run_id)
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(text, encoding="utf-8")

    print(f"Wrote operational stack manifest: {last_path}")
    print(f"Wrote run archive copy: {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
