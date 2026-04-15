#!/usr/bin/env python3
"""Print export-gate eligibility for a list of mailboxes (validation / QA).

Reads addresses from ``--file`` (one per line, or any line parseable by ``emails_in``)
or from stdin. Uses the same ``build_marketing_export_gate_context`` +
``evaluate_export_eligibility`` as archive / lead exports.

Example::

  uv run python scripts/leads/advanced/audit_emails_export_gate.py \\
    --file reports/out/active/sent_contacts.txt \\
    --gmail-user contacto@origenlab.cl
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.candidate_export_gate import evaluate_export_eligibility
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.marketing_export_context import (
    DEFAULT_SENT_FOLDERS,
    build_marketing_export_gate_context,
)


def _load_emails(path: Path | None) -> list[str]:
    if path is None:
        raw = sys.stdin.read()
    else:
        raw = path.read_text(encoding="utf-8")
    seen: set[str] = set()
    out: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        for e in emails_in(s):
            if e not in seen:
                seen.add(e)
                out.append(e)
            break
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", "-f", type=Path, default=None, help="Input file (default: stdin)")
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--gmail-user", type=str, default="")
    ap.add_argument("--sent-folder", action="append", default=[])
    ap.add_argument(
        "--strict-contact-graph-noise",
        action="store_true",
        help="Stricter noise rules (contact_master / archive path).",
    )
    ap.add_argument("--csv-out", type=Path, default=None)
    args = ap.parse_args()

    addrs = _load_emails(args.file)
    if not addrs:
        print("No addresses to audit.", file=sys.stderr)
        return 2

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    gmail_user = (args.gmail_user or settings.gmail_workspace_user or "contacto@origenlab.cl").strip()
    sent_folders = tuple(args.sent_folder) if args.sent_folder else DEFAULT_SENT_FOLDERS

    conn = connect(db_path)
    try:
        ctx = build_marketing_export_gate_context(
            conn,
            gmail_user=gmail_user,
            sent_folders=sent_folders,
            strict_contact_graph_noise=bool(args.strict_contact_graph_noise),
        )
        rows: list[dict[str, str]] = []
        for em in addrs:
            g = evaluate_export_eligibility(
                contact_email=em,
                institution_name=None,
                ctx=ctx,
            )
            reason = g.reasons[0] if g.reasons else ""
            rows.append(
                {
                    "contact_email": em,
                    "eligible": "yes" if g.eligible else "no",
                    "reject_reason": reason,
                }
            )
    finally:
        conn.close()

    if args.csv_out:
        args.csv_out.parent.mkdir(parents=True, exist_ok=True)
        with args.csv_out.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["contact_email", "eligible", "reject_reason"])
            w.writeheader()
            w.writerows(rows)

    blocked = sum(1 for r in rows if r["eligible"] != "yes")
    print(f"audited={len(rows)} blocked={blocked} gmail_user={gmail_user!r}")
    for r in rows:
        if r["eligible"] != "yes":
            print(f"  BLOCK {r['contact_email']}: {r['reject_reason']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
