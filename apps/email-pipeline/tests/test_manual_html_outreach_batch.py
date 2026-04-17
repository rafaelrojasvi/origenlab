"""Tests for manual HTML outreach batch packaging (no send, no DB)."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "leads" / "build_manual_html_outreach_batch.py"

from origenlab_email_pipeline.manual_html_outreach_batch import (
    MANIFEST_JSON_NAME,
    MARK_CONTACTED_TXT_NAME,
    PREVIEW_MD_NAME,
    RECIPIENTS_CSV_NAME,
    SHARED_HTML_NAME,
    run_manual_html_outreach_batch,
)


def test_run_manual_html_outreach_batch_happy_path(tmp_path: Path) -> None:
    inp = tmp_path / "in.csv"
    inp.write_text(
        "contact_email,institution_name,domain\n"
        "a@acme.cl,Acme,acme.cl\n"
        "b@beta.org,Beta,beta.org\n",
        encoding="utf-8",
    )
    html = tmp_path / "body.html"
    html.write_text("<html><body>Hi</body></html>", encoding="utf-8")
    out = tmp_path / "out"

    manifest = run_manual_html_outreach_batch(
        input_csv=inp,
        html_path=html,
        subject="Test subject",
        out_dir=out,
        batch_name="batch_x",
    )

    assert manifest["batch_name"] == "batch_x"
    assert manifest["subject"] == "Test subject"
    assert manifest["counts"]["recipients_written"] == 2
    assert manifest["counts"]["recipients_after_dedupe"] == 2
    assert "input_rows_with_valid_email" in manifest["counts"]

    rec_path = out / RECIPIENTS_CSV_NAME
    with rec_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2
    assert rows[0]["contact_email"] == "a@acme.cl"
    assert rows[0]["subject"] == "Test subject"
    assert rows[0]["html_source_path"] == str(html.resolve())
    assert rows[0]["batch_name"] == "batch_x"

    mark = (out / MARK_CONTACTED_TXT_NAME).read_text(encoding="utf-8").strip().splitlines()
    assert mark == ["a@acme.cl", "b@beta.org"]

    assert (out / SHARED_HTML_NAME).read_text(encoding="utf-8") == html.read_text(encoding="utf-8")
    assert (out / MANIFEST_JSON_NAME).is_file()
    preview = (out / PREVIEW_MD_NAME).read_text(encoding="utf-8")
    assert "a@acme.cl" in preview
    assert "Test subject" in preview


def test_dedupe_case_insensitive_preserves_first_row(tmp_path: Path) -> None:
    inp = tmp_path / "in.csv"
    inp.write_text(
        "contact_email,institution_name,domain\n"
        "A@acme.cl,First,acme.cl\n"
        "a@acme.cl,Second,acme.cl\n",
        encoding="utf-8",
    )
    html = tmp_path / "b.html"
    html.write_text("<html/>", encoding="utf-8")
    out = tmp_path / "out2"
    run_manual_html_outreach_batch(
        input_csv=inp,
        html_path=html,
        subject="S",
        out_dir=out,
        batch_name="b",
        copy_shared_html=False,
        write_preview_md=False,
    )
    with (out / RECIPIENTS_CSV_NAME).open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["contact_email"] == "a@acme.cl"
    assert rows[0]["institution_name"] == "First"


def test_limit_truncates(tmp_path: Path) -> None:
    inp = tmp_path / "in.csv"
    inp.write_text(
        "contact_email\nx@1.cl\ny@2.cl\nz@3.cl\n",
        encoding="utf-8",
    )
    html = tmp_path / "h.html"
    html.write_text("<html/>", encoding="utf-8")
    out = tmp_path / "out3"
    run_manual_html_outreach_batch(
        input_csv=inp,
        html_path=html,
        subject="S",
        out_dir=out,
        limit=2,
        batch_name="lim",
        copy_shared_html=False,
        write_preview_md=False,
    )
    manifest = json.loads((out / MANIFEST_JSON_NAME).read_text(encoding="utf-8"))
    assert manifest["counts"]["recipients_after_dedupe"] == 3
    assert manifest["counts"]["recipients_written"] == 2
    assert manifest["counts"]["limit_applied"] == 2


def test_missing_html_raises(tmp_path: Path) -> None:
    inp = tmp_path / "in.csv"
    inp.write_text("contact_email\na@x.cl\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="HTML file not found"):
        run_manual_html_outreach_batch(
            input_csv=inp,
            html_path=tmp_path / "nope.html",
            subject="S",
            out_dir=tmp_path / "o",
        )


def test_empty_recipients_raises(tmp_path: Path) -> None:
    inp = tmp_path / "in.csv"
    inp.write_text("contact_email,foo\n,\n", encoding="utf-8")
    html = tmp_path / "h.html"
    html.write_text("<html/>", encoding="utf-8")
    with pytest.raises(ValueError, match="No valid recipients"):
        run_manual_html_outreach_batch(
            input_csv=inp,
            html_path=html,
            subject="S",
            out_dir=tmp_path / "empty_out",
        )


def test_manifest_expected_fields(tmp_path: Path) -> None:
    inp = tmp_path / "in.csv"
    inp.write_text("contact_email\nsolo@one.cl\n", encoding="utf-8")
    html = tmp_path / "h.html"
    html.write_text("<html/>", encoding="utf-8")
    out = tmp_path / "out4"
    run_manual_html_outreach_batch(
        input_csv=inp,
        html_path=html,
        subject="Subj",
        out_dir=out,
        batch_name="bn",
        copy_shared_html=False,
        write_preview_md=False,
    )
    m = json.loads((out / MANIFEST_JSON_NAME).read_text(encoding="utf-8"))
    for key in (
        "schema_version",
        "batch_name",
        "created_at_utc",
        "input_csv",
        "html_source_path",
        "subject",
        "counts",
        "artifacts",
    ):
        assert key in m
    assert m["subject"] == "Subj"
    assert m["counts"]["recipients_written"] == 1


@pytest.mark.skipif(not SCRIPT.is_file(), reason="CLI script missing")
def test_cli_exits_2_on_missing_html(tmp_path: Path) -> None:
    inp = tmp_path / "in.csv"
    inp.write_text("contact_email\na@b.cl\n", encoding="utf-8")
    out = tmp_path / "o"
    r = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--input",
            str(inp),
            "--html",
            str(tmp_path / "missing.html"),
            "--out-dir",
            str(out),
        ],
        cwd=str(SCRIPT.resolve().parents[2]),
        capture_output=True,
        text=True,
    )
    assert r.returncode == 2
    assert "HTML file not found" in (r.stderr or "")
