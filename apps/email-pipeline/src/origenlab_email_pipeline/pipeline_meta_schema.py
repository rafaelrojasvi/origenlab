"""Pipeline run audit and key/value metadata tables (additive, shared SQLite file)."""

from __future__ import annotations

import sqlite3

PIPELINE_META_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pipeline_run (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  script_name TEXT NOT NULL,
  argv_json TEXT,
  git_describe TEXT,
  notes TEXT
);
CREATE INDEX IF NOT EXISTS idx_pipeline_run_started ON pipeline_run(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_run_script ON pipeline_run(script_name);

CREATE TABLE IF NOT EXISTS pipeline_kv (
  k TEXT PRIMARY KEY,
  v TEXT,
  updated_at TEXT NOT NULL
);
"""


def ensure_pipeline_meta_tables(conn: sqlite3.Connection) -> None:
    """Idempotent: create pipeline_run and pipeline_kv."""
    conn.executescript(PIPELINE_META_SCHEMA_SQL)
    conn.commit()
