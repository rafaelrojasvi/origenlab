"""Record pipeline runs and pipeline_kv entries for reproducibility."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys

from origenlab_email_pipeline.pipeline_meta_schema import ensure_pipeline_meta_tables
from origenlab_email_pipeline.timeutil import now_iso


def get_git_describe(fallback: str = "") -> str:
    try:
        out = subprocess.run(
            ["git", "describe", "--always", "--dirty"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=None,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return fallback


def argv_json_default() -> str:
    try:
        return json.dumps(sys.argv, ensure_ascii=False)
    except (TypeError, ValueError):
        return "[]"


def start_run(
    conn: sqlite3.Connection,
    *,
    script_name: str,
    argv_json: str | None = None,
    git_describe: str | None = None,
    notes: str | None = None,
) -> int:
    ensure_pipeline_meta_tables(conn)
    ts = now_iso()
    gd = git_describe if git_describe is not None else get_git_describe()
    aj = argv_json if argv_json is not None else argv_json_default()
    cur = conn.execute(
        """
        INSERT INTO pipeline_run (started_at, finished_at, script_name, argv_json, git_describe, notes)
        VALUES (?, NULL, ?, ?, ?, ?)
        """,
        (ts, script_name, aj, gd, notes or ""),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int) -> None:
    conn.execute(
        "UPDATE pipeline_run SET finished_at = ? WHERE id = ?",
        (now_iso(), run_id),
    )
    conn.commit()


def set_kv(conn: sqlite3.Connection, key: str, value: str) -> None:
    ensure_pipeline_meta_tables(conn)
    ts = now_iso()
    conn.execute(
        """
        INSERT INTO pipeline_kv (k, v, updated_at) VALUES (?, ?, ?)
        ON CONFLICT(k) DO UPDATE SET v = excluded.v, updated_at = excluded.updated_at
        """,
        (key, value, ts),
    )
    conn.commit()


def get_kv(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT v FROM pipeline_kv WHERE k = ?", (key,)).fetchone()
    return row[0] if row else None
