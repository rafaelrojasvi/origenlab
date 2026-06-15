"""Build equipment-first queue rows from Mercado Público licitaciones API."""

from __future__ import annotations

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


def build_equipment_queue_from_chilecompra_api(
    *,
    ticket: str | None = None,
    estado: str | None = "activas",
    fecha: str | None = None,
    max_details: int = 100,
    detail_sleep_seconds: float = 1.0,
    continue_on_detail_error: bool = True,
    now: datetime | None = None,
    fetch_licitaciones_fn: FetchLicitacionesFn | None = None,
    fetch_licitacion_by_codigo_fn: FetchLicitacionByCodigoFn | None = None,
    sleep_fn: SleepFn | None = None,
) -> tuple[list[dict[str, str]], dict[str, Any]]:
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

    normalized_item_rows: list[dict[str, str]] = []
    detail_requests = 0
    detail_errors: list[dict[str, str]] = []
    detail_error_codes: list[str] = []
    for index, summary in enumerate(detail_candidates):
        if index > 0 and detail_sleep_seconds > 0:
            pause(detail_sleep_seconds)
        codigo = (summary.get("codigo") or "").strip()
        if not codigo:
            continue
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
            if not continue_on_detail_error:
                raise
            normalized_item_rows.append(summary)
            continue
        detail_requests += 1
        licitaciones = _extract_licitaciones_listado(detail_payload)
        if not licitaciones:
            normalized_item_rows.append(summary)
            continue
        for licitacion in licitaciones:
            normalized_item_rows.extend(normalize_licitacion_detail_items(licitacion))

    queue_rows = build_equipment_queue_rows_from_normalized_rows(
        normalized_item_rows,
        now=now_utc,
    )
    queue_rows = _annotate_chilecompra_api_source(queue_rows)

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
        "normalized_item_rows": len(normalized_item_rows),
        "output_rows": len(queue_rows),
        "by_next_action": dict(by_next_action),
    }
    return queue_rows, manifest


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
