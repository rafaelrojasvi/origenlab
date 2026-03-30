"""Helpers for ingesting raw lead records into external_leads_raw."""

from __future__ import annotations

import json
import sqlite3

from origenlab_email_pipeline.timeutil import now_iso

SOURCE_CHILECOMPRA = "chilecompra"
SOURCE_INN_LABS = "inn_labs"
SOURCE_CORFO_CENTERS = "corfo_centers"

SOURCE_NAMES = (SOURCE_CHILECOMPRA, SOURCE_INN_LABS, SOURCE_CORFO_CENTERS)


def insert_raw(
    conn: sqlite3.Connection,
    *,
    source_name: str,
    source_record_id: str,
    raw_json: dict | str | None = None,
    source_url: str | None = None,
) -> None:
    """Insert or replace one raw record. Uses UNIQUE(source_name, source_record_id)."""
    fetched_at = now_iso()
    if isinstance(raw_json, dict):
        raw_json_str = json.dumps(raw_json, ensure_ascii=False)
    else:
        raw_json_str = raw_json
    conn.execute(
        """
        INSERT INTO external_leads_raw (source_name, source_record_id, fetched_at, raw_json, source_url)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(source_name, source_record_id) DO UPDATE SET
          fetched_at = excluded.fetched_at,
          raw_json = excluded.raw_json,
          source_url = excluded.source_url
        """,
        (source_name, source_record_id, fetched_at, raw_json_str, source_url or ""),
    )
