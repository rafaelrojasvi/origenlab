#!/usr/bin/env python3
"""Import a v1.2 contact-hunt CSV (merged with Deep Research) into SQLite.

Writes one row per ``id_lead`` into ``lead_outreach_enrichment`` (full row as JSON).
Optionally copies procurement columns into ``lead_master`` for simple queries.

Re-normalizing leads will **not** wipe ``lead_outreach_enrichment``. With the updated
``normalize_leads.py`` upsert logic, ``lead_master.email`` / ``phone`` / ``contact_name``
are preserved when the ChileCompra raw row has no contact fields, as long as you
imported them here (or typed them in).

Usage::

    uv run python scripts/leads/export_contact_hunt_sheet.py --out reports/out/hunt_base.csv --limit 500
    uv run python scripts/leads/merge_contact_hunt_enrichment.py \\
        -b reports/out/hunt_base.csv -e ~/Downloads/enriched.csv -o reports/out/hunt_merged.csv
    uv run python scripts/leads/validate_contact_hunt_alignment.py -c reports/out/active/leads_contact_hunt_current.csv \\
        -m reports/out/hunt_merged.csv
    uv run python scripts/leads/import_contact_hunt_to_sqlite.py \\
        --csv reports/out/hunt_merged.csv --promote-procurement \\
        --require-aligned-with reports/out/active/leads_contact_hunt_current.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.hunt_csv_alignment import describe_hunt_misalignment
from origenlab_email_pipeline.leads_ingest import now_iso
from origenlab_email_pipeline.leads_schema import ensure_leads_tables


def _read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        headers = list(r.fieldnames or [])
        rows = list(r)
    return headers, rows


def _non_empty_payload(row: dict[str, str]) -> dict[str, str]:
    return {k: v.strip() for k, v in row.items() if k and (v or "").strip()}


def main() -> int:
    ap = argparse.ArgumentParser(description="Import contact-hunt CSV into lead_outreach_enrichment.")
    ap.add_argument("--csv", "-c", type=Path, required=True, help="Merged contact-hunt CSV (must have id_lead).")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config).")
    ap.add_argument(
        "--promote-procurement",
        action="store_true",
        help="Copy nombre/email/teléfono compras into lead_master.contact_name, email, phone when present.",
    )
    ap.add_argument(
        "--skip-unknown-ids",
        action="store_true",
        help="Skip rows whose id_lead is not in lead_master (default: warn and skip).",
    )
    ap.add_argument(
        "--require-aligned-with",
        type=Path,
        default=None,
        metavar="BASE_CSV",
        help=(
            "If set, require the same id_lead set as this hunt CSV (typically "
            "leads_contact_hunt_current.csv) before importing merged rows. Exits with error if they differ."
        ),
    )
    args = ap.parse_args()

    if args.require_aligned_with is not None:
        base = args.require_aligned_with.resolve()
        merged_path = args.csv.resolve()
        msg = describe_hunt_misalignment(base, merged_path)
        if msg:
            print(msg, file=sys.stderr)
            return 1

    settings = load_settings()
    db_path = args.db or settings.resolved_sqlite_path()
    conn = connect(db_path)
    conn.execute("PRAGMA busy_timeout=30000")
    ensure_leads_tables(conn)

    headers, rows = _read_csv(args.csv)
    if "id_lead" not in headers:
        print("CSV must include id_lead column.", file=sys.stderr)
        return 1

    stored = 0
    promoted = 0
    skipped = 0
    errors = 0
    ts = now_iso()
    src_name = str(args.csv.resolve())

    for row in rows:
        rid_raw = (row.get("id_lead") or "").strip()
        if not rid_raw:
            skipped += 1
            continue
        try:
            lead_id = int(rid_raw)
        except ValueError:
            print(f"Warning: bad id_lead {rid_raw!r}", file=sys.stderr)
            errors += 1
            continue

        exists = conn.execute("SELECT 1 FROM lead_master WHERE id = ?", (lead_id,)).fetchone()
        if not exists:
            msg = f"id_lead={lead_id} not in lead_master"
            if args.skip_unknown_ids:
                print(f"Skip: {msg}", file=sys.stderr)
            else:
                print(f"Skip: {msg}", file=sys.stderr)
            skipped += 1
            continue

        payload = _non_empty_payload(row)
        if len(payload) <= 1:  # only id_lead
            skipped += 1
            continue

        conn.execute(
            """
            INSERT INTO lead_outreach_enrichment (lead_id, enrichment_json, source_file, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(lead_id) DO UPDATE SET
              enrichment_json = excluded.enrichment_json,
              source_file = excluded.source_file,
              updated_at = excluded.updated_at
            """,
            (lead_id, json.dumps(payload, ensure_ascii=False), src_name, ts),
        )
        stored += 1

        if args.promote_procurement:
            name = (row.get("nombre_contacto_compras") or "").strip()
            email = (row.get("email_publico_compras") or "").strip()
            phone = (row.get("telefono_publico_compras") or "").strip()
            if name or email or phone:
                conn.execute(
                    """
                    UPDATE lead_master SET
                      contact_name = COALESCE(NULLIF(?, ''), contact_name),
                      email = COALESCE(NULLIF(?, ''), email),
                      phone = COALESCE(NULLIF(?, ''), phone)
                    WHERE id = ?
                    """,
                    (name or None, email or None, phone or None, lead_id),
                )
                promoted += 1

    conn.commit()
    conn.close()
    print(f"Stored enrichment rows: {stored}")
    if args.promote_procurement:
        print(f"Rows with procurement promoted to lead_master: {promoted}")
    print(f"Skipped: {skipped}, errors: {errors}")
    return 0 if errors == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
