from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "validate_contacted_csv_coverage.py"


def _run_cli(db: Path, reports_active: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO / "src")}
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--db",
            str(db),
            "--reports-active",
            str(reports_active),
            "--gmail-user",
            "contacto@origenlab.cl",
            "--sent-folder",
            "[Gmail]/Enviados",
            "--sent-folder",
            "[Gmail]/Sent Mail",
            *extra,
        ],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _seed_db(db: Path) -> None:
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE emails (
          recipients TEXT,
          source_file TEXT,
          folder TEXT,
          date_iso TEXT,
          date_raw TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO emails VALUES (?,?,?,?,?)",
        [
            (
                "To: A@X.CL, b@y.cl",
                "gmail:contacto@origenlab.cl/m1",
                "[Gmail]/Enviados",
                "2026-04-01T10:00:00Z",
                "",
            ),
            (
                "to: c@z.cl",
                "gmail:contacto@origenlab.cl/m2",
                "[Gmail]/Sent Mail",
                "2026-04-02T11:00:00Z",
                "",
            ),
        ],
    )
    conn.commit()
    conn.close()


def _seed_csvs(base: Path) -> None:
    current = base / "current"
    current.mkdir(parents=True, exist_ok=True)
    (current / "do_not_repeat_master.csv").write_text(
        "email_norm,source_kinds\n"
        "a@x.cl,gmail_sent\n"
        "b@y.cl,gmail_sent\n"
        "extra@other.cl,manual\n",
        encoding="utf-8",
    )
    (base / "outreach_contacted_all.csv").write_text(
        "contact_email,source\n"
        "a@x.cl,sent\n"
        "b@y.cl,sent\n",
        encoding="utf-8",
    )
    (base / "all_known_marketing_contacts_dedup.csv").write_text(
        "contact_email,institution_name\n"
        "a@x.cl,Inst A\n"
        "b@y.cl,Inst B\n"
        "b@y.cl,Inst B duplicate\n",
        encoding="utf-8",
    )


def test_reports_coverage_and_duplicates(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    reports_active = tmp_path / "active"
    _seed_db(db)
    _seed_csvs(reports_active)

    result = _run_cli(db, reports_active)
    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(result.stdout)

    assert payload["sent_unique_emails"] == 3
    assert payload["sent_vs_csv"]["do_not_repeat_master"]["sent_missing_from_csv_count"] == 1
    assert payload["sent_vs_csv"]["outreach_contacted_all"]["sent_missing_from_csv_count"] == 1
    assert (
        payload["csv_stats"]["all_known_marketing_contacts_dedup"]["duplicate_unique_emails"]
        == 1
    )
    assert payload["strict_failures"] is True


def test_strict_mode_exits_nonzero_on_missing_sent(tmp_path: Path) -> None:
    db = tmp_path / "t.sqlite"
    reports_active = tmp_path / "active"
    _seed_db(db)
    _seed_csvs(reports_active)

    result = _run_cli(db, reports_active, "--strict")
    assert result.returncode == 3, result.stderr + result.stdout
