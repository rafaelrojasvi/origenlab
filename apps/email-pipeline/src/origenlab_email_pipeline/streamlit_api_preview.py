"""Optional Streamlit page: read-only preview of Postgres mirror API (apps/api :8001 /mirror/*)."""

from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import streamlit as st

from origenlab_email_pipeline.streamlit_page_status import render_page_status

ENV_API_BASE_URL = "ORIGENLAB_API_BASE_URL"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8001"

MIRROR_LABEL = "Postgres mirror / eventually consistent"

SUMMARY_COUNT_FIELDS: tuple[tuple[str, str], ...] = (
    ("contact_count", "Contactos"),
    ("organization_count", "Organizaciones"),
    ("opportunity_signal_count", "Señales oportunidad"),
    ("email_suppression_count", "Supresiones email"),
    ("domain_suppression_count", "Supresiones dominio"),
    ("outreach_state_count", "Estados outreach"),
)


def api_preview_enabled() -> bool:
    """True when ORIGENLAB_API_BASE_URL is set (non-empty)."""
    return bool(os.environ.get(ENV_API_BASE_URL, "").strip())


def primary_sidebar_pages(base_pages: list[str]) -> list[str]:
    """Append API preview when env enables it; does not mutate ``base_pages``."""
    pages = list(base_pages)
    if api_preview_enabled():
        pages.append("API preview")
    return pages


def normalize_api_base_url(url: str) -> str:
    u = url.strip().rstrip("/")
    if not u:
        raise ValueError("empty API base URL")
    if not u.startswith(("http://", "https://")):
        u = f"http://{u}"
    return u


def build_api_url(base_url: str, path: str) -> str:
    p = path if path.startswith("/") else f"/{path}"
    return f"{normalize_api_base_url(base_url)}{p}"


def api_preview_paths(_base_url: str) -> dict[str, str]:
    """Resolve GET paths for API preview (apps/api mirror on :8001)."""
    return {
        "health": "/mirror/health/dependencies",
        "health_label": "/mirror/health/dependencies",
        "summary": "/mirror/dashboard/summary?scope=canonical",
        "summary_label": "/mirror/dashboard/summary",
        "readiness": "/mirror/outbound/readiness",
        "readiness_label": "/mirror/outbound/readiness",
    }


def fetch_json(
    base_url: str,
    path: str,
    *,
    timeout: float = 10.0,
    opener: Callable[..., Any] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    """GET JSON object from API path; returns (data, error_message)."""
    url = build_api_url(base_url, path)
    open_fn = opener or urlopen
    try:
        req = Request(url, headers={"Accept": "application/json"})
        with open_fn(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
        data = json.loads(body)
        if not isinstance(data, dict):
            return None, "expected JSON object response"
        return data, None
    except HTTPError as exc:
        return None, f"HTTP {exc.code}: {exc.reason}"
    except URLError as exc:
        return None, f"connection failed: {exc.reason}"
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"
    except TimeoutError:
        return None, "request timed out"
    except OSError as exc:
        return None, str(exc)


def resolve_api_base_url(override: str | None = None) -> str:
    if override is not None and override.strip():
        return normalize_api_base_url(override)
    env = os.environ.get(ENV_API_BASE_URL, "").strip()
    if env:
        return normalize_api_base_url(env)
    return DEFAULT_API_BASE_URL


def summary_count_cards(summary: dict[str, Any]) -> list[tuple[str, int | str]]:
    cards: list[tuple[str, int | str]] = []
    for key, label in SUMMARY_COUNT_FIELDS:
        if key in summary:
            cards.append((label, summary[key]))
    return cards


def readiness_needs_warning(readiness: dict[str, Any]) -> bool:
    return readiness.get("verdict") == "ready_with_warnings"


def render_api_preview_page() -> None:
    """Render read-only API preview (no SQLite writes; GET only)."""
    st.subheader("API preview")
    render_page_status("API preview")
    st.caption(
        f"**{MIRROR_LABEL}** — lectura opcional del API FastAPI (Slice 1). "
        "El panel operativo sigue usando **SQLite**; esta vista no sustituye gates ni envíos."
    )
    st.info(
        f"Fuente de datos: **{MIRROR_LABEL}**. "
        "Los conteos pueden diferir del Streamlit principal hasta la próxima carga Postgres."
    )

    default_url = resolve_api_base_url()
    base_input = st.text_input(
        "API base URL",
        value=default_url,
        help=f"Variable de entorno `{ENV_API_BASE_URL}` o valor por defecto (`apps/api` :8001).",
        key="api_preview_base_url",
    )

    if st.button("Actualizar desde API", type="primary", key="api_preview_refresh"):
        st.session_state["api_preview_do_fetch"] = True

    if not st.session_state.get("api_preview_do_fetch"):
        st.caption(
            "Pulse **Actualizar desde API** para cargar dependencias, resumen mart y readiness "
            "(rutas `GET /mirror/*` en apps/api :8001)."
        )
        return

    try:
        base = resolve_api_base_url(base_input)
    except ValueError as exc:
        st.error(str(exc))
        return

    paths = api_preview_paths(base)
    health, health_err = fetch_json(base, paths["health"])
    summary, summary_err = fetch_json(base, paths["summary"])
    readiness, readiness_err = fetch_json(base, paths["readiness"])

    col_h, col_s, col_r = st.columns(3)
    with col_h:
        st.markdown(f"#### {paths['health_label']}")
        if health_err:
            st.error(health_err)
        elif health:
            st.success(health.get("status", "ok"))
            if health.get("service"):
                st.caption(f"service: {health.get('service', '—')} · read_only: {health.get('read_only')}")
            elif health.get("postgres_url_redacted"):
                st.caption(f"postgres: {health.get('postgres_url_redacted', '—')}")

    with col_s:
        st.markdown(f"#### {paths['summary_label']}")
        if summary_err:
            st.error(summary_err)
        elif summary:
            if summary.get("eventually_consistent"):
                st.caption(MIRROR_LABEL)
            cards = summary_count_cards(summary)
            if cards:
                metric_cols = st.columns(min(3, len(cards)))
                for i, (label, value) in enumerate(cards):
                    metric_cols[i % len(metric_cols)].metric(label, value)
            else:
                st.caption("Sin conteos en la respuesta.")

    with col_r:
        st.markdown(f"#### {paths['readiness_label']}")
        if readiness_err:
            st.error(readiness_err)
        elif readiness:
            verdict = readiness.get("verdict", "unknown")
            st.metric("Veredicto", verdict)
            if readiness.get("eventually_consistent"):
                st.caption(MIRROR_LABEL)
            if readiness_needs_warning(readiness):
                st.warning(
                    "Listo con advertencias (`ready_with_warnings`). "
                    "Revise `warnings` en el API; no use solo esta vista para envío."
                )
            for w in readiness.get("warnings") or []:
                st.warning(str(w))
            counts = readiness.get("counts") or {}
            if counts:
                st.markdown("**Conteos readiness**")
                rc = st.columns(min(3, len(counts)))
                for i, (k, v) in enumerate(sorted(counts.items())):
                    rc[i % len(rc)].metric(str(k), v)

    with st.expander("Respuestas JSON (técnico)"):
        st.json(
            {
                "health": health if health else {"error": health_err},
                "dashboard_summary": summary if summary else {"error": summary_err},
                "outbound_readiness": readiness if readiness else {"error": readiness_err},
            }
        )
