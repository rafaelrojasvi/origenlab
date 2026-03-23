"""Tests for scripts/qa operational trust CLIs (happy + one failure each)."""

from __future__ import annotations

import csv
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from origenlab_email_pipeline.leads_schema import ensure_leads_tables
from origenlab_email_pipeline.operational_trust import (
    check_cohort_partition,
    check_evidence_url_formats,
    normalized_fit_bucket_counts,
    probe_url,
)

REPO = Path(__file__).resolve().parents[1]


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_minimal_publish_workspace(root: Path, db_path: Path) -> None:
    """Synthetic hunt (20 ids), readiness split, top20, pack summary, audit MD, merged hunt."""
    db_path = db_path.resolve()
    active = root / "reports" / "out" / "active"
    active.mkdir(parents=True, exist_ok=True)
    pack = root / "reports" / "out" / "client_pack_latest"
    pack.mkdir(parents=True, exist_ok=True)
    docs = root / "docs" / "generated"
    docs.mkdir(parents=True, exist_ok=True)

    hunt_ids = list(range(1, 21))
    ready_ids = hunt_ids[:8]
    needs_ids = hunt_ids[8:]

    def hunt_row(i: int) -> dict[str, str]:
        return {
            "id_lead": str(i),
            "ajuste_fit": "high_fit",
            "tipo_comprador": "hospital",
            "url_fuente": f"https://example.com/hunt/{i}",
        }

    hunt_p = active / "leads_contact_hunt_current.csv"
    with hunt_p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id_lead", "ajuste_fit", "tipo_comprador", "url_fuente"])
        w.writeheader()
        for i in hunt_ids:
            w.writerow(hunt_row(i))

    merged_p = active / "leads_contact_hunt_current_merged.csv"
    merged_p.write_bytes(hunt_p.read_bytes())

    def write_ready_csv(path: Path, ids: list[int]) -> None:
        with path.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["id_lead", "org_name"])
            w.writeheader()
            for i in ids:
                w.writerow({"id_lead": str(i), "org_name": f"Org {i}"})

    write_ready_csv(active / "leads_ready_to_contact.csv", ready_ids)
    write_ready_csv(active / "leads_needs_contact_research.csv", needs_ids)
    (active / "leads_not_ready.csv").write_text(
        "id_lead,org_name\n", encoding="utf-8-sig"
    )

    top_fields = [
        "id_lead",
        "org_name",
        "readiness_status",
        "fit_bucket",
        "priority_score",
        "buyer_kind",
        "source_url",
        "evidence_summary",
    ]
    top_p = active / "leads_top20_for_client_report.csv"
    with top_p.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=top_fields)
        w.writeheader()
        for i in ready_ids:
            w.writerow(
                {
                    "id_lead": str(i),
                    "org_name": f"Org {i}",
                    "readiness_status": "ready_now",
                    "fit_bucket": "high_fit",
                    "priority_score": "7.0",
                    "buyer_kind": "hospital",
                    "source_url": f"https://example.com/top/{i}",
                    "evidence_summary": f"ev {i}",
                }
            )
        for i in needs_ids:
            w.writerow(
                {
                    "id_lead": str(i),
                    "org_name": f"Org {i}",
                    "readiness_status": "needs_validation",
                    "fit_bucket": "high_fit",
                    "priority_score": "6.0",
                    "buyer_kind": "hospital",
                    "source_url": f"https://example.com/top/{i}",
                    "evidence_summary": f"ev {i}",
                }
            )

    summary = {
        "generated_at_utc": _iso_now(),
        "totals": {
            "lead_master_rows": 20,
            "fit_bucket": {"high_fit": 20},
        },
    }
    (pack / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_leads_tables(conn)
        for i in hunt_ids:
            conn.execute(
                """
                INSERT INTO lead_master (
                  id, source_name, org_name, fit_bucket, priority_score, status
                ) VALUES (?, 'test', ?, 'high_fit', 7.0, 'nuevo')
                """,
                (i, f"Org {i}"),
            )
        conn.commit()
    finally:
        conn.close()

    audit_body = f"""# Audit

**Base de datos usada:** `{db_path}`
"""
    (docs / "CONTACT_READINESS_AUDIT.md").write_text(audit_body, encoding="utf-8")


def test_verify_client_pack_consistency_passes(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _build_minimal_publish_workspace(tmp_path, db)
    mod = _import_qa("verify_client_pack_consistency")
    ns = _args(tmp_path, db)
    assert mod.run(ns) == 0


def test_verify_client_pack_consistency_fails_on_summary_mismatch(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _build_minimal_publish_workspace(tmp_path, db)
    summary = tmp_path / "reports" / "out" / "client_pack_latest" / "summary.json"
    data = json.loads(summary.read_text(encoding="utf-8"))
    data["totals"]["lead_master_rows"] = 999
    summary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    mod = _import_qa("verify_client_pack_consistency")
    assert mod.run(_args(tmp_path, db)) == 1


def test_audit_operational_trust_passes(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _build_minimal_publish_workspace(tmp_path, db)
    mod = _import_qa("audit_operational_trust")
    ns = _args(tmp_path, db)
    assert mod.run(ns) == 0
    score_json = tmp_path / "reports" / "out" / "active" / "operational_trust_scorecard.json"
    assert score_json.is_file()
    payload = json.loads(score_json.read_text(encoding="utf-8"))
    assert "checks" in payload and len(payload["checks"]) > 0


def test_audit_operational_trust_fails_when_merged_hunt_missing(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _build_minimal_publish_workspace(tmp_path, db)
    merged = tmp_path / "reports" / "out" / "active" / "leads_contact_hunt_current_merged.csv"
    merged.unlink()
    mod = _import_qa("audit_operational_trust")
    assert mod.run(_args(tmp_path, db)) == 1


def test_check_evidence_links_passes_with_mocked_http(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _build_minimal_publish_workspace(tmp_path, db)

    class _Resp:
        status = 200

        def __enter__(self) -> "_Resp":
            return self

        def __exit__(self, *a: object) -> None:
            return None

        def getcode(self) -> int:
            return 200

    mod = _import_qa("check_evidence_links")
    ns = _args(tmp_path, db)
    with patch("origenlab_email_pipeline.operational_trust.urlopen", return_value=_Resp()):
        assert mod.run(ns) == 0


def test_check_evidence_links_fails_on_bad_url_format() -> None:
    c = check_evidence_url_formats(["mailto:a@b.com", "https://ok.example/"])
    assert not c.ok
    assert c.critical


def test_check_evidence_links_fails_http_with_mock(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _build_minimal_publish_workspace(tmp_path, db)
    mod = _import_qa("check_evidence_links")
    ns = _args(tmp_path, db)
    with patch(
        "origenlab_email_pipeline.operational_trust.urlopen",
        side_effect=OSError("network down"),
    ):
        assert mod.run(ns) == 1


def test_publish_gate_aggregate(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _build_minimal_publish_workspace(tmp_path, db)
    script = REPO / "scripts" / "qa" / "publish_gate.py"
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    r = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo-root",
            str(tmp_path),
            "--db",
            str(db),
            "--skip-evidence-http",
        ],
        cwd=str(REPO),
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr + r.stdout


def test_publish_gate_fails_when_verify_fails(tmp_path: Path) -> None:
    db = tmp_path / "db.sqlite"
    _build_minimal_publish_workspace(tmp_path, db)
    summary = tmp_path / "reports" / "out" / "client_pack_latest" / "summary.json"
    data = json.loads(summary.read_text(encoding="utf-8"))
    data["totals"]["lead_master_rows"] = 1
    summary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    script = REPO / "scripts" / "qa" / "publish_gate.py"
    env = {**os.environ, "PYTHONPATH": str(REPO)}
    r = subprocess.run(
        [
            sys.executable,
            str(script),
            "--repo-root",
            str(tmp_path),
            "--db",
            str(db),
            "--skip-evidence-http",
        ],
        cwd=str(REPO),
        env=env,
        check=False,
    )
    assert r.returncode == 1


def test_cohort_partition_detects_overlap(tmp_path: Path) -> None:
    hunt = tmp_path / "h.csv"
    hunt.write_text("id_lead,ajuste_fit\n1,high_fit\n", encoding="utf-8-sig")
    r = tmp_path / "r.csv"
    r.write_text("id_lead,org_name\n1,A\n", encoding="utf-8-sig")
    n = tmp_path / "n.csv"
    n.write_text("id_lead,org_name\n1,B\n", encoding="utf-8-sig")
    nr = tmp_path / "nr.csv"
    nr.write_text("id_lead,org_name\n", encoding="utf-8-sig")
    checks = check_cohort_partition(hunt, r, n, nr)
    disjoint = next(c for c in checks if c.check_id == "readiness_partition_disjoint")
    assert not disjoint.ok


def test_probe_url_invalid() -> None:
    ok, reason = probe_url("not-a-url", timeout=1.0)
    assert not ok
    assert "invalid" in reason


def test_normalized_fit_bucket_counts_merges_blank_keys() -> None:
    a = {"high_fit": 1, "": 3, "low_fit": 2}
    b = {"high_fit": 1, "low_fit": 5}
    assert normalized_fit_bucket_counts(a) == normalized_fit_bucket_counts(b)


def _args(root: Path, db: Path) -> object:
    from argparse import Namespace

    return Namespace(
        repo_root=root,
        db=db,
        max_pack_age_hours=168.0,
        json_out=None,
        md_out=None,
        timeout=5.0,
        max_failures=5,
        max_fail_ratio=0.15,
    )


def _import_qa(stem: str):
    import importlib.util

    path = REPO / "scripts" / "qa" / f"{stem}.py"
    spec = importlib.util.spec_from_file_location(f"qa_{stem}_test", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    if str(REPO) not in sys.path:
        sys.path.insert(0, str(REPO))
    spec.loader.exec_module(mod)
    return mod
