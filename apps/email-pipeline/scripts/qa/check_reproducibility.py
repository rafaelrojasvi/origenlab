#!/usr/bin/env python3
"""Read-only environment and reproducibility report (no DB writes, no network, no Gmail calls).

Prints Python version, package import status, presence of key docs, .env (yes/no only),
SQLite path resolution and existence, optional read-only table checks, Gmail env var presence
(values never printed), and a single-line verdict.

Exit code 0 unless argparse errors. Missing private runtime inputs is not a hard failure.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_SRC = REPO / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

KEY_DOCS = (
    "docs/SCRIPT_MAP.md",
    "docs/REPRODUCIBILITY.md",
    "docs/CRUD_SAFETY.md",
)

KEY_TABLES = (
    "emails",
    "contact_master",
    "organization_master",
    "opportunity_signals",
    "lead_master",
    "outreach_contact_state",
    "contact_email_suppression",
    "supplier_master",
)

GMAIL_ENV = (
    "ORIGENLAB_GMAIL_OAUTH_CLIENT_JSON",
    "ORIGENLAB_GMAIL_TOKEN_JSON",
    "ORIGENLAB_GMAIL_WORKSPACE_USER",
)


def _line(label: str, value: str) -> None:
    print(f"{label}: {value}")


def _env_set(key: str) -> str:
    v = os.environ.get(key)
    if v is None or (isinstance(v, str) and not v.strip()):
        return "unset"
    return "set (value not shown)"


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


def build_parser() -> argparse.ArgumentParser:
    return argparse.ArgumentParser(description=__doc__)


def main() -> int:
    build_parser().parse_args()

    _line("python", sys.version.split()[0])
    _line("platform", sys.platform)

    try:
        import origenlab_email_pipeline  # noqa: PLC0415

        _line("import origenlab_email_pipeline", f"ok ({getattr(origenlab_email_pipeline, '__file__', '?')})")
    except Exception as exc:  # noqa: BLE001
        _line("import origenlab_email_pipeline", f"FAILED: {exc!r}")
        _line("verdict", "missing_private_runtime_inputs")
        return 0

    for rel in KEY_DOCS:
        p = REPO / rel
        _line(f"doc {rel}", "yes" if p.is_file() else "no")

    env_path = REPO / ".env"
    _line("apps/email-pipeline/.env file", "yes" if env_path.is_file() else "no")

    # Load settings only after we can import the package
    from origenlab_email_pipeline.config import load_settings  # noqa: PLC0415

    settings = load_settings()
    sqlite_path = settings.resolved_sqlite_path()
    _line("ORIGENLAB_SQLITE_PATH env", _env_set("ORIGENLAB_SQLITE_PATH"))
    _line("resolved SQLite path", str(sqlite_path))
    _line("SQLite file exists", "yes" if sqlite_path.is_file() else "no")

    missing_tables: list[str] = []
    sqlite_open_failed = False
    if sqlite_path.is_file():
        try:
            uri = f"file:{sqlite_path.resolve()}?mode=ro"
            conn = sqlite3.connect(uri, uri=True)
        except sqlite3.Error as exc:
            sqlite_open_failed = True
            _line("sqlite read-only open", f"failed: {exc!r}")
            for t in KEY_TABLES:
                _line(f"table {t}", "skipped (open failed)")
        else:
            try:
                for t in KEY_TABLES:
                    ok = _table_exists(conn, t)
                    _line(f"table {t}", "yes" if ok else "no")
                    if not ok:
                        missing_tables.append(t)
            finally:
                conn.close()
    else:
        for t in KEY_TABLES:
            _line(f"table {t}", "skipped (no db file)")

    for k in GMAIL_ENV:
        _line(f"env {k}", _env_set(k))

    # Verdict
    if not sqlite_path.is_file():
        verdict = "code_only_ready"
    elif sqlite_open_failed or missing_tables:
        verdict = "missing_private_runtime_inputs"
    else:
        verdict = "operational_ready"

    _line("verdict", verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
