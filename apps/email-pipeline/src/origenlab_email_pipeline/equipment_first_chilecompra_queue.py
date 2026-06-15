"""Build equipment-first queue rows from Mercado Público licitaciones API."""

from __future__ import annotations

import csv
import json
import re
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from origenlab_email_pipeline.chilecompra_api import (
    ChileCompraHttpError,
    fetch_licitacion_by_codigo,
    fetch_licitaciones,
    normalize_licitacion_detail_items,
    normalize_licitaciones_response,
    redact_ticket,
    ticket_from_env,
)
from origenlab_email_pipeline.equipment_first_licitacion_queue import (
    build_equipment_queue_rows_from_normalized_rows,
    write_equipment_queue_csv,
)

SUMMARY_KEYWORD_PREFILTER_RE = re.compile(
    r"centr[ií]fug|microcentr[ií]fug|balanza|sonicador|sonificador|"
    r"homogeneizador|dispersor|incubadora|osm[oó]metr|ultrason|"
    r"laboratorio|equipo[s]?\s+(de\s+)?laboratorio|manten(ci|ció)n.*centr[ií]fug|"
    r"manten(ci|ció)n.*balanza",
    re.I,
)

CANDIDATE_AUDIT_FIELDS = (
    "codigo",
    "title",
    "buyer",
    "region",
    "close_date",
    "prefilter_match",
    "detail_requested",
    "detail_cache_hit",
    "normalized_item_count",
    "detected_output_rows",
    "next_action_summary",
    "reject_reason",
)

FetchLicitacionesFn = Callable[..., dict[str, Any]]
FetchLicitacionByCodigoFn = Callable[..., dict[str, Any]]
SleepFn = Callable[[float], None]


def summary_passes_keyword_prefilter(row: dict[str, str]) -> bool:
    """Broad equipment/lab keyword gate before detail API lookups."""
    hay = " ".join(
        [
            row.get("title", ""),
            row.get("descripcion", ""),
            row.get("tipo_licitacion", ""),
        ]
    )
    return bool(SUMMARY_KEYWORD_PREFILTER_RE.search(hay))


def _extract_licitaciones_listado(payload: dict[str, Any]) -> list[dict[str, Any]]:
    listado = payload.get("Listado")
    if listado is None:
        return []
    if isinstance(listado, list):
        return [item for item in listado if isinstance(item, dict)]
    if isinstance(listado, dict):
        nested = listado.get("Licitacion")
        if nested is None:
            return [listado]
        if isinstance(nested, list):
            return [item for item in nested if isinstance(item, dict)]
        if isinstance(nested, dict):
            return [nested]
    return []


def _annotate_chilecompra_api_source(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    annotated: list[dict[str, str]] = []
    for row in rows:
        updated = dict(row)
        reason = (updated.get("reason") or "").strip()
        if "source:chilecompra_api" not in reason:
            updated["reason"] = (
                f"source:chilecompra_api; {reason}" if reason else "source:chilecompra_api"
            )
        annotated.append(updated)
    return annotated


def default_chilecompra_api_queue_csv_path(
    reports_dir: Path,
    *,
    now: datetime | None = None,
) -> Path:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d")
    return (
        reports_dir
        / "active"
        / "current"
        / f"equipment_first_operator_queue_chilecompra_api_{stamp}.csv"
    )


def default_chilecompra_api_manifest_path(csv_path: Path) -> Path:
    return csv_path.with_suffix(".manifest.json")


def default_chilecompra_candidate_audit_path(
    reports_dir: Path,
    *,
    now: datetime | None = None,
) -> Path:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d")
    return (
        reports_dir
        / "active"
        / "current"
        / f"chilecompra_equipment_candidate_audit_{stamp}.csv"
    )


def default_chilecompra_detail_cache_dir(reports_dir: Path) -> Path:
    return reports_dir / "active" / "current" / "chilecompra_detail_cache"


def _detail_cache_path(cache_dir: Path, codigo: str) -> Path:
    safe_codigo = re.sub(r"[^\w\-.]+", "_", codigo.strip())
    return cache_dir / f"{safe_codigo}.json"


def read_detail_cache(cache_dir: Path, codigo: str) -> dict[str, Any] | None:
    path = _detail_cache_path(cache_dir, codigo)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def write_detail_cache(cache_dir: Path, codigo: str, payload: dict[str, Any]) -> Path:
    path = _detail_cache_path(cache_dir, codigo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _new_candidate_audit_row(summary: dict[str, str], *, detail_requested: bool) -> dict[str, str]:
    codigo = (summary.get("codigo") or "").strip()
    row = {
        "codigo": codigo,
        "title": summary.get("title", ""),
        "buyer": summary.get("buyer", ""),
        "region": summary.get("region", ""),
        "close_date": summary.get("close_date", ""),
        "prefilter_match": "true",
        "detail_requested": "true" if detail_requested else "false",
        "detail_cache_hit": "false",
        "normalized_item_count": "0",
        "detected_output_rows": "0",
        "next_action_summary": "",
        "reject_reason": "",
    }
    if codigo and not detail_requested:
        row["reject_reason"] = "not_detailed_max_details"
    return row


def _finalize_candidate_audit_rows(
    audit_rows: list[dict[str, str]],
    queue_rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    output_by_codigo: dict[str, int] = defaultdict(int)
    actions_by_codigo: dict[str, set[str]] = defaultdict(set)
    for row in queue_rows:
        codigo = (row.get("codigo_licitacion") or "").strip()
        if not codigo:
            continue
        output_by_codigo[codigo] += 1
        actions_by_codigo[codigo].add(row.get("next_action", ""))

    finalized: list[dict[str, str]] = []
    for audit in audit_rows:
        updated = dict(audit)
        codigo = updated["codigo"]
        if updated["detail_requested"] == "true" and updated["reject_reason"] == "":
            count = output_by_codigo.get(codigo, 0)
            updated["detected_output_rows"] = str(count)
            if count > 0:
                updated["next_action_summary"] = ";".join(
                    sorted(action for action in actions_by_codigo[codigo] if action)
                )
            else:
                updated["reject_reason"] = "no_equipment_match_after_detail"
        finalized.append(updated)
    return finalized


def write_candidate_audit_csv(rows: list[dict[str, str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(CANDIDATE_AUDIT_FIELDS))
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in CANDIDATE_AUDIT_FIELDS} for row in rows)


def build_equipment_queue_from_chilecompra_api(
    *,
    ticket: str | None = None,
    estado: str | None = "activas",
    fecha: str | None = None,
    max_details: int = 100,
    detail_sleep_seconds: float = 1.0,
    continue_on_detail_error: bool = True,
    detail_cache_dir: Path | None = None,
    now: datetime | None = None,
    fetch_licitaciones_fn: FetchLicitacionesFn | None = None,
    fetch_licitacion_by_codigo_fn: FetchLicitacionByCodigoFn | None = None,
    sleep_fn: SleepFn | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any], list[dict[str, str]]]:
    """Fetch summaries, detail rows for keyword candidates, and build equipment queue."""
    resolved_ticket = ticket or ticket_from_env()
    now_utc = now or datetime.now()
    fetch_list = fetch_licitaciones_fn or fetch_licitaciones
    fetch_detail = fetch_licitacion_by_codigo_fn or fetch_licitacion_by_codigo
    pause = sleep_fn or time.sleep

    summary_payload = fetch_list(
        ticket=resolved_ticket,
        estado=estado,
        fecha=fecha,
    )
    summary_rows = normalize_licitaciones_response(summary_payload)
    candidate_summaries = [row for row in summary_rows if summary_passes_keyword_prefilter(row)]
    detail_candidates = candidate_summaries[: max(0, max_details)]

    candidate_audit_rows = [
        _new_candidate_audit_row(
            summary,
            detail_requested=index < max(0, max_details),
        )
        for index, summary in enumerate(candidate_summaries)
    ]
    audit_by_codigo = {
        (row.get("codigo") or "").strip(): row
        for row in candidate_audit_rows
        if (row.get("codigo") or "").strip()
    }

    normalized_item_rows: list[dict[str, str]] = []
    detail_requests = 0
    detail_cache_hits = 0
    detail_cache_writes = 0
    detail_errors: list[dict[str, str]] = []
    detail_error_codes: list[str] = []
    for index, summary in enumerate(detail_candidates):
        if index > 0 and detail_sleep_seconds > 0:
            pause(detail_sleep_seconds)
        codigo = (summary.get("codigo") or "").strip()
        if not codigo:
            continue
        audit = audit_by_codigo.get(codigo)
        if audit is not None:
            audit["detail_requested"] = "true"
            audit["reject_reason"] = ""

        detail_payload: dict[str, Any] | None = None
        if detail_cache_dir is not None:
            detail_payload = read_detail_cache(detail_cache_dir, codigo)
            if detail_payload is not None:
                detail_cache_hits += 1
                if audit is not None:
                    audit["detail_cache_hit"] = "true"

        if detail_payload is None:
            try:
                detail_payload = fetch_detail(codigo, ticket=resolved_ticket)
            except ChileCompraHttpError as exc:
                detail_requests += 1
                detail_error_codes.append(codigo)
                detail_errors.append(
                    {
                        "codigo": codigo,
                        "error": redact_ticket(str(exc), resolved_ticket),
                    }
                )
                if audit is not None:
                    audit["reject_reason"] = "detail_error"
                if not continue_on_detail_error:
                    raise
                normalized_item_rows.append(summary)
                continue
            detail_requests += 1
            if detail_cache_dir is not None:
                write_detail_cache(detail_cache_dir, codigo, detail_payload)
                detail_cache_writes += 1

        codigo_item_rows: list[dict[str, str]] = []
        licitaciones = _extract_licitaciones_listado(detail_payload)
        if not licitaciones:
            codigo_item_rows.append(summary)
        else:
            for licitacion in licitaciones:
                codigo_item_rows.extend(normalize_licitacion_detail_items(licitacion))
        normalized_item_rows.extend(codigo_item_rows)
        if audit is not None:
            audit["normalized_item_count"] = str(len(codigo_item_rows))

    queue_rows = build_equipment_queue_rows_from_normalized_rows(
        normalized_item_rows,
        now=now_utc,
    )
    queue_rows = _annotate_chilecompra_api_source(queue_rows)
    candidate_audit_rows = _finalize_candidate_audit_rows(candidate_audit_rows, queue_rows)

    by_next_action: dict[str, int] = defaultdict(int)
    for row in queue_rows:
        by_next_action[row["next_action"]] += 1

    manifest = {
        "source": "chilecompra_api",
        "generated_at_utc": (
            now_utc.replace(tzinfo=timezone.utc).isoformat()
            if now_utc.tzinfo is None
            else now_utc.astimezone(timezone.utc).replace(microsecond=0).isoformat()
        ),
        "estado": estado,
        "fecha": fecha,
        "fetched_summaries": len(summary_rows),
        "candidate_summaries": len(candidate_summaries),
        "detail_requests": detail_requests,
        "detail_errors": detail_errors,
        "detail_error_count": len(detail_errors),
        "detail_error_codes": detail_error_codes,
        "detail_sleep_seconds": detail_sleep_seconds,
        "detail_cache_hits": detail_cache_hits,
        "detail_cache_writes": detail_cache_writes,
        "detail_cache_dir": str(detail_cache_dir) if detail_cache_dir is not None else "",
        "normalized_item_rows": len(normalized_item_rows),
        "output_rows": len(queue_rows),
        "by_next_action": dict(by_next_action),
        "candidate_audit_rows": len(candidate_audit_rows),
    }
    return queue_rows, manifest, candidate_audit_rows


def write_chilecompra_api_queue_outputs(
    *,
    rows: list[dict[str, str]],
    manifest: dict[str, Any],
    out_csv: Path,
    manifest_path: Path | None = None,
) -> dict[str, Any]:
    """Write equipment queue CSV and JSON manifest summary."""
    write_equipment_queue_csv(rows, out_csv)
    manifest_file = manifest_path or default_chilecompra_api_manifest_path(out_csv)
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_payload = dict(manifest)
    manifest_payload["out_csv"] = str(out_csv)
    manifest_file.write_text(
        json.dumps(manifest_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "out_csv": str(out_csv),
        "manifest_path": str(manifest_file),
        **manifest_payload,
    }
