"""Packaging-only helper: one shared HTML body + recipient list for manual operator sends.

No DB, no gate, no Gmail. Produces CSV, manifest, and a newline file for ``mark_outreach_state``.
"""

from __future__ import annotations

import csv
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.business_mart import emails_in

RECIPIENTS_CSV_NAME = "manual_html_outreach_recipients.csv"
MANIFEST_JSON_NAME = "manual_html_outreach_send_manifest.json"
MARK_CONTACTED_TXT_NAME = "manual_html_outreach_mark_contacted.txt"
SHARED_HTML_NAME = "shared_email.html"
PREVIEW_MD_NAME = "manual_html_outreach_preview.md"

SCHEMA_VERSION = "1"
DEFAULT_SUBJECT = "OrigenLab · Equipos para laboratorio en Chile"


def _normalize_header_row(row: dict[str, Any]) -> dict[str, str]:
    return {str(k or "").strip().lower(): str(v or "").strip() for k, v in row.items()}


def _pick_contact_email(norm: dict[str, str]) -> str | None:
    for key in ("contact_email", "email", "to"):
        raw = norm.get(key, "")
        if not raw:
            continue
        found = emails_in(raw)
        if found:
            return found[0]
    return None


def _read_input_rows(path: Path) -> list[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        return []
    rows: list[dict[str, str]] = []
    for raw in reader:
        norm = _normalize_header_row(raw)
        em = _pick_contact_email(norm)
        if not em:
            continue
        rows.append(
            {
                "_email": em,
                "institution_name": norm.get("institution_name", ""),
                "domain": norm.get("domain", ""),
            }
        )
    return rows


def run_manual_html_outreach_batch(
    *,
    input_csv: Path,
    html_path: Path,
    subject: str,
    out_dir: Path,
    limit: int | None = None,
    batch_name: str | None = None,
    copy_shared_html: bool = True,
    write_preview_md: bool = True,
) -> dict[str, Any]:
    """Build operator package under ``out_dir``. Returns manifest dict."""
    input_csv = Path(input_csv).resolve()
    html_path = Path(html_path).resolve()
    out_dir = Path(out_dir)
    if not input_csv.is_file():
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")
    if not html_path.is_file():
        raise FileNotFoundError(f"HTML file not found: {html_path}")

    subj = (subject or "").strip() or DEFAULT_SUBJECT
    bn = (batch_name or "").strip() or (
        f"{input_csv.stem}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    )

    raw_rows = _read_input_rows(input_csv)
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for r in raw_rows:
        em = r["_email"].strip().lower()
        if em in seen:
            continue
        seen.add(em)
        deduped.append(r)

    n_after_dedupe = len(deduped)
    if limit is not None:
        lim = max(0, int(limit))
        deduped = deduped[:lim]

    if not deduped:
        raise ValueError(
            "No valid recipients after reading input (need at least one row with a parseable contact_email)."
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    html_resolved = str(html_path)

    recipient_out: list[dict[str, str]] = []
    mark_lines: list[str] = []
    for r in deduped:
        em = r["_email"].strip().lower()
        recipient_out.append(
            {
                "contact_email": em,
                "institution_name": r.get("institution_name", ""),
                "domain": r.get("domain", ""),
                "subject": subj,
                "html_source_path": html_resolved,
                "batch_name": bn,
            }
        )
        mark_lines.append(em)

    recipients_path = out_dir / RECIPIENTS_CSV_NAME
    with recipients_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=[
                "contact_email",
                "institution_name",
                "domain",
                "subject",
                "html_source_path",
                "batch_name",
            ],
        )
        w.writeheader()
        w.writerows(recipient_out)

    mark_path = out_dir / MARK_CONTACTED_TXT_NAME
    mark_path.write_text("\n".join(mark_lines) + "\n", encoding="utf-8")

    if copy_shared_html:
        shutil.copy2(html_path, out_dir / SHARED_HTML_NAME)

    created = datetime.now(timezone.utc).isoformat()
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "batch_name": bn,
        "created_at_utc": created,
        "input_csv": str(input_csv),
        "html_source_path": html_resolved,
        "subject": subj,
        "counts": {
            "input_rows_with_valid_email": len(raw_rows),
            "recipients_after_dedupe": n_after_dedupe,
            "recipients_written": len(recipient_out),
            "limit_applied": int(limit) if limit is not None else None,
        },
        "artifacts": {
            "recipients_csv": str(recipients_path.resolve()),
            "manifest_json": str((out_dir / MANIFEST_JSON_NAME).resolve()),
            "mark_contacted_txt": str(mark_path.resolve()),
            "shared_html": str((out_dir / SHARED_HTML_NAME).resolve()) if copy_shared_html else None,
            "preview_md": str((out_dir / PREVIEW_MD_NAME).resolve()) if write_preview_md else None,
        },
    }

    (out_dir / MANIFEST_JSON_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if write_preview_md:
        preview_lines = [
            "# Manual HTML outreach batch (preview)",
            "",
            f"- **Batch:** `{bn}`",
            f"- **Subject:** {subj}",
            f"- **HTML source:** `{html_resolved}`",
            f"- **Recipients (total):** {len(recipient_out)}",
            "",
            "## First 10 recipients",
            "",
        ]
        for row in recipient_out[:10]:
            preview_lines.append(
                f"- `{row['contact_email']}` — {row.get('institution_name', '')} (`{row.get('domain', '')}`)"
            )
        (out_dir / PREVIEW_MD_NAME).write_text("\n".join(preview_lines) + "\n", encoding="utf-8")

    return manifest


__all__ = [
    "DEFAULT_SUBJECT",
    "MANIFEST_JSON_NAME",
    "MARK_CONTACTED_TXT_NAME",
    "PREVIEW_MD_NAME",
    "RECIPIENTS_CSV_NAME",
    "SCHEMA_VERSION",
    "SHARED_HTML_NAME",
    "run_manual_html_outreach_batch",
]
