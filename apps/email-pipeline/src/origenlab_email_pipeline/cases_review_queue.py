"""Message-level review queue for Streamlit «Casos para revisar» (v1: Gmail contacto only).

Read-only helpers; no drafting here. See docs/pipeline/CASOS_PARA_REVISAR.md.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from origenlab_email_pipeline.contacto_gmail_source import (
    CONTACTO_GMAIL_SOURCE_SQL,
    sql_predicate_contacto_gmail_source,
)


def _noise_sql_predicate() -> str:
    """Deterministic exclusion of obvious DSN / bounce-style rows (narrow)."""
    return """(
      lower(COALESCE(sender, '')) LIKE '%mailer-daemon%'
      OR lower(COALESCE(sender, '')) LIKE '%mailer daemon%'
      OR lower(COALESCE(sender, '')) LIKE '%postmaster%'
      OR lower(COALESCE(subject, '')) LIKE '%undeliverable%'
      OR lower(COALESCE(subject, '')) LIKE '%undelivered%'
      OR lower(COALESCE(subject, '')) LIKE '%delivery status%'
      OR lower(COALESCE(subject, '')) LIKE '%delivery failure%'
      OR lower(COALESCE(subject, '')) LIKE '%failure notice%'
      OR lower(COALESCE(subject, '')) LIKE '%returned mail%'
      OR lower(COALESCE(subject, '')) LIKE '%message not delivered%'
    )"""


def _date_prefix_cutoff(days: int) -> str:
    d = max(1, min(int(days), 3660))
    return (date.today() - timedelta(days=d)).isoformat()


@dataclass(frozen=True)
class CasesReviewQueueResult:
    rows: list[dict[str, Any]]
    enrichment_available: bool
    """True if ``commercial_email_signal_fact`` was used."""
    reduced_mode: bool
    """True when enrichment table was missing."""
    caption_es: str
    """User-facing note (Spanish)."""


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    r = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,),
    ).fetchone()
    return bool(r)


def fetch_cases_review_queue(
    conn: sqlite3.Connection,
    *,
    days_window: int = 30,
    exclude_obvious_noise: bool = True,
    positive_signal_only: bool = False,
    limit: int = 200,
) -> CasesReviewQueueResult:
    """
    Recent Gmail contacto messages as reviewable cases (one row per ``emails.id``).

    Optionally aggregates ``commercial_email_signal_fact`` when the table exists.
    """
    if not _table_exists(conn, "emails"):
        return CasesReviewQueueResult(
            rows=[],
            enrichment_available=False,
            reduced_mode=True,
            caption_es="No hay tabla de correos en esta base.",
        )

    cap = max(10, min(int(limit), 500))
    cutoff = _date_prefix_cutoff(days_window)
    noise_ex = exclude_obvious_noise
    cisf = _table_exists(conn, "commercial_email_signal_fact")

    if positive_signal_only and not cisf:
        return CasesReviewQueueResult(
            rows=[],
            enrichment_available=False,
            reduced_mode=True,
            caption_es="El filtro «solo señal positiva» requiere la tabla de inteligencia comercial "
            "(ejecute build_commercial_intel_v1). Mostrando vacío; desactive el filtro o construya la capa CI.",
        )

    date_clause = (
        "(length(COALESCE(e.date_iso, '')) >= 10 AND substr(e.date_iso, 1, 10) >= ?)"
    )
    _noise_e = _noise_sql_predicate().replace("sender", "e.sender").replace("subject", "e.subject")
    noise_clause = f"AND NOT {_noise_e}" if noise_ex else ""
    contact_where = sql_predicate_contacto_gmail_source(table_alias="e", coalesce_null=True)
    pos_clause = ""
    if positive_signal_only and cisf:
        pos_clause = "AND COALESCE(agg.has_positive, 0) = 1"

    params: list[Any] = [cutoff]

    if cisf:
        sql = f"""
        SELECT
          e.id AS email_id,
          e.date_iso,
          substr(COALESCE(e.subject, ''), 1, 140) AS subject_preview,
          substr(COALESCE(e.sender, ''), 1, 140) AS sender_preview,
          e.source_file,
          COALESCE(agg.has_positive, 0) AS has_positive_signal,
          COALESCE(agg.has_suppression, 0) AS has_suppression_signal,
          agg.max_positive_strength AS max_positive_strength
        FROM emails e
        LEFT JOIN (
          SELECT
            email_id,
            MAX(CASE WHEN signal_kind = 'positive' THEN 1 ELSE 0 END) AS has_positive,
            MAX(CASE WHEN signal_kind = 'suppression' THEN 1 ELSE 0 END) AS has_suppression,
            MAX(CASE WHEN signal_kind = 'positive' THEN strength_score END) AS max_positive_strength
          FROM commercial_email_signal_fact
          GROUP BY email_id
        ) agg ON agg.email_id = e.id
        WHERE {contact_where}
          AND {date_clause}
          {noise_clause}
          {pos_clause}
        ORDER BY
          CASE WHEN e.date_iso IS NULL OR trim(e.date_iso) = '' THEN 1 ELSE 0 END,
          e.date_iso DESC
        LIMIT ?
        """
        params.append(cap)
    else:
        sql = f"""
        SELECT
          e.id AS email_id,
          e.date_iso,
          substr(COALESCE(e.subject, ''), 1, 140) AS subject_preview,
          substr(COALESCE(e.sender, ''), 1, 140) AS sender_preview,
          e.source_file,
          NULL AS has_positive_signal,
          NULL AS has_suppression_signal,
          NULL AS max_positive_strength
        FROM emails e
        WHERE {contact_where}
          AND {date_clause}
          {noise_clause}
        ORDER BY
          CASE WHEN e.date_iso IS NULL OR trim(e.date_iso) = '' THEN 1 ELSE 0 END,
          e.date_iso DESC
        LIMIT ?
        """
        params.append(cap)

    conn.row_factory = sqlite3.Row
    cur = conn.execute(sql, params)
    raw_rows = [dict(r) for r in cur.fetchall()]

    caption = (
        "Cola enriquecida con señales por mensaje (inteligencia comercial v1)."
        if cisf
        else "Modo reducido: no existe la tabla `commercial_email_signal_fact` en esta base. "
        "Solo se listan correos recientes de Gmail contacto; ejecute `build_commercial_intel_v1` para pistas comerciales."
    )

    return CasesReviewQueueResult(
        rows=raw_rows,
        enrichment_available=cisf,
        reduced_mode=not cisf,
        caption_es=caption,
    )


def fetch_case_detail(
    conn: sqlite3.Connection,
    *,
    email_id: int,
    include_signal_breakdown: bool = True,
) -> dict[str, Any] | None:
    """Single message detail for the detail panel (read-only)."""
    if not _table_exists(conn, "emails"):
        return None
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        """
        SELECT id, date_iso, subject, sender, source_file, message_id,
               top_reply_clean, full_body_clean, body_text_clean, body
        FROM emails
        WHERE id = ?
        """,
        (int(email_id),),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    body = (
        (d.get("top_reply_clean") or "").strip()
        or (d.get("full_body_clean") or "").strip()
        or (d.get("body_text_clean") or "").strip()
        or (d.get("body") or "").strip()
    )
    d["body_preview"] = body[:4000] if len(body) <= 4000 else body[:3997] + "..."
    cisf = _table_exists(conn, "commercial_email_signal_fact")
    signals: list[dict[str, Any]] = []
    if include_signal_breakdown and cisf:
        sig_rows = conn.execute(
            """
            SELECT signal_code, signal_kind, reason_code, strength_score, confidence_score, reason_text
            FROM commercial_email_signal_fact
            WHERE email_id = ?
            ORDER BY strength_score DESC
            LIMIT 30
            """,
            (int(email_id),),
        ).fetchall()
        signals = [dict(x) for x in sig_rows]
    d["commercial_signals"] = signals

    doc_n: int | None = None
    if _table_exists(conn, "document_master"):
        r2 = conn.execute(
            "SELECT COUNT(*) FROM document_master WHERE email_id = ?",
            (int(email_id),),
        ).fetchone()
        doc_n = int(r2[0]) if r2 else 0
    d["document_count"] = doc_n

    return d


def commercial_hint_es(row: dict[str, Any], *, enrichment_available: bool) -> str:
    """One short Spanish hint for the queue table."""
    if not enrichment_available:
        return "—"
    hp = row.get("has_positive_signal")
    hs = row.get("has_suppression_signal")
    mx = row.get("max_positive_strength")
    parts: list[str] = []
    if hp:
        parts.append("Señal comercial (+)")
    if hs:
        parts.append("Posible ruido/supresión")
    if mx is not None and float(mx) > 0:
        parts.append(f"Intensidad máx. (+): {float(mx):.2f}")
    return " · ".join(parts) if parts else "Sin señal CI"


def looks_like_obvious_noise(sender: str | None, subject: str | None) -> bool:
    """Mirror SQL noise predicate for tests (Python)."""
    snd = (sender or "").lower()
    sub = (subject or "").lower()
    return (
        "mailer-daemon" in snd
        or "mailer daemon" in snd
        or "postmaster" in snd
        or "undeliverable" in sub
        or "undelivered" in sub
        or "delivery status" in sub
        or "delivery failure" in sub
        or "failure notice" in sub
        or "returned mail" in sub
        or "message not delivered" in sub
    )
