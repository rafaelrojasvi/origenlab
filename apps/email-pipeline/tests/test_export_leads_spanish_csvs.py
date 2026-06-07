"""CLI tests for export_leads_spanish_csvs (plan-only by default)."""

from __future__ import annotations

import csv
import importlib.util
import io
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "leads" / "advanced" / "export_leads_spanish_csvs.py"

SHORTLIST_HEADERS = ["id_lead", "fit_bucket", "priority_score", "priority_reason", "org_name", "buyer_kind"]
CLIENT_HEADERS = ["id_lead", "fit_bucket", "priority_score", "org_name", "contact_name", "lead_email", "status"]
EXPORT_HEADERS = ["id_lead", "fit_bucket", "priority_score", "org_name", "source_name", "status"]


def _load_script():
    spec = importlib.util.spec_from_file_location("export_leads_spanish_csvs", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_csv(path: Path, headers: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)


def _seed_inputs(in_dir: Path, *, export_name: str = "leads_export.csv") -> dict[str, Path]:
    shortlist = in_dir / "leads_shortlist.csv"
    client = in_dir / "leads_client_review.csv"
    export = in_dir / export_name
    _write_csv(
        shortlist,
        SHORTLIST_HEADERS,
        [
            {
                "id_lead": "1",
                "fit_bucket": "high_fit",
                "priority_score": "8",
                "priority_reason": "lab",
                "org_name": "Org A",
                "buyer_kind": "hospital",
            }
        ],
    )
    _write_csv(
        client,
        CLIENT_HEADERS,
        [
            {
                "id_lead": "2",
                "fit_bucket": "medium_fit",
                "priority_score": "6",
                "org_name": "Org B",
                "contact_name": "Ana",
                "lead_email": "a@b.cl",
                "status": "nuevo",
            }
        ],
    )
    _write_csv(
        export,
        EXPORT_HEADERS,
        [
            {
                "id_lead": "3",
                "fit_bucket": "high_fit",
                "priority_score": "9",
                "org_name": "Org C",
                "source_name": "chilecompra",
                "status": "nuevo",
            }
        ],
    )
    return {"shortlist": shortlist, "client": client, "export": export}


def _run_main(mod, argv: list[str]) -> tuple[int | None, str, str]:
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    code: int | None = 0
    try:
        with redirect_stdout(out_buf), redirect_stderr(err_buf):
            code = mod.main(argv)
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    return code, out_buf.getvalue(), err_buf.getvalue()


def test_default_run_is_plan_only(tmp_path: Path) -> None:
    mod = _load_script()
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    paths = _seed_inputs(in_dir)
    code, stdout, _stderr = _run_main(
        mod,
        [
            "--shortlist",
            str(paths["shortlist"]),
            "--client-review",
            str(paths["client"]),
            "--export",
            str(paths["export"]),
            "--out-dir",
            str(out_dir),
        ],
    )
    assert code == 0
    assert "Plan only: pass --write-outputs to write Spanish CSVs." in stdout
    assert not (out_dir / "leads_shortlist_es.csv").exists()
    assert not (out_dir / "leads_client_review_es.csv").exists()
    assert not (out_dir / "leads_export_es.csv").exists()
    assert "leads_shortlist_es.csv rows: 1" in stdout


def test_dry_run_behaves_like_default(tmp_path: Path) -> None:
    mod = _load_script()
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    paths = _seed_inputs(in_dir)
    code, stdout, _stderr = _run_main(
        mod,
        [
            "--dry-run",
            "--shortlist",
            str(paths["shortlist"]),
            "--client-review",
            str(paths["client"]),
            "--export",
            str(paths["export"]),
            "--out-dir",
            str(out_dir),
        ],
    )
    assert code == 0
    assert "Plan only" in stdout
    assert not (out_dir / "leads_shortlist_es.csv").exists()


def test_write_outputs_writes_all_three_csvs(tmp_path: Path) -> None:
    mod = _load_script()
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    paths = _seed_inputs(in_dir)
    code, stdout, _stderr = _run_main(
        mod,
        [
            "--write-outputs",
            "--shortlist",
            str(paths["shortlist"]),
            "--client-review",
            str(paths["client"]),
            "--export",
            str(paths["export"]),
            "--out-dir",
            str(out_dir),
        ],
    )
    assert code == 0
    assert (out_dir / "leads_shortlist_es.csv").is_file()
    assert (out_dir / "leads_client_review_es.csv").is_file()
    assert (out_dir / "leads_export_es.csv").is_file()
    assert "Wrote Spanish CSVs to" in stdout


def test_write_outputs_and_dry_run_rejected(tmp_path: Path) -> None:
    mod = _load_script()
    in_dir = tmp_path / "in"
    paths = _seed_inputs(in_dir)
    code, _stdout, stderr = _run_main(
        mod,
        [
            "--write-outputs",
            "--dry-run",
            "--shortlist",
            str(paths["shortlist"]),
            "--client-review",
            str(paths["client"]),
            "--export",
            str(paths["export"]),
        ],
    )
    assert code == 2
    assert "cannot be used together" in stderr


def test_export_remains_input_path_in_write_mode(tmp_path: Path) -> None:
    mod = _load_script()
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    paths = _seed_inputs(in_dir, export_name="custom_full_export_input.csv")
    code, _stdout, _stderr = _run_main(
        mod,
        [
            "--write-outputs",
            "--shortlist",
            str(paths["shortlist"]),
            "--client-review",
            str(paths["client"]),
            "--export",
            str(paths["export"]),
            "--out-dir",
            str(out_dir),
        ],
    )
    assert code == 0
    export_es = out_dir / "leads_export_es.csv"
    assert export_es.is_file()
    with export_es.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["id_lead"] == "3"
    assert rows[0]["ajuste"] == "alto_ajuste"


def test_map_fit_bucket_high_fit_to_alto_ajuste() -> None:
    mod = _load_script()
    row = mod._to_spanish_row({"id_lead": "1", "fit_bucket": "high_fit"}, mode="shortlist")
    assert row["ajuste"] == "alto_ajuste"
