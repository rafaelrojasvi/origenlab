from __future__ import annotations

from pathlib import Path

from origenlab_email_pipeline.merge_marketing_contact_csvs import (
    merge_contact_csvs_dedupe_by_email,
    normalize_header_row,
)


def test_normalize_header_row_strips_padding() -> None:
    row = normalize_header_row(
        {
            "  institution_name  ": "  Org A  ",
            " contact_email ": "a@x.cl",
        }
    )
    assert row["institution_name"] == "Org A"
    assert row["contact_email"] == "a@x.cl"


def test_merge_dedupes_by_email_first_row_wins(tmp_path: Path) -> None:
    f1 = tmp_path / "a.csv"
    f1.write_text(
        "institution_name,region,city,type,contact_email,contact_label,source_url,confidence\n"
        "One,RM,Santiago,hospital,overlap@x.cl,lab,https://a,high\n"
        "Two,RM,Santiago,hospital,only@x.cl,OIRS,https://b,high\n",
        encoding="utf-8",
    )
    f2 = tmp_path / "b.csv"
    f2.write_text(
        "institution_name,region,city,type,contact_email,contact_label,source_url,confidence\n"
        "Three,VI,Rancagua,hospital,overlap@x.cl,compras,https://c,high\n",
        encoding="utf-8",
    )
    rows = merge_contact_csvs_dedupe_by_email((f1, f2))
    emails = {r["contact_email"] for r in rows}
    assert emails == {"overlap@x.cl", "only@x.cl"}
    overlap = next(r for r in rows if r["contact_email"] == "overlap@x.cl")
    assert overlap["institution_name"] == "One"
    assert "a.csv" in overlap["source_files"] and "b.csv" in overlap["source_files"]
