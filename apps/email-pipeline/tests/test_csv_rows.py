"""Tests for origenlab_email_pipeline.csv_rows."""

from __future__ import annotations

import csv
from pathlib import Path

from origenlab_email_pipeline.csv_rows import read_dict_rows, write_dict_rows


def test_read_dict_rows_returns_headers_and_rows(tmp_path: Path) -> None:
    path = tmp_path / "in.csv"
    path.write_text("id,name\n1,Alpha\n2,Beta\n", encoding="utf-8")

    headers, rows = read_dict_rows(path)

    assert headers == ["id", "name"]
    assert rows == [{"id": "1", "name": "Alpha"}, {"id": "2", "name": "Beta"}]


def test_write_dict_rows_creates_parent_and_writes_rows(tmp_path: Path) -> None:
    out = tmp_path / "nested" / "out.csv"
    write_dict_rows(out, ["id", "name"], [{"id": "1", "name": "Alpha"}])

    assert out.is_file()
    with out.open(encoding="utf-8", newline="") as f:
        assert list(csv.DictReader(f)) == [{"id": "1", "name": "Alpha"}]


def test_write_dict_rows_extrasaction_ignore(tmp_path: Path) -> None:
    out = tmp_path / "out.csv"
    write_dict_rows(out, ["id"], [{"id": "1", "extra": "drop-me"}])

    with out.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert rows == [{"id": "1"}]


def test_read_dict_rows_utf8_sig(tmp_path: Path) -> None:
    path = tmp_path / "bom.csv"
    path.write_text("id,name\n1,Alpha\n", encoding="utf-8-sig")

    headers, rows = read_dict_rows(path, encoding="utf-8-sig")

    assert headers == ["id", "name"]
    assert rows == [{"id": "1", "name": "Alpha"}]
