"""CSV / JSON helpers for operational trust (no TrustCheck logic)."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def id_leads_from_rows(rows: list[dict[str, str]], col: str = "id_lead") -> list[int]:
    out: list[int] = []
    for r in rows:
        raw = (r.get(col) or "").strip()
        if not raw:
            continue
        try:
            out.append(int(raw))
        except ValueError:
            continue
    return out


def duplicate_ids(ids: list[int]) -> list[int]:
    seen: set[int] = set()
    dups: set[int] = set()
    for i in ids:
        if i in seen:
            dups.add(i)
        seen.add(i)
    return sorted(dups)


def parse_iso_utc(s: str) -> datetime | None:
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except ValueError:
        return None


def load_client_pack_summary(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def dedupe_urls(urls: list[str]) -> list[str]:
    return list(dict.fromkeys((u or "").strip() for u in urls if (u or "").strip()))
