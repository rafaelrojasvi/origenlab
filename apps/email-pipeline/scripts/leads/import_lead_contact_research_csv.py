#!/usr/bin/env python3
"""Import reviewed DeepSearch/ChatGPT contact findings into lead_contact_research.

This importer is conservative by default:
- dry-run unless --apply
- preserves raw lead_master fields
- does not overwrite existing research rows unless --replace-existing
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from origenlab_email_pipeline.business_mart import emails_in
from origenlab_email_pipeline.candidate_export_gate import normalize_export_email
from origenlab_email_pipeline.config import load_settings
from origenlab_email_pipeline.db import connect
from origenlab_email_pipeline.lead_contact_research import (
    fetch_contact_research_row,
    upsert_contact_research,
    validate_contact_research_payload,
)
from origenlab_email_pipeline.lead_export_queries import sql_upstream_active_lead_master
from origenlab_email_pipeline.leads_schema import ensure_leads_tables
from origenlab_email_pipeline.csv_contracts import (
    has_required_columns,
    normalize_header_name,
    normalize_row_dict,
    read_csv_normalized,
)

_REQUIRED_COLUMNS: tuple[str, ...] = (
    "lead_id",
    "org_name",
    "resolved_domain",
    "resolved_contact_email",
    "resolved_contact_name",
    "contact_source_url",
    "source_type",
    "confidence",
    "notes",
)

_ALLOWED_CONFIDENCE = {"high", "medium", "low", ""}
_STATUS_MAP = {
    "resolved_contact_found": "contacto_encontrado",
    "no_contact_found": "descartado",
    "needs_review": "investigar_contacto",
}
_FREE_EMAIL_DOMAINS = {
    "gmail.com",
    "hotmail.com",
    "outlook.com",
    "yahoo.com",
    "icloud.com",
    "live.com",
    "protonmail.com",
}


def _norm_row(row: dict[str, str]) -> dict[str, str]:
    return normalize_row_dict(row)


def _email_domain(email: str) -> str:
    return email.rsplit("@", 1)[-1].strip().lower()


def _looks_official_url(url: str) -> bool:
    u = url.strip().lower()
    return u.startswith("https://") or u.startswith("http://")


def _url_host(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").strip().lower()
    except ValueError:
        return ""


def _host_matches_domain(host: str, domain: str) -> bool:
    d = (domain or "").strip().lower()
    h = (host or "").strip().lower()
    if not d or not h:
        return False
    return h == d or h.endswith("." + d)


def _is_generic_localpart(email: str) -> bool:
    local = (email.split("@", 1)[0] if "@" in email else "").strip().lower()
    return local in {
        "info",
        "contacto",
        "contact",
        "ventas",
        "sales",
        "admin",
        "soporte",
        "support",
        "compras",
        "adquisiciones",
        "facturacion",
        "billing",
        "noreply",
        "no-reply",
        "postmaster",
    }


def _load_rows(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    headers, rows = read_csv_normalized(path)
    return rows, headers


def _infer_status(*, resolved_contact_email: str, confidence: str, source_url: str) -> str:
    if resolved_contact_email:
        if confidence == "low" or not source_url:
            return "needs_review"
        return "resolved_contact_found"
    return "no_contact_found"


def _coverage_report(conn) -> dict[str, int]:
    where = sql_upstream_active_lead_master("lm")
    rows = conn.execute(
        f"""
        SELECT lm.id, COALESCE(lm.fit_bucket, 'low_fit') AS fit_bucket,
               COALESCE(NULLIF(TRIM(lm.email_norm), ''), NULLIF(TRIM(lm.email), '')) AS lead_email,
               lcr.resolved_contact_email
        FROM lead_master lm
        LEFT JOIN lead_contact_research lcr ON lcr.lead_id = lm.id
        WHERE {where}
          AND COALESCE(lm.fit_bucket, 'low_fit') IN ('high_fit', 'medium_fit')
        """
    ).fetchall()

    total = len(rows)
    with_original = 0
    with_researched = 0
    still_missing = 0
    ready_for_gate = 0

    for _, _fit, lead_email, researched in rows:
        le = normalize_export_email(str(lead_email or "").strip())
        re = normalize_export_email(str(researched or "").strip())
        if le:
            with_original += 1
        if re:
            with_researched += 1
        if not le and not re:
            still_missing += 1
        if le or re:
            ready_for_gate += 1

    return {
        "total_high_medium": total,
        "with_original_lead_email": with_original,
        "with_resolved_researched_email": with_researched,
        "still_missing_contact": still_missing,
        "ready_for_gate_audit": ready_for_gate,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--input", type=Path, required=True, help="CSV path with reviewed enrichment columns")
    ap.add_argument("--db", type=Path, default=None, help="SQLite path (default: from config)")
    ap.add_argument("--apply", action="store_true", help="Write changes (default: dry-run)")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit dry-run mode (same as default when --apply is not set).",
    )
    ap.add_argument(
        "--replace-existing",
        action="store_true",
        help="Allow overwrite when lead already has a lead_contact_research row",
    )
    ap.add_argument("--updated-by", default="csv_import", help="updated_by value in lead_contact_research")
    ap.add_argument(
        "--allow-deepsearch-aliases",
        action="store_true",
        help=(
            "Allow reviewed CSV aliases (institution_name->org_name, contact_email->resolved_contact_email). "
            "Default keeps strict reviewed schema."
        ),
    )
    args = ap.parse_args()

    rows, headers = _load_rows(args.input)
    if args.allow_deepsearch_aliases:
        rows2: list[dict[str, str]] = []
        for r in rows:
            nr = dict(r)
            if "org_name" not in nr and "institution_name" in nr:
                nr["org_name"] = nr.get("institution_name", "")
            if "resolved_contact_email" not in nr and "contact_email" in nr:
                nr["resolved_contact_email"] = nr.get("contact_email", "")
            rows2.append(nr)
        rows = rows2
        headers = sorted({normalize_header_name(k) for rr in rows for k in rr.keys()})

    ok_required, missing = has_required_columns(headers, _REQUIRED_COLUMNS)
    if not ok_required:
        missing = list(missing)
    if missing:
        print(f"Missing required columns: {', '.join(missing)}", file=sys.stderr)
        return 1

    settings = load_settings()
    db = args.db or settings.resolved_sqlite_path()
    conn = connect(db)
    ensure_leads_tables(conn)

    seen_ids: set[int] = set()
    decisions: list[dict[str, object]] = []
    applied = 0

    try:
        for i, row in enumerate(rows, start=2):
            rid = row.get("lead_id", "")
            try:
                lead_id = int(rid)
            except (TypeError, ValueError):
                decisions.append({"lead_id": -1, "action": "reject", "reason": f"line {i}: invalid lead_id"})
                continue

            if str(lead_id) != rid.strip():
                decisions.append(
                    {"lead_id": lead_id, "action": "reject", "reason": f"line {i}: lead_id must be exact integer text"}
                )
                continue
            if lead_id in seen_ids:
                decisions.append({"lead_id": lead_id, "action": "reject", "reason": f"line {i}: duplicate lead_id in CSV"})
                continue
            seen_ids.add(lead_id)

            exists = conn.execute("SELECT id, org_name, domain_norm FROM lead_master WHERE id = ?", (lead_id,)).fetchone()
            if not exists:
                decisions.append({"lead_id": lead_id, "action": "reject", "reason": f"line {i}: lead_id not found"})
                continue

            resolved_email = (row.get("resolved_contact_email") or "").strip().lower()
            confidence = (row.get("confidence") or "").strip().lower()
            source_url = (row.get("contact_source_url") or "").strip()
            source_type = (row.get("source_type") or "").strip()
            lead_domain = str(exists[2] or "").strip().lower()
            resolved_domain = (row.get("resolved_domain") or "").strip().lower()

            if confidence not in _ALLOWED_CONFIDENCE:
                decisions.append({"lead_id": lead_id, "action": "reject", "reason": f"line {i}: bad confidence"})
                continue

            if resolved_email:
                parsed = emails_in(resolved_email)
                if not parsed or parsed[0] != resolved_email:
                    decisions.append({"lead_id": lead_id, "action": "reject", "reason": f"line {i}: invalid email format"})
                    continue
                if confidence == "low" and _email_domain(resolved_email) in _FREE_EMAIL_DOMAINS:
                    decisions.append(
                        {
                            "lead_id": lead_id,
                            "action": "reject",
                            "reason": f"line {i}: low-confidence free-mail address rejected",
                        }
                    )
                    continue

            if confidence == "high" and (not source_url or not _looks_official_url(source_url)):
                decisions.append(
                    {
                        "lead_id": lead_id,
                        "action": "reject",
                        "reason": f"line {i}: high confidence requires official source URL",
                    }
                )
                continue
            if confidence == "high":
                host = _url_host(source_url)
                official = _host_matches_domain(host, resolved_domain) or _host_matches_domain(host, lead_domain)
                if not official:
                    decisions.append(
                        {
                            "lead_id": lead_id,
                            "action": "reject",
                            "reason": f"line {i}: high confidence URL host must match lead/resolved domain",
                        }
                    )
                    continue
            if confidence == "low" and resolved_email:
                if not source_url:
                    decisions.append(
                        {
                            "lead_id": lead_id,
                            "action": "reject",
                            "reason": f"line {i}: low confidence contact requires source URL",
                        }
                    )
                    continue
                if _is_generic_localpart(resolved_email):
                    decisions.append(
                        {
                            "lead_id": lead_id,
                            "action": "reject",
                            "reason": f"line {i}: low-confidence generic mailbox rejected",
                        }
                    )
                    continue

            existing = fetch_contact_research_row(conn, lead_id)
            if existing and not args.replace_existing:
                decisions.append({"lead_id": lead_id, "action": "skip", "reason": "existing_research_row"})
                continue

            status_label = _infer_status(
                resolved_contact_email=resolved_email,
                confidence=confidence,
                source_url=source_url,
            )
            status_db = _STATUS_MAP[status_label]

            resolved_domain = (row.get("resolved_domain") or "").strip() or lead_domain
            notes_parts = []
            if (row.get("notes") or "").strip():
                notes_parts.append((row.get("notes") or "").strip())
            if source_url:
                notes_parts.append(f"source_url={source_url}")
            if source_type:
                notes_parts.append(f"source_type={source_type}")
            if confidence:
                notes_parts.append(f"confidence={confidence}")
            notes_parts.append(f"import_status={status_label}")
            notes = " | ".join(notes_parts)

            payload = validate_contact_research_payload(
                contact_research_status=status_db,
                resolved_domain=resolved_domain or None,
                resolved_contact_name=(row.get("resolved_contact_name") or "").strip() or None,
                resolved_contact_email=resolved_email or None,
                contact_source=source_type or None,
                contact_research_notes=notes or None,
                updated_by=(args.updated_by or "").strip() or None,
            )

            decisions.append({"lead_id": lead_id, "action": "upsert", "reason": status_label})
            if args.apply:
                upsert_contact_research(conn, lead_id=lead_id, payload=payload)
                applied += 1

        if args.apply:
            conn.commit()
        else:
            conn.rollback()

        summary = {
            "mode": "apply" if args.apply else "dry_run",
            "input_rows": len(rows),
            "upsert_candidates": sum(1 for d in decisions if d["action"] == "upsert"),
            "applied": applied,
            "skipped_existing": sum(1 for d in decisions if d["action"] == "skip"),
            "rejected": sum(1 for d in decisions if d["action"] == "reject"),
        }
        coverage = _coverage_report(conn)
        print(json.dumps({"summary": summary, "coverage": coverage}, ensure_ascii=False, indent=2))

        if summary["rejected"]:
            for d in decisions:
                if d["action"] == "reject":
                    print(f"reject lead_id={d['lead_id']}: {d['reason']}", file=sys.stderr)

        return 0 if summary["rejected"] == 0 else 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
