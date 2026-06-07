"""CLI tests for apply_ready8_contact_patch (plan-only by default)."""

from __future__ import annotations

import csv
import importlib.util
import io
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "leads" / "campaigns" / "apply_ready8_contact_patch.py"

READY_IDS = (608694, 622998, 608621, 617311, 619403, 608386, 609442, 610539)

HUNT_HEADERS = [
    "id_lead",
    "organizacion_compradora",
    "ajuste_fit",
    "puntaje_prioridad",
    "tipo_comprador",
    "url_fuente",
    "resumen_evidencia",
    "confianza_contacto",
    "estado_seguimiento",
    "notas_manuales",
    "nombre_contacto_compras",
    "rol_contacto_compras",
    "email_publico_compras",
    "telefono_publico_compras",
    "nombre_contacto_tecnico",
    "rol_contacto_tecnico",
    "email_publico_tecnico",
    "telefono_publico_tecnico",
    "email_contacto_general",
    "telefono_contacto_general",
    "url_evidencia_compras",
    "url_evidencia_tecnico",
    "url_evidencia_general",
]

READY_HEADERS = [
    "id_lead",
    "primary_contact_email",
    "contact_name",
    "contact_role",
    "contact_phone",
    "evidence_url_dr",
    "reconciliation_reason",
    "recommended_contact_route",
]

NEEDS_HEADERS = [
    "id_lead",
    "priority_score",
    "primary_contact_email",
    "contact_name",
    "contact_role",
    "contact_phone",
    "dr_confidence",
    "reconciliation_reason",
    "recommended_contact_route",
]


def _load_script():
    spec = importlib.util.spec_from_file_location("apply_ready8_contact_patch", SCRIPT)
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


def _hunt_row(lid: int) -> dict[str, str]:
    return {
        "id_lead": str(lid),
        "organizacion_compradora": f"Org {lid}",
        "ajuste_fit": "high_fit",
        "puntaje_prioridad": "8.0",
        "tipo_comprador": "hospital",
        "url_fuente": f"https://example.cl/{lid}",
        "resumen_evidencia": "evidence",
        "confianza_contacto": "",
        "estado_seguimiento": "",
        "notas_manuales": "",
        "nombre_contacto_compras": "",
        "rol_contacto_compras": "",
        "email_publico_compras": "",
        "telefono_publico_compras": "",
        "nombre_contacto_tecnico": "",
        "rol_contacto_tecnico": "",
        "email_publico_tecnico": "",
        "telefono_publico_tecnico": "",
        "email_contacto_general": "",
        "telefono_contacto_general": "",
        "url_evidencia_compras": "",
        "url_evidencia_tecnico": "",
        "url_evidencia_general": "",
    }


def _ready_row(lid: int) -> dict[str, str]:
    return {
        "id_lead": str(lid),
        "primary_contact_email": f"ready{lid}@cliente.cl",
        "contact_name": f"Ready {lid}",
        "contact_role": "Compras",
        "contact_phone": "",
        "evidence_url_dr": f"https://mp.cl/{lid}",
        "reconciliation_reason": f"ready reason {lid}",
        "recommended_contact_route": "compras",
    }


def _needs_row(lid: int, *, score: str = "7.0") -> dict[str, str]:
    return {
        "id_lead": str(lid),
        "priority_score": score,
        "primary_contact_email": f"needs{lid}@cliente.cl",
        "contact_name": f"Needs {lid}",
        "contact_role": "Compras",
        "contact_phone": "",
        "dr_confidence": "alta",
        "reconciliation_reason": f"needs reason {lid}",
        "recommended_contact_route": "compras",
    }


def _install_paths(mod, tmp_path: Path) -> dict[str, Path]:
    active = tmp_path / "reports" / "out" / "active"
    docs_gen = tmp_path / "docs" / "generated"
    paths = {
        "hunt": active / "leads_contact_hunt_current.csv",
        "ready8": active / "leads_dr50_ready_candidates.csv",
        "needs": active / "leads_dr50_needs_research.csv",
        "patch": active / "leads_contact_hunt_current_ready8_patch.csv",
        "top20": active / "leads_top20_for_client_report.csv",
        "plan": docs_gen / "READY8_AND_TOP20_REPORTING_PLAN.md",
    }
    mod.HUNT = paths["hunt"]
    mod.READY8 = paths["ready8"]
    mod.NEEDS = paths["needs"]
    mod.PATCH_OUT = paths["patch"]
    mod.TOP20_OUT = paths["top20"]
    mod.PLAN_MD = paths["plan"]
    return paths


def _write_fixtures(paths: dict[str, Path], *, ready_ids: tuple[int, ...] = READY_IDS) -> str:
    needs_ids = [700000 + i for i in range(12)]
    hunt_rows = [_hunt_row(lid) for lid in ready_ids]
    hunt_rows.extend(_hunt_row(lid) for lid in needs_ids)
    hunt_rows.extend(_hunt_row(999001) for _ in range(2))
    _write_csv(paths["hunt"], HUNT_HEADERS, hunt_rows)
    _write_csv(paths["ready8"], READY_HEADERS, [_ready_row(lid) for lid in ready_ids])
    _write_csv(
        paths["needs"],
        NEEDS_HEADERS,
        [_needs_row(lid, score=str(9 - i * 0.1)) for i, lid in enumerate(needs_ids)],
    )
    return paths["hunt"].read_text(encoding="utf-8")


def _run_main(mod, argv: list[str] | None = None) -> tuple[int | None, str, str]:
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
    paths = _install_paths(mod, tmp_path)
    original_hunt = _write_fixtures(paths)

    code, stdout, _stderr = _run_main(mod, [])
    assert code == 0
    assert "Plan only: pass --apply to write patched hunt/top20/report files." in stdout
    assert "--apply" in stdout
    assert paths["hunt"].read_text(encoding="utf-8") == original_hunt
    assert not paths["patch"].exists()
    assert not paths["top20"].exists()
    assert not paths["plan"].exists()
    assert "patched rows: 8" in stdout
    assert "top20 rows: 20" in stdout


def test_apply_writes_all_expected_outputs(tmp_path: Path) -> None:
    mod = _load_script()
    paths = _install_paths(mod, tmp_path)
    original_hunt = _write_fixtures(paths)

    code, stdout, _stderr = _run_main(mod, ["--apply"])
    assert code == 0
    assert paths["patch"].is_file()
    assert paths["top20"].is_file()
    assert paths["plan"].is_file()
    assert paths["hunt"].read_text(encoding="utf-8") != original_hunt
    assert "Updated" in stdout
    assert "Wrote" in stdout
    with paths["top20"].open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 20


def test_apply_and_dry_run_rejected(tmp_path: Path) -> None:
    mod = _load_script()
    paths = _install_paths(mod, tmp_path)
    _write_fixtures(paths)

    code, _stdout, stderr = _run_main(mod, ["--apply", "--dry-run"])
    assert code == 2
    assert "cannot be used together" in stderr
    assert not paths["patch"].exists()


def test_ready8_mismatch_returns_nonzero_without_writes(tmp_path: Path) -> None:
    mod = _load_script()
    paths = _install_paths(mod, tmp_path)
    _write_fixtures(paths, ready_ids=(608694, 622998, 608621, 617311, 619403, 608386, 609442, 999999))

    code, _stdout, stderr = _run_main(mod, ["--apply"])
    assert code == 1
    assert "mismatch" in stderr.lower()
    assert not paths["patch"].exists()
    assert not paths["top20"].exists()
    assert not paths["plan"].exists()
