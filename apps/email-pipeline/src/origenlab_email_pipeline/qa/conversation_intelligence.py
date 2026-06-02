#!/usr/bin/env python3
"""Read-only OrigenLab email conversation intelligence export (library)."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from email.header import decode_header, make_header
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.business_mart import domain_of, emails_in
from origenlab_email_pipeline.contacto_gmail_source import sql_predicate_contacto_gmail_source

REAL_CLIENT_CONVERSATION_COLUMNS = [
    "organization",
    "domain",
    "contact_email",
    "contact_name",
    "sector",
    "region",
    "city",
    "first_outbound_date",
    "first_inbound_date",
    "last_interaction_date",
    "sent_count",
    "received_count",
    "status",
    "product_or_need",
    "summary",
    "recommended_next_action",
    "confidence",
]

FOLLOW_UP_COLUMNS = [
    "priority",
    "organization",
    "contact_email",
    "contact_name",
    "last_inbound_date",
    "last_outbound_date",
    "days_since_last_touch",
    "product_or_need",
    "why_follow_up_needed",
    "suggested_follow_up_message",
    "confidence",
]

COMMERCIAL_OPPORTUNITIES_COLUMNS = [
    "priority",
    "organization",
    "contact_email",
    "contact_name",
    "sector",
    "region",
    "city",
    "product_or_need",
    "status",
    "last_interaction_date",
    "summary",
    "recommended_next_action",
    "confidence",
]

NOISE_SUPPLIER_COLUMNS = [
    "category",
    "organization_or_sender",
    "email",
    "domain",
    "last_date",
    "summary",
    "reason_classified_as_noise_or_supplier",
]

REPORT_FILENAME = "email_conversation_intelligence_report.md"

NOISE_PATTERNS = [
    r"mailer-daemon",
    r"postmaster",
    r"delivery status notification",
    r"undeliverable",
    r"returned mail",
    r"out of office",
    r"automatic reply",
    r"auto-?reply",
    r"unsubscribe",
    r"newsletter",
    r"mercadopublico",
    r"chilecompra",
    r"payment reminder",
]

SUPPLIER_PATTERNS = [
    r"distributor",
    r"representante",
    r"fabricante",
    r"proveedor",
    r"invoice",
    r"factura",
    r"dhl",
    r"fedex",
    r"ups",
    r"courier",
]

HOT_PATTERNS = [
    r"cotiz",
    r"quote",
    r"precio",
    r"valor",
    r"ficha t[ée]cnica",
    r"disponibilidad",
    r"stock",
    r"reuni[oó]n",
    r"agenda",
]

WARM_PATTERNS = [
    r"interesad",
    r"me interesa",
    r"enviar informaci[oó]n",
    r"deriv",
    r"contactar",
    r"podr[ií]a",
    r"gracias",
]

NEED_PATTERNS: dict[str, list[str]] = {
    "centrifuga_microcentrifuga": [r"centr[ií]fug", r"microcentr[ií]fug"],
    "osmometro_osmometria": [r"osm[oó]metr", r"osmometr[ií]a"],
    "electroforesis": [r"electroforesis"],
    "reactivos": [r"reactiv"],
    "biorreactor_fotobiorreactor": [r"biorreactor", r"fotobiorreactor"],
    "ultrasonidos_dispersion_homogeneizador": [r"ultrason", r"dispersi[oó]n", r"homogeneiz"],
    "incubadora": [r"incubador"],
    "autoclave": [r"autoclave"],
    "espectrofotometro": [r"espectrofot[oó]metr", r"spectrophotometer"],
    "microscopio": [r"microscop"],
    "balanza": [r"\bbalanza\b", r"balance anal"],
    "laboratorio_clinico": [r"laboratorio cl[ií]nico", r"clinical lab"],
    "alimentos_inocuidad_microbiologia": [r"alimento", r"inocuidad", r"microbiolog"],
    "agua_ambiente_analisis": [r"\bagua\b", r"ambient", r"an[aá]lisis"],
    "control_calidad_qa_qc": [r"control de calidad", r"\bqa\b", r"\bqc\b"],
    "cotizacion_precio_ficha_disponibilidad": [r"cotiz", r"precio", r"ficha t[ée]cnica", r"disponibilidad"],
}


@dataclass
class MessageEvent:
    id: int
    date_iso: str
    dt: datetime | None
    direction: str
    folder: str
    subject: str
    sender_email: str
    counterparty_email: str
    counterparty_domain: str
    body: str
    source_file: str


@dataclass
class ConversationIntelligenceBuildResult:
    summary_json: dict[str, Any]
    report_md: str
    real_conversations: list[dict[str, Any]]
    follow_ups: list[dict[str, Any]]
    opportunities: list[dict[str, Any]]
    noise_rows: list[dict[str, Any]]


def decode_subject(value: str) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value))).strip()
    except Exception:
        return value.strip()


def parse_date(date_iso: str) -> datetime | None:
    if not date_iso:
        return None
    raw = date_iso.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=UTC)
        return dt
    except ValueError:
        return None


def normalize_subject(subject: str) -> str:
    s = decode_subject(subject).lower()
    s = re.sub(r"^\s*((re|fw|fwd)\s*:\s*)+", "", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^\w\sáéíóúñü]", " ", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def compile_any(patterns: list[str]) -> re.Pattern[str]:
    return re.compile("|".join(patterns), re.IGNORECASE)


NOISE_RE = compile_any(NOISE_PATTERNS)
SUPPLIER_RE = compile_any(SUPPLIER_PATTERNS)
HOT_RE = compile_any(HOT_PATTERNS)
WARM_RE = compile_any(WARM_PATTERNS)


def is_noncommercial_contact(email: str, domain: str) -> bool:
    e = (email or "").lower()
    d = (domain or "").lower()
    local = e.split("@")[0] if "@" in e else ""
    if d in {"origenlab.cl", "labdelivery.cl"}:
        return True
    if any(token in local for token in ("noreply", "no-reply", "mailer-daemon", "postmaster", "workspace-noreply")):
        return True
    return False


def fetch_rows(
    conn: sqlite3.Connection,
    since_days: int | None,
    gmail_user: str,
    *,
    include_legacy_email_sources: bool,
) -> list[sqlite3.Row]:
    params: list[Any] = []
    where_parts = [
        "(lower(COALESCE(sender,'')) LIKE ? OR lower(COALESCE(recipients,'')) LIKE ? OR lower(COALESCE(folder,'')) LIKE ? OR lower(COALESCE(source_file,'')) LIKE ?)"
    ]
    params.extend([f"%{gmail_user.lower()}%", f"%{gmail_user.lower()}%", "%inbox%", "%enviados%"])
    if not include_legacy_email_sources:
        canon = sql_predicate_contacto_gmail_source()
        where_parts.append(f"({canon})")
    if since_days is not None:
        where_parts.append("date_iso >= datetime('now', ?)")
        params.append(f"-{since_days} days")
    where = "WHERE " + " AND ".join(where_parts)
    conn.row_factory = sqlite3.Row
    return conn.execute(
        f"""
        SELECT id, source_file, folder, message_id, subject, sender, recipients, date_iso,
               COALESCE(top_reply_clean, body_text_clean, full_body_clean, '') AS body
        FROM emails
        {where}
        ORDER BY date_iso
        """,
        params,
    ).fetchall()


def build_events(rows: list[sqlite3.Row], gmail_user: str) -> tuple[list[MessageEvent], dict[str, Any]]:
    mailbox = gmail_user.lower()
    mailbox_domain = domain_of(mailbox) or ""
    events: list[MessageEvent] = []

    total_sent = 0
    total_received = 0
    unique_outbound: set[str] = set()
    unique_inbound: set[str] = set()
    out_domains: set[str] = set()
    in_domains: set[str] = set()
    min_dt: datetime | None = None
    max_dt: datetime | None = None
    latest_sent: datetime | None = None
    latest_inbox: datetime | None = None

    for row in rows:
        sender_email = (emails_in(row["sender"] or "") or [""])[0]
        recipients = set(emails_in(row["recipients"] or ""))
        folder = (row["folder"] or "").lower()
        date_iso = row["date_iso"] or ""
        dt = parse_date(date_iso)
        if dt:
            min_dt = dt if min_dt is None else min(min_dt, dt)
            max_dt = dt if max_dt is None else max(max_dt, dt)

        is_sent = sender_email == mailbox
        if not is_sent and mailbox in recipients:
            is_received = True
        else:
            is_received = False

        if is_sent:
            counterparty_list = sorted(
                e for e in recipients if e != mailbox and domain_of(e) not in {mailbox_domain, "origenlab.cl"}
            )
            if not counterparty_list:
                continue
            for cp in counterparty_list:
                cpd = domain_of(cp) or ""
                total_sent += 1
                unique_outbound.add(cp)
                if cpd:
                    out_domains.add(cpd)
                if dt and (latest_sent is None or dt > latest_sent):
                    latest_sent = dt
                events.append(
                    MessageEvent(
                        id=int(row["id"]),
                        date_iso=date_iso,
                        dt=dt,
                        direction="outbound",
                        folder=folder,
                        subject=decode_subject(row["subject"] or ""),
                        sender_email=sender_email,
                        counterparty_email=cp,
                        counterparty_domain=cpd,
                        body=row["body"] or "",
                        source_file=row["source_file"] or "",
                    )
                )
        elif is_received:
            cpd = domain_of(sender_email) or ""
            total_received += 1
            unique_inbound.add(sender_email)
            if cpd:
                in_domains.add(cpd)
            if dt and (latest_inbox is None or dt > latest_inbox):
                latest_inbox = dt
            events.append(
                MessageEvent(
                    id=int(row["id"]),
                    date_iso=date_iso,
                    dt=dt,
                    direction="inbound",
                    folder=folder,
                    subject=decode_subject(row["subject"] or ""),
                    sender_email=sender_email,
                    counterparty_email=sender_email,
                    counterparty_domain=cpd,
                    body=row["body"] or "",
                    source_file=row["source_file"] or "",
                )
            )

    summary = {
        "total_archived": len(rows),
        "total_sent": total_sent,
        "total_received": total_received,
        "unique_outbound_recipients": len(unique_outbound),
        "unique_inbound_senders": len(unique_inbound),
        "unique_outbound_domains": len(out_domains),
        "unique_inbound_domains": len(in_domains),
        "date_min": min_dt.isoformat() if min_dt else "",
        "date_max": max_dt.isoformat() if max_dt else "",
        "latest_sent": latest_sent.isoformat() if latest_sent else "",
        "latest_inbox": latest_inbox.isoformat() if latest_inbox else "",
    }
    return events, summary


def load_lookup_maps(conn: sqlite3.Connection) -> tuple[dict[str, sqlite3.Row], dict[str, sqlite3.Row], dict[str, sqlite3.Row]]:
    conn.row_factory = sqlite3.Row
    c_map = {r["email"].lower(): r for r in conn.execute("SELECT * FROM contact_master").fetchall() if r["email"]}
    o_map = {r["domain"].lower(): r for r in conn.execute("SELECT * FROM organization_master").fetchall() if r["domain"]}
    l_map = {
        r["email_norm"].lower(): r
        for r in conn.execute("SELECT * FROM lead_master WHERE email_norm IS NOT NULL AND length(trim(email_norm)) > 0").fetchall()
    }
    return c_map, o_map, l_map


def thread_key(ev: MessageEvent) -> str:
    subj = normalize_subject(ev.subject)
    if subj:
        return f"{ev.counterparty_email}|{subj}"
    return f"{ev.counterparty_email}|(no-subject)"


def classify_thread(
    messages: list[MessageEvent],
    contact_row: sqlite3.Row | None,
    org_row: sqlite3.Row | None,
    lead_row: sqlite3.Row | None,
) -> tuple[str, str, float]:
    text_blob = " ".join([(m.subject + " " + m.body) for m in messages]).lower()
    only_inbound = all(m.direction == "inbound" for m in messages)
    has_inbound = any(m.direction == "inbound" for m in messages)
    has_outbound = any(m.direction == "outbound" for m in messages)
    quote_count = int((contact_row["quote_email_count"] if contact_row else 0) or 0)
    invoice_count = int((contact_row["invoice_email_count"] if contact_row else 0) or 0)
    purchase_count = int((contact_row["purchase_email_count"] if contact_row else 0) or 0)
    org_type = (org_row["organization_type_guess"] if org_row else "") or ""

    cp_email = messages[0].counterparty_email if messages else ""
    cp_domain = messages[0].counterparty_domain if messages else ""
    if is_noncommercial_contact(cp_email, cp_domain):
        return "admin_noise", "Internal/non-commercial automated contact.", 0.98
    if NOISE_RE.search(text_blob):
        return "admin_noise", "Detected auto/system/noise patterns.", 0.95
    if SUPPLIER_RE.search(text_blob) and invoice_count + purchase_count > quote_count:
        return "supplier_or_partner", "Supplier/logistics pattern dominates.", 0.85
    if HOT_RE.search(text_blob) and has_inbound:
        if has_outbound and invoice_count == 0:
            return "hot_opportunity", "Inbound asks for quote/price/availability.", 0.86
        return "warm_opportunity", "Inbound interest with commercial intent.", 0.76
    if WARM_RE.search(text_blob) and has_inbound:
        if has_outbound:
            return "warm_opportunity", "Positive inbound response and active exchange.", 0.72
        return "needs_follow_up", "Inbound response without outbound closure.", 0.7
    if only_inbound and has_inbound:
        return "needs_follow_up", "Inbound-first thread needs qualification/response.", 0.68
    if quote_count > 0 and has_outbound:
        return "quoted_or_info_sent", "Quote/info language present and outbound sent.", 0.73
    if org_type == "consumer_email" and has_inbound and not has_outbound:
        return "unknown", "Personal mailbox with limited context.", 0.45
    return "unknown", "Insufficient evidence to classify confidently.", 0.4


def extract_need_tags(text: str) -> list[str]:
    out: list[str] = []
    for need, pats in NEED_PATTERNS.items():
        if any(re.search(pat, text, re.IGNORECASE) for pat in pats):
            out.append(need)
    return out


def iso_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def days_since(dt: datetime | None) -> int | None:
    if dt is None:
        return None
    return int((datetime.now(UTC) - dt.astimezone(UTC)).days)


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        for row in rows:
            w.writerow({c: row.get(c, "") for c in columns})


def build_conversation_intelligence_export(
    conn: sqlite3.Connection,
    *,
    db_path: Path,
    gmail_user: str,
    since_days: int | None,
    include_legacy_email_sources: bool,
    include_noise: bool,
) -> ConversationIntelligenceBuildResult:
    """Build conversation intelligence rows and summary (read-only SQLite)."""
    rows = fetch_rows(
        conn,
        since_days,
        gmail_user,
        include_legacy_email_sources=include_legacy_email_sources,
    )
    events, overall = build_events(rows, gmail_user.lower())
    c_map, o_map, l_map = load_lookup_maps(conn)

    by_thread: dict[str, list[MessageEvent]] = defaultdict(list)
    for ev in events:
        by_thread[thread_key(ev)].append(ev)

    real_conversations: list[dict[str, Any]] = []
    follow_ups: list[dict[str, Any]] = []
    opportunities: list[dict[str, Any]] = []
    noise_rows: list[dict[str, Any]] = []
    replied_contacts: set[str] = set()
    replied_domains: set[str] = set()
    contacted = {ev.counterparty_email for ev in events if ev.direction == "outbound"}
    top_domain_replies = Counter()
    status_counts = Counter()
    need_counter = Counter()
    need_examples: dict[str, set[str]] = defaultdict(set)
    inbound_first_rows: list[dict[str, Any]] = []

    for key, msgs in by_thread.items():
        msgs = sorted(msgs, key=lambda m: (m.dt or datetime.min.replace(tzinfo=UTC), m.id))
        cp_email = msgs[0].counterparty_email
        cp_domain = msgs[0].counterparty_domain
        c_row = c_map.get(cp_email)
        o_row = o_map.get(cp_domain)
        l_row = l_map.get(cp_email)
        sent_count = sum(1 for m in msgs if m.direction == "outbound")
        recv_count = sum(1 for m in msgs if m.direction == "inbound")
        first_out = next((m.dt for m in msgs if m.direction == "outbound"), None)
        first_in = next((m.dt for m in msgs if m.direction == "inbound"), None)
        last_dt = msgs[-1].dt
        org_name = (
            (o_row["organization_name_guess"] if o_row else None)
            or (c_row["organization_name_guess"] if c_row else None)
            or (l_row["org_name"] if l_row else None)
            or cp_domain
        )
        contact_name = (c_row["contact_name_best"] if c_row else None) or (l_row["contact_name"] if l_row else "")
        sector = (o_row["organization_type_guess"] if o_row else None) or (l_row["organization_type_guess"] if l_row else "")
        region = (l_row["region"] if l_row else "") or ""
        city = (l_row["city"] if l_row else "") or ""
        merged_text = " ".join((m.subject + " " + m.body) for m in msgs)
        needs = extract_need_tags(merged_text)
        status, status_reason, confidence = classify_thread(msgs, c_row, o_row, l_row)
        status_counts[status] += 1
        if recv_count > 0 and sent_count > 0:
            replied_contacts.add(cp_email)
            if cp_domain:
                replied_domains.add(cp_domain)
                top_domain_replies[cp_domain] += 1
        if first_in and (first_out is None or first_in < first_out):
            inbound_first_rows.append(
                {
                    "organization": org_name,
                    "contact_email": cp_email,
                    "classification": status,
                    "requested": "; ".join(needs[:4]) or decode_subject(msgs[0].subject),
                    "recommended_next_action": "Calificar necesidad y responder con siguiente paso comercial.",
                }
            )

        summary = (
            f"{decode_subject(msgs[-1].subject)[:90]} | {status_reason}"
            if msgs
            else status_reason
        )
        next_action = "Enviar seguimiento comercial en 48h."
        if status == "hot_opportunity":
            next_action = "Prioridad alta: enviar cotizacion/precio y proponer llamada."
        elif status == "warm_opportunity":
            next_action = "Enviar informacion tecnica y confirmar requerimiento."
        elif status == "needs_follow_up":
            next_action = "Responder hilo pendiente y cerrar siguiente paso."
        elif status in {"supplier_or_partner", "admin_noise"}:
            next_action = "Excluir del pipeline comercial de prospectos."

        row = {
            "organization": org_name or "",
            "domain": cp_domain or "",
            "contact_email": cp_email,
            "contact_name": contact_name or "",
            "sector": sector or "",
            "region": region,
            "city": city,
            "first_outbound_date": first_out.isoformat() if first_out else "",
            "first_inbound_date": first_in.isoformat() if first_in else "",
            "last_interaction_date": last_dt.isoformat() if last_dt else "",
            "sent_count": sent_count,
            "received_count": recv_count,
            "status": status,
            "product_or_need": "; ".join(needs) if needs else "",
            "summary": summary,
            "recommended_next_action": next_action,
            "confidence": round(confidence, 2),
        }

        if status in {"admin_noise", "supplier_or_partner"}:
            noise_rows.append(
                {
                    "category": status,
                    "organization_or_sender": org_name or cp_email,
                    "email": cp_email,
                    "domain": cp_domain,
                    "last_date": row["last_interaction_date"],
                    "summary": summary,
                    "reason_classified_as_noise_or_supplier": status_reason,
                }
            )
            if not include_noise:
                continue

        if status in {
            "hot_opportunity",
            "warm_opportunity",
            "nurture",
            "needs_follow_up",
            "quoted_or_info_sent",
            "unknown",
        }:
            real_conversations.append(row)
            priority = "high" if status == "hot_opportunity" else ("medium" if status in {"warm_opportunity", "needs_follow_up"} else "low")
            opportunities.append(
                {
                    "priority": priority,
                    "organization": row["organization"],
                    "contact_email": row["contact_email"],
                    "contact_name": row["contact_name"],
                    "sector": row["sector"],
                    "region": row["region"],
                    "city": row["city"],
                    "product_or_need": row["product_or_need"],
                    "status": row["status"],
                    "last_interaction_date": row["last_interaction_date"],
                    "summary": row["summary"],
                    "recommended_next_action": row["recommended_next_action"],
                    "confidence": row["confidence"],
                }
            )
            if (
                status in {"needs_follow_up", "hot_opportunity", "warm_opportunity"}
                and recv_count > 0
                and not is_noncommercial_contact(cp_email, cp_domain)
            ):
                last_in = max((m.dt for m in msgs if m.direction == "inbound"), default=None)
                last_out = max((m.dt for m in msgs if m.direction == "outbound"), default=None)
                if last_in and (last_out is None or last_in > last_out):
                    follow_ups.append(
                        {
                            "priority": priority,
                            "organization": row["organization"],
                            "contact_email": row["contact_email"],
                            "contact_name": row["contact_name"],
                            "last_inbound_date": last_in.isoformat(),
                            "last_outbound_date": last_out.isoformat() if last_out else "",
                            "days_since_last_touch": days_since(last_in),
                            "product_or_need": row["product_or_need"],
                            "why_follow_up_needed": "Cliente/prospecto respondio y no hay cierre claro posterior.",
                            "suggested_follow_up_message": (
                                "Hola, gracias por tu mensaje. Quedamos atentos para avanzar con la cotizacion/informacion solicitada. "
                                "Si te parece, hoy mismo te enviamos propuesta con precio, disponibilidad y plazo de entrega."
                            ),
                            "confidence": row["confidence"],
                        }
                    )

        for need in needs:
            need_counter[need] += 1
            if org_name:
                need_examples[need].add(org_name)

    replied_email_rate = (len(replied_contacts) / len(contacted) * 100.0) if contacted else 0.0
    replied_domain_rate = (len(replied_domains) / overall["unique_outbound_domains"] * 100.0) if overall["unique_outbound_domains"] else 0.0
    top_replied = top_domain_replies.most_common(15)

    latest_mail_dt = max(parse_date(overall["latest_sent"]) or datetime.min.replace(tzinfo=UTC), parse_date(overall["latest_inbox"]) or datetime.min.replace(tzinfo=UTC))
    days_stale = days_since(latest_mail_dt)
    stale_note = (
        "Gmail ingest appears stale; run ingest commands before relying on newest activity."
        if days_stale is not None and days_stale > 7
        else "Gmail ingest freshness appears acceptable for this analysis window."
    )

    need_lines = []
    for need, count in need_counter.most_common(20):
        examples = ", ".join(sorted(need_examples[need])[:3])
        demand_hint = "supplier_noise" if need in {"reactivos"} and count < 2 else "buyer_demand"
        need_lines.append(f"- {need}: {count} conversaciones | ejemplos: {examples} | {demand_hint}")

    top_opps = [r for r in opportunities if r["priority"] in {"high", "medium"}][:15]
    top_follow_ups = sorted(follow_ups, key=lambda r: (-(r["days_since_last_touch"] or 0), r["priority"]))[:15]

    report_md = f"""# Email Conversation Intelligence Report

Generated at: {iso_now()}
Mailbox analyzed: {gmail_user}
DB: {db_path}

## Executive Summary

- Sent emails from mailbox: {overall["total_sent"]}
- Received emails to mailbox: {overall["total_received"]}
- Unique contacted emails: {len(contacted)}
- Unique contacts that replied: {len(replied_contacts)}
- Estimated reply rate by email: {replied_email_rate:.2f}%
- Estimated reply rate by domain: {replied_domain_rate:.2f}%
- Real prospect/client conversation threads: {len(real_conversations)}
- Hot opportunities: {status_counts["hot_opportunity"]}
- Warm opportunities: {status_counts["warm_opportunity"]}
- Needs follow-up: {len(follow_ups)}

## Overall Email Volume

- Total archived emails scanned: {overall["total_archived"]}
- Total sent emails from {gmail_user}: {overall["total_sent"]}
- Total received emails to {gmail_user}: {overall["total_received"]}
- Unique outbound recipient emails: {overall["unique_outbound_recipients"]}
- Unique inbound sender emails: {overall["unique_inbound_senders"]}
- Unique domains contacted: {overall["unique_outbound_domains"]}
- Unique domains that replied: {len(replied_domains)}
- Date range in archive slice: {overall["date_min"]} -> {overall["date_max"]}
- Latest sent date: {overall["latest_sent"]}
- Latest inbox date: {overall["latest_inbox"]}

## Replies and Response Rate

- Unique contacted emails: {len(contacted)}
- Unique contacted emails that replied: {len(replied_contacts)}
- Unique contacted domains that replied: {len(replied_domains)}
- Reply rate by email: {replied_email_rate:.2f}%
- Reply rate by domain/institution: {replied_domain_rate:.2f}%
- Top replied domains: {", ".join(f"{d} ({n})" for d, n in top_replied[:10])}

## Conversation Classification Counts

- hot_opportunity: {status_counts["hot_opportunity"]}
- warm_opportunity: {status_counts["warm_opportunity"]}
- nurture: {status_counts["nurture"]}
- needs_follow_up: {status_counts["needs_follow_up"]}
- quoted_or_info_sent: {status_counts["quoted_or_info_sent"]}
- supplier_or_partner: {status_counts["supplier_or_partner"]}
- admin_noise: {status_counts["admin_noise"]}
- unknown: {status_counts["unknown"]}

## Products and Needs Mentioned

{chr(10).join(need_lines) if need_lines else "- No clear product/need mentions found in classified threads."}

## Inbound-First Conversations

{chr(10).join(f"- {r['organization']} ({r['contact_email']}): {r['requested']} | class={r['classification']}" for r in inbound_first_rows[:20]) if inbound_first_rows else "- None detected."}

## Top Commercial Opportunities

{chr(10).join(f"- [{r['priority']}] {r['organization']} <{r['contact_email']}> | {r['status']} | {r['product_or_need']} | {r['summary']}" for r in top_opps) if top_opps else "- None identified with current heuristics."}

## Follow-up Needed

{chr(10).join(f"- [{r['priority']}] {r['organization']} <{r['contact_email']}> | {r['days_since_last_touch']} days | {r['product_or_need']}" for r in top_follow_ups) if top_follow_ups else "- No pending follow-up threads detected."}

## Noise and Supplier Summary

- Supplier/partner threads: {status_counts["supplier_or_partner"]}
- Admin/noise threads: {status_counts["admin_noise"]}
- Total rows exported to noise summary: {len(noise_rows)}

## Limitations

- Body text availability: uses `top_reply_clean` fallback to `body_text_clean`/`full_body_clean`; quality varies by message.
- Thread reconstruction: subject + counterparty heuristic; forward/subject drift can split or merge threads.
- Reply matching: conservative and heuristic-based; ambiguous cases default to `unknown`.
- Organization mapping confidence drops for free-mail domains.
- Gmail ingest freshness: {stale_note}
- If stale, run:
  - `uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --gmail-user "{gmail_user}" --folder "INBOX" --since-days 30`
  - `uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --gmail-user "{gmail_user}" --folder "[Gmail]/Enviados" --since-days 30`
  - `uv run python scripts/ingest/05_workspace_gmail_imap_to_sqlite.py --gmail-user "{gmail_user}" --folder "[Gmail]/Sent Mail" --since-days 30`
"""

    summary_json = {
        "overall": overall,
        "status_counts": dict(status_counts),
        "reply_rate_email_pct": round(replied_email_rate, 2),
        "reply_rate_domain_pct": round(replied_domain_rate, 2),
        "real_conversations": len(real_conversations),
        "hot_opportunities": status_counts["hot_opportunity"],
        "warm_opportunities": status_counts["warm_opportunity"],
        "follow_up_needed": len(follow_ups),
        "top_replied_domains": top_replied[:25],
        "paths": {},
    }
    return ConversationIntelligenceBuildResult(
        summary_json=summary_json,
        report_md=report_md,
        real_conversations=real_conversations,
        follow_ups=follow_ups,
        opportunities=opportunities,
        noise_rows=noise_rows,
    )


def write_conversation_intelligence_outputs(
    out_dir: Path,
    result: ConversationIntelligenceBuildResult,
) -> None:
    """Write CSV artifacts and markdown report under ``out_dir``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    write_csv(out_dir / "real_client_conversations.csv", result.real_conversations, REAL_CLIENT_CONVERSATION_COLUMNS)
    write_csv(
        out_dir / "follow_up_needed.csv",
        sorted(result.follow_ups, key=lambda r: (r["priority"], -(r["days_since_last_touch"] or 0))),
        FOLLOW_UP_COLUMNS,
    )
    write_csv(
        out_dir / "commercial_opportunities.csv",
        sorted(result.opportunities, key=lambda r: (r["priority"], r["status"]), reverse=False),
        COMMERCIAL_OPPORTUNITIES_COLUMNS,
    )
    write_csv(out_dir / "noise_and_supplier_conversations.csv", result.noise_rows, NOISE_SUPPLIER_COLUMNS)
    (out_dir / REPORT_FILENAME).write_text(result.report_md, encoding="utf-8")
    result.summary_json["paths"] = {
        "report_md": str(out_dir / REPORT_FILENAME),
        "real_client_conversations_csv": str(out_dir / "real_client_conversations.csv"),
        "follow_up_needed_csv": str(out_dir / "follow_up_needed.csv"),
        "commercial_opportunities_csv": str(out_dir / "commercial_opportunities.csv"),
        "noise_and_supplier_conversations_csv": str(out_dir / "noise_and_supplier_conversations.csv"),
    }


def print_conversation_intelligence_summary(summary_json: dict[str, Any]) -> None:
    print(json.dumps(summary_json, ensure_ascii=False, indent=2))
