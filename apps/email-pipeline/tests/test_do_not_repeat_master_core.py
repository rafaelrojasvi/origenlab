from __future__ import annotations

from collections import Counter
from pathlib import Path

from origenlab_email_pipeline.core.outbound import do_not_repeat_master as m


def test_norm_email_from_cell_extracts_first() -> None:
    assert m.norm_email_from_cell("Foo <a@B.co>") == "a@b.co"
    assert m.norm_email_from_cell("  ") is None


def test_parse_send_manifest_and_duplicate_emails_increment_merge() -> None:
    payload = {
        "recipients": ["A@X.CL", "a@x.cl"],
        "contact_email": "other@y.cl",
    }
    out, root = m.parse_send_manifest_payload(payload)
    assert "a@x.cl" in out
    assert "other@y.cl" in out
    assert isinstance(root, dict)
    agg: dict[str, m.DoNotRepeatAgg] = {}
    m.touch_source_with_paths(agg, out, tag="send_manifest:foo", rel="reports/x.json")
    assert "a@x.cl" in agg and "other@y.cl" in agg
    n_g, n_o, n_s, n_mkt = m.count_source_buckets(agg)
    assert n_mkt == 2


def test_merge_sources_same_email_joins_kinds() -> None:
    agg: dict[str, m.DoNotRepeatAgg] = {}
    m.apply_gmail_sent_bounds(agg, {"u@d.co": ("2026-01-01", "2026-01-02")})
    m.apply_outreach_state_dates(agg, {"u@d.co": ("2025-12-01", "2025-12-01")})
    m.apply_suppression_set(agg, ("x@d.co",))
    row = next(r for r in m.build_master_csv_rows(agg) if r["email_norm"] == "u@d.co")
    kinds = set(row["source_kinds"].split(";"))
    assert "gmail_sent" in kinds and "outreach_state" in kinds
    assert int(row["source_count"]) == 2
    n_g, n_o, n_s, n_m = m.count_source_buckets(agg)
    assert n_g == 1 and n_o == 1 and n_s == 1 and n_m == 0


def test_build_master_rows_sorted_by_email() -> None:
    agg: dict[str, m.DoNotRepeatAgg] = {}
    m.apply_suppression_set(agg, ("z@x.cl", "a@x.cl", "m@x.cl"))
    keys = [r["email_norm"] for r in m.build_master_csv_rows(agg)]
    assert keys == ["a@x.cl", "m@x.cl", "z@x.cl"]


def test_marketing_file_kind_in_bucket_count() -> None:
    a = m.DoNotRepeatAgg()
    a.touch("marketing_csv:deepsearch", path="reports/a.csv")
    agg = {"e@e.co": a}
    n_g, n_o, n_s, n_m = m.count_source_buckets(agg)
    assert n_g == n_o == n_s == 0 and n_m == 1


def test_top_file_paths_respects_counter_order() -> None:
    c: Counter[str] = Counter()
    c["a"] = 3
    c["b"] = 5
    c["c"] = 1
    top = m.top_file_paths_by_row_count(c, limit=2)
    assert top == ["b", "a"]


def test_build_summary_keys_stable() -> None:
    agg: dict[str, m.DoNotRepeatAgg] = {}
    m.apply_suppression_set(agg, ("one@test.co",))
    c: Counter[str] = Counter()
    c["f.csv"] = 1
    csv_p = Path("/tmp/do_not_repeat_master.csv")
    txt_p = Path("/tmp/do_not_repeat_master.txt")
    db = Path("/tmp/t.sqlite")
    s = m.build_do_not_repeat_summary(
        generated_at="2026-01-01T00:00:00Z",
        db_path=db,
        gmail_user="u@x",
        sent_folders=("[Gmail]/Sent",),
        reports_out_dir=Path("/tmp/active"),
        agg=agg,
        file_email_counts=c,
        csv_path=csv_p,
        txt_path=txt_p,
    )
    assert s["schema_version"] == "1"
    assert s["unique_emails"] == 1
    assert set(s["outputs"].keys()) == {"csv", "txt"}
    assert s["from_email_suppression"] == 1


def test_discover_dedupes_by_resolved_path(tmp_path: Path) -> None:
    root = tmp_path / "active"
    cur = root / "current"
    cur.mkdir(parents=True)
    man = cur / "send_manifest.json"
    man.write_text("{}", encoding="utf-8")
    (root / "deepsearch_1.csv").write_text("contact_email\ne@e.co\n", encoding="utf-8")
    found = m.discover_active_files(root)
    paths = {f[2].resolve() for f in found}
    assert man.resolve() in paths


def test_scan_csv_emails_reads_contact_column(tmp_path: Path) -> None:
    p = tmp_path / "x.csv"
    p.write_text("email,other\nA@B.CO,x\n", encoding="utf-8")
    assert m.scan_csv_emails(p) == {"a@b.co"}


def test_format_txt_list_trailing_newline() -> None:
    agg: dict[str, m.DoNotRepeatAgg] = {}
    m.apply_suppression_set(agg, ("a@a.co", "b@b.co"))
    t = m.format_email_list_txt(agg)
    assert t.endswith("\n")
    assert t.splitlines() == ["a@a.co", "b@b.co"]


def test_rel_path_for_docs() -> None:
    root = Path("/tmp/ws")
    sub = root / "reports" / "a.csv"
    s = m.rel_path_for_docs(sub, Path("/tmp/ws"))
    assert "reports" in s and s.endswith("a.csv")


def test_csv_row_notes_path_cap() -> None:
    agg: dict[str, m.DoNotRepeatAgg] = {}
    m.touch_source_with_paths(agg, ("a@a.co",), tag="m:k", rel="p8")
    m.touch_source_with_paths(agg, ("a@a.co",), tag="m:k", rel="p7")
    m.touch_source_with_paths(agg, ("a@a.co",), tag="m:k", rel="p6")
    m.touch_source_with_paths(agg, ("a@a.co",), tag="m:k", rel="p5")
    m.touch_source_with_paths(agg, ("a@a.co",), tag="m:k", rel="p4")
    m.touch_source_with_paths(agg, ("a@a.co",), tag="m:k", rel="p3")
    m.touch_source_with_paths(agg, ("a@a.co",), tag="m:k", rel="p2")
    m.touch_source_with_paths(agg, ("a@a.co",), tag="m:k", rel="p1")
    m.touch_source_with_paths(agg, ("a@a.co",), tag="m:k", rel="p0")
    m.touch_source_with_paths(agg, ("a@a.co",), tag="m:k", rel="p9")
    # first sort order by path; first 8 only
    r = m.build_master_csv_rows(agg)[0]
    listed = r["notes"].removeprefix("paths=")
    assert len(listed.split(",")) == 8


def test_send_manifest_file_email_count_unique() -> None:
    """When ingesting a manifest, file counts use len(set(emails)) like the script."""
    payload = ["a@a.co", "a@a.co", "b@b.co"]
    emails, _ = m.parse_send_manifest_payload(payload)
    c: Counter[str] = Counter()
    c["f.json"] = len(set(emails))
    assert c["f.json"] == 2  # a and b, not 3
    agg: dict[str, m.DoNotRepeatAgg] = {}
    m.touch_source_with_paths(agg, emails, tag="send_manifest:x", rel="f.json")
    assert m.count_source_buckets(agg)[3] == 2  # n_mkt: a@a.co and b@b.co
