#!/usr/bin/env python3
"""Print SQLite schema, row counts, and short samples (any DB path)."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_ROOT / "src"))

from origenlab_email_pipeline.config import load_settings


def trunc(s: str | None, n: int = 120) -> str:
    if s is None:
        return ""
    s = s.replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 3] + "..."


def main() -> None:
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else load_settings().resolved_sqlite_path()
    print("=== inspect_sqlite.py ===")
    print("db_path:", db_path.resolve())
    if not db_path.is_file():
        print("File missing — build it first:")
        print("  1) bash scripts/ingest/01_convert_pst.sh   # PST → mbox (long for ~31GB PST)")
        print("  2) uv run python scripts/ingest/02_mbox_to_sqlite.py")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            ).fetchall()
        ]
        print("tables:", tables)
        for t in tables:
            if t.startswith("sqlite_"):
                continue
            n = conn.execute(f"SELECT COUNT(*) AS c FROM {quote_ident(t)}").fetchone()[0]
            print(f"\n--- {t}  rows={n} ---")
            cols = conn.execute(f"PRAGMA table_info({quote_ident(t)})").fetchall()
            for c in cols:
                print(f"  {c[1]}  {c[2]}")
            rows = conn.execute(f"SELECT * FROM {quote_ident(t)} LIMIT 3").fetchall()
            for i, row in enumerate(rows):
                d = dict(row)
                if "body" in d:
                    d["body"] = trunc(d.get("body"), 200)
                if "body_html" in d:
                    d["body_html"] = trunc(d.get("body_html"), 120)
                print(f"  sample[{i}]:", d)
    finally:
        conn.close()


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


if __name__ == "__main__":
    main()
