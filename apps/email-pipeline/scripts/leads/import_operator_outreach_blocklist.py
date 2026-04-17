#!/usr/bin/env python3
"""Load operator never-contact lists into SQLite (email + domain suppressions).

Reads line-oriented files (``#`` comments and blank lines ignored). Upserts:

- ``contact_email_suppression`` (``manual_do_not_contact``)
- ``contact_domain_suppression`` (full-domain block for the shared export gate)

Default data files ship under ``data/`` in this app. Example::

  uv run python scripts/leads/import_operator_outreach_blocklist.py \\
    --db ~/data/origenlab-email/sqlite/emails.sqlite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.contact_domain_suppression import (
    ensure_contact_domain_suppression_table,
    upsert_contact_domain_suppression,
    validate_contact_domain_suppression_payload,
)
from origenlab_email_pipeline.contact_email_suppression import (
    ensure_contact_email_suppression_table,
    upsert_contact_email_suppression,
    validate_contact_email_suppression_payload,
)
from origenlab_email_pipeline.db import connect


def _iter_file_lines(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    out: list[str] = []
    for line in text.splitlines():
        s = line.split("#", 1)[0].strip()
        if s:
            out.append(s)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument(
        "--emails-file",
        type=Path,
        default=_ROOT / "data" / "operator_outreach_blocklist_emails.txt",
        help="Newline-separated emails (default: bundled data file).",
    )
    ap.add_argument(
        "--domains-file",
        type=Path,
        default=_ROOT / "data" / "operator_outreach_blocklist_domains.txt",
        help="Newline-separated registrable domains (default: bundled data file).",
    )
    ap.add_argument(
        "--email-note",
        default="Operator outreach blocklist (import_operator_outreach_blocklist)",
        help="suppression_reason_text for email rows.",
    )
    ap.add_argument(
        "--domain-note",
        default="Operator outreach domain blocklist (import_operator_outreach_blocklist)",
        help="suppression_reason_text for domain rows.",
    )
    ap.add_argument("--updated-by", default="import_operator_outreach_blocklist.py")
    ap.add_argument(
        "--skip-emails",
        action="store_true",
        help="Only import domains file.",
    )
    ap.add_argument(
        "--skip-domains",
        action="store_true",
        help="Only import emails file.",
    )
    args = ap.parse_args()

    db_path = args.db or load_settings().sqlite_path
    n_emails = 0
    n_domains = 0

    conn = connect(db_path)
    try:
        if not args.skip_emails:
            if not args.emails_file.is_file():
                print(f"Missing emails file: {args.emails_file}", file=sys.stderr)
                return 2
            ensure_contact_email_suppression_table(conn)
            for raw in _iter_file_lines(args.emails_file):
                payload = validate_contact_email_suppression_payload(
                    email=raw,
                    suppression_reason_code="manual_do_not_contact",
                    suppression_reason_text=args.email_note,
                    suppression_source="import_operator_outreach_blocklist",
                    last_bounced_at=None,
                    updated_by=args.updated_by,
                )
                upsert_contact_email_suppression(conn, payload=payload)
                n_emails += 1
                print(f"email  suppressed: {payload.email}")

        if not args.skip_domains:
            if not args.domains_file.is_file():
                print(f"Missing domains file: {args.domains_file}", file=sys.stderr)
                return 2
            ensure_contact_domain_suppression_table(conn)
            for raw in _iter_file_lines(args.domains_file):
                dp = validate_contact_domain_suppression_payload(
                    domain=raw,
                    suppression_reason_text=args.domain_note,
                    updated_by=args.updated_by,
                )
                upsert_contact_domain_suppression(conn, payload=dp)
                n_domains += 1
                print(f"domain suppressed: {dp.domain_norm}")

        conn.commit()
    finally:
        conn.close()

    print(f"Done. emails={n_emails} domains={n_domains} db={db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
