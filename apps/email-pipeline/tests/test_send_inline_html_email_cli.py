from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "qa" / "send_inline_html_email_via_gmail_api.py"


def _write_html(path: Path) -> None:
    path.write_text(
        "<html><body><h1>Test</h1><p>Hello</p></body></html>",
        encoding="utf-8",
    )


def test_send_inline_html_cli_dry_run_with_csv_and_test_recipient(tmp_path: Path) -> None:
    html = tmp_path / "email.html"
    _write_html(html)
    recipients = tmp_path / "recipients.csv"
    recipients.write_text(
        "contact_email\nalice@example.com\nbob@example.com\nalice@example.com\n",
        encoding="utf-8",
    )
    run = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--to-file",
            str(recipients),
            "--test-recipient",
            "qa@origenlab.cl",
            "--html",
            str(html),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr + run.stdout
    assert "Completed validation for 2 recipient(s)." in run.stdout
    assert "real_to=alice@example.com effective_to=qa@origenlab.cl" in run.stdout
    assert "real_to=bob@example.com effective_to=qa@origenlab.cl" in run.stdout


def test_send_inline_html_cli_rejects_invalid_email(tmp_path: Path) -> None:
    html = tmp_path / "email.html"
    _write_html(html)
    run = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--to",
            "bad-email",
            "--html",
            str(html),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode != 0
    assert "Invalid recipient email" in (run.stderr + run.stdout)


def test_send_inline_html_cli_single_message_dry_run_with_cc(tmp_path: Path) -> None:
    html = tmp_path / "email.html"
    _write_html(html)
    run = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--single-message",
            "--to",
            "a@example.com",
            "--to",
            "b@example.com",
            "--cc",
            "cc@example.com",
            "--html",
            str(html),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode == 0, run.stderr + run.stdout
    assert "single_message" in run.stdout
    assert "a@example.com,b@example.com" in run.stdout.replace(" ", "")
    assert "cc_requested=cc@example.com" in run.stdout.replace(" ", "")


def test_send_inline_html_cli_cc_requires_single_message(tmp_path: Path) -> None:
    html = tmp_path / "email.html"
    _write_html(html)
    run = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--to",
            "a@example.com",
            "--cc",
            "cc@example.com",
            "--html",
            str(html),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode != 0
    assert "requires --single-message" in (run.stderr + run.stdout)


def test_send_inline_html_cli_single_message_counts_cc_for_max_recipients(tmp_path: Path) -> None:
    html = tmp_path / "email.html"
    _write_html(html)
    run = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--single-message",
            "--to",
            "a@example.com",
            "--to",
            "b@example.com",
            "--cc",
            "cc@example.com",
            "--max-recipients",
            "2",
            "--html",
            str(html),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode != 0
    assert "exceeds --max-recipients=2" in (run.stderr + run.stdout)


def test_send_inline_html_cli_respects_max_recipients(tmp_path: Path) -> None:
    html = tmp_path / "email.html"
    _write_html(html)
    run = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dry-run",
            "--to",
            "a@example.com",
            "--to",
            "b@example.com",
            "--max-recipients",
            "1",
            "--html",
            str(html),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert run.returncode != 0
    assert "exceeds --max-recipients=1" in (run.stderr + run.stdout)
