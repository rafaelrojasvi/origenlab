"""Merge marketing contact CSVs into one deduplicated list (by email) for outreach seeds."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from pathlib import Path

from origenlab_email_pipeline.business_mart import emails_in

_OUTPUT_FIELDS: tuple[str, ...] = (
    "institution_name",
    "region",
    "city",
    "type",
    "contact_email",
    "contact_label",
    "source_url",
    "confidence",
    "source_files",
)


def normalize_header_row(row: dict[str, str]) -> dict[str, str]:
    """Strip CSV header keys and values (handles space-padded legacy exports)."""
    out: dict[str, str] = {}
    for k, v in row.items():
        key = (k or "").strip().lower()
        if not key:
            continue
        out[key] = (v or "").strip()
    return out


def _email_from_row(norm: dict[str, str]) -> str | None:
    raw = norm.get("contact_email") or norm.get("email") or norm.get("to") or ""
    found = emails_in(raw)
    if not found:
        return None
    return found[0]


def iter_contact_rows_from_csv(path: Path) -> Iterable[dict[str, str]]:
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(text.splitlines())
    if not reader.fieldnames:
        return
    label = path.name
    for raw in reader:
        norm = normalize_header_row({str(k): str(v or "") for k, v in raw.items()})
        em = _email_from_row(norm)
        if not em:
            continue
        yield {
            "institution_name": norm.get("institution_name", ""),
            "region": norm.get("region", ""),
            "city": norm.get("city", ""),
            "type": norm.get("type", ""),
            "contact_email": em,
            "contact_label": norm.get("contact_label", ""),
            "source_url": norm.get("source_url", ""),
            "confidence": norm.get("confidence", ""),
            "source_files": label,
        }


def merge_contact_csvs_dedupe_by_email(paths: Iterable[Path]) -> list[dict[str, str]]:
    """Return rows unique by lowercased contact_email.

    First row wins for institution/metadata. ``source_files`` lists every file basename
    that contained that email, ``;``-separated and sorted.
    """
    by_email: dict[str, dict[str, str]] = {}
    order: list[str] = []

    for path in paths:
        path = path.expanduser().resolve()
        if not path.is_file():
            continue
        for row in iter_contact_rows_from_csv(path):
            em = row["contact_email"].strip().lower()
            if not em:
                continue
            label = row["source_files"]
            if em not in by_email:
                by_email[em] = row
                order.append(em)
            else:
                existing = by_email[em]
                files = {s.strip() for s in existing["source_files"].split(";") if s.strip()}
                files.add(label)
                existing["source_files"] = ";".join(sorted(files))

    return [by_email[e] for e in order]


def write_merged_contacts_csv(rows: list[dict[str, str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(_OUTPUT_FIELDS))
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in _OUTPUT_FIELDS})


def default_active_marketing_csv_paths(*, reports_active: Path) -> tuple[Path, ...]:
    """Canonical defaults aligned with active/archive/reference workspace policy."""
    reports_out = reports_active.parent
    archive = reports_out / "archive"
    reference = reports_out / "reference"

    out: list[Path] = []

    # Always include contacted-all when present (primary anti-repeat auxiliary seed).
    out.append(reports_active / "outreach_contacted_all.csv")

    # Include conservative reference contact exports only.
    for p in sorted(reference.glob("*official*contacts*.csv")):
        out.append(p)
    for p in sorted(reference.glob("*marketing*contacts*.csv")):
        out.append(p)

    # Historical research contact CSVs now live under archive/research.
    research = archive / "research"
    if research.exists():
        for pat in (
            "chile_institutional*.csv",
            "reviewed_marketing_contacts*.csv",
            "deepsearch_marketing_send_batch_*/deepsearch_contacts_all.csv",
            "supplement_research_send_batch_*/send_ready.csv",
        ):
            for p in sorted(research.glob(pat)):
                out.append(p)

    # Historical campaign contact exports under archive/campaigns.
    campaigns = archive / "campaigns"
    if campaigns.exists():
        for pat in (
            "next_marketing*.csv",
            "*/send_ready.csv",
            "*/archive_manual_send_candidates*.csv",
        ):
            for p in sorted(campaigns.glob(pat)):
                out.append(p)

    # De-duplicate while preserving order.
    seen: set[str] = set()
    ordered: list[Path] = []
    for p in out:
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        ordered.append(p)
    return tuple(ordered)
