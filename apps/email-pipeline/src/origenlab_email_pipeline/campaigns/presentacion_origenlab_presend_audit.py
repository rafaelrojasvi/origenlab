"""Pre-send audit for Presentación OrigenLab Batch 1 (read-only, no sends)."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.business_mart import domain_of
from origenlab_email_pipeline.candidate_export_gate import normalize_export_email
from origenlab_email_pipeline.campaigns.presentacion_origenlab_campaign import (
    check_presentacion_hard_block,
    is_presentacion_hold_active_case,
    load_cyberday_sent_emails,
)
from origenlab_email_pipeline.campaigns.presentacion_origenlab_quality_types import (
    BATCH_CSV_FIELDS,
    CLASS_PRESENTATION,
    PresentacionBatchRow,
)
from origenlab_email_pipeline.campaigns.presentacion_origenlab_templates import (
    PRESENTACION_BATCH1_SUBJECT,
    template_presentacion_batch1_es,
    _greeting,
)
from origenlab_email_pipeline.leads.contacted_universe_audit import (
    build_contacted_universe_context,
)
from origenlab_email_pipeline.campaigns.presentacion_origenlab_quality import (
    _UNIVERSITY_BULK_DOMAINS,
    _is_low_quality_contact,
    _presentation_fit_score,
)
from origenlab_email_pipeline.leads.new_customer_research import load_exclusion_lists

INPUT_BATCH1 = "presentacion_batch1_send_now_25.csv"
OUTPUT_FINAL = "presentacion_batch1_final_send_25.csv"
OUTPUT_DRY_RUN = "presentacion_batch1_dry_run_preview.csv"
OUTPUT_AUDIT_REPORT = "presentacion_batch1_presend_audit.json"
OUTPUT_AUDIT_MD = "presentacion_batch1_presend_audit.md"

FINAL_CSV_FIELDS: tuple[str, ...] = BATCH_CSV_FIELDS + (
    "audit_status",
    "audit_notes",
    "greeting",
)

DRY_RUN_FIELDS: tuple[str, ...] = (
    "email",
    "organization",
    "contact_name",
    "greeting",
    "subject",
    "reason",
)

# Dominios/organizaciones con señal de distribuidor/revendedor — revisión manual en audit.
_RESELLER_DOMAIN_MARKERS: frozenset[str] = frozenset(
    {
        "scientificlab.cl",  # distribuidor equipamiento lab (no lab end-user)
        "redlab.cl",  # red de laboratorios / servicios — perfil ambiguo
    }
)
_RESELLER_ORG_RE = re.compile(
    r"distribuidor|importador|reventa|reseller|dealer|representante comercial|"
    r"venta de equipos|equipos cient[ií]ficos",
    re.I,
)
_UNIVERSITY_SUBDOMAIN_RE = re.compile(
    r"\.(uchile|udec|uc|puc|usach|uv|utalca|ubiobio|userena|ufro|usm|ucn|pucv|uach|unach)\.cl$"
)


@dataclass
class AuditFinding:
    email: str
    severity: str  # fail | warn | ok
    code: str
    detail: str


@dataclass
class PresendAuditResult:
    approved: list[PresentacionBatchRow] = field(default_factory=list)
    removed: list[dict[str, str]] = field(default_factory=list)
    replaced: list[dict[str, str]] = field(default_factory=list)
    warnings: list[AuditFinding] = field(default_factory=list)
    findings: list[AuditFinding] = field(default_factory=list)
    dry_run: list[dict[str, str]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


def _load_batch_rows(path: Path) -> list[PresentacionBatchRow]:
    if not path.is_file():
        return []
    out: list[PresentacionBatchRow] = []
    with path.open(encoding="utf-8", newline="") as f:
        for raw in csv.DictReader(f):
            out.append(
                PresentacionBatchRow(
                    email=raw.get("email") or "",
                    domain=raw.get("domain") or "",
                    organization=raw.get("organization") or "",
                    contact_name=raw.get("contact_name") or "",
                    classification=raw.get("classification") or "",
                    sector_guess=raw.get("sector_guess") or "",
                    reason_for_inclusion=raw.get("reason_for_inclusion") or "",
                    history_note=raw.get("history_note") or "",
                    product_angle=raw.get("product_angle") or "",
                    suggested_subject=raw.get("suggested_subject") or "",
                    suggested_message=raw.get("suggested_message") or "",
                    recommended_action=raw.get("recommended_action") or "",
                    priority_score=float(raw.get("priority_score") or 0),
                    dedupe_key=raw.get("dedupe_key") or "",
                    primary_or_secondary=raw.get("primary_or_secondary") or "primary",
                )
            )
    return out


def _batch_row_from_do_not_send(raw: dict[str, str]) -> PresentacionBatchRow | None:
    """Reconstruct a presentation candidate from do_not_send row metadata if possible."""
    return None


def _replacement_is_eligible(row: PresentacionBatchRow) -> tuple[bool, str]:
    em = (row.email or "").lower()
    dom = (row.domain or domain_of(em) or "").lower()
    local = em.split("@")[0] if "@" in em else em
    if not dom.endswith(".cl"):
        return False, "not_chile_domain"
    if dom in _UNIVERSITY_BULK_DOMAINS or _UNIVERSITY_SUBDOMAIN_RE.search(dom):
        return False, "university_domain"
    if dom in _RESELLER_DOMAIN_MARKERS:
        return False, "reseller_domain"
    low, reason = _is_low_quality_contact(em, row.organization)
    if low:
        return False, reason
    if re.match(r"^(callcenter|servicioalcliente|servicios|info@hospital)", local, re.I):
        return False, "admin_service_mailbox"
    score = _presentation_fit_score(
        domain=dom,
        organization=row.organization,
        email=em,
        subject=row.history_note,
        history=row.history_note,
        base_score=row.priority_score,
    )
    if score < 35:
        return False, f"low_presentation_fit_{score:.0f}"
    return True, "ok"


def _load_replacement_candidates(
    out_dir: Path,
    *,
    excluded_domains: frozenset[str],
    excluded_emails: frozenset[str],
    same_domain_domains: frozenset[str],
) -> list[PresentacionBatchRow]:
    """Next-best presentation candidates from do_not_send (below_batch1_cutoff)."""
    path = out_dir / "presentacion_do_not_send_reasons.csv"
    if not path.is_file():
        return []
    # Reload full presentation pool rows from send_now that were cutoff
    send_now_path = out_dir / "presentacion_origenlab_send_now_review.csv"
    if not send_now_path.is_file():
        return []
    cutoff_emails: set[str] = set()
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            if row.get("reason_code") != "below_batch1_cutoff":
                continue
            if row.get("classification_attempted") != CLASS_PRESENTATION:
                continue
            em = normalize_export_email(row.get("email") or "") or ""
            if em and em not in excluded_emails:
                cutoff_emails.add(em)

    candidates: list[PresentacionBatchRow] = []
    with send_now_path.open(encoding="utf-8", newline="") as f:
        for raw in csv.DictReader(f):
            em = normalize_export_email(raw.get("email") or "") or ""
            if em not in cutoff_emails:
                continue
            dom = domain_of(em) or ""
            if dom in excluded_domains or dom in same_domain_domains:
                continue
            subj, body = template_presentacion_batch1_es(
                contact_name=raw.get("contact_name") or ""
            )
            candidates.append(
                PresentacionBatchRow(
                    email=em,
                    domain=dom,
                    organization=raw.get("organization") or "",
                    contact_name=raw.get("contact_name") or "",
                    classification=CLASS_PRESENTATION,
                    sector_guess="lab_privado_industria",
                    reason_for_inclusion="Reemplazo audit — presentación empresa",
                    history_note=raw.get("history_note") or "",
                    product_angle=raw.get("product_angle") or "",
                    suggested_subject=subj,
                    suggested_message=body,
                    recommended_action="operator_review_before_send",
                    priority_score=float(raw.get("priority_score") or 0),
                    dedupe_key=dom.rsplit(".", 1)[0] if dom.count(".") else dom,
                    primary_or_secondary="primary",
                )
            )
    filtered: list[PresentacionBatchRow] = []
    for cand in candidates:
        ok, _ = _replacement_is_eligible(cand)
        if ok:
            filtered.append(cand)
    filtered.sort(key=lambda r: (-r.priority_score, r.email))
    return filtered


def _spot_check_reseller(row: PresentacionBatchRow) -> AuditFinding | None:
    dom = (row.domain or domain_of(row.email) or "").lower()
    org = row.organization or ""
    if dom in _RESELLER_DOMAIN_MARKERS:
        return AuditFinding(
            email=row.email,
            severity="fail",
            code="likely_distributor_reseller",
            detail=f"Dominio {dom} — perfil distribuidor/revendedor, no lab comprador",
        )
    if _RESELLER_ORG_RE.search(org):
        return AuditFinding(
            email=row.email,
            severity="fail",
            code="likely_distributor_reseller",
            detail=f"Organización sugiere distribuidor: {org}",
        )
    if _UNIVERSITY_SUBDOMAIN_RE.search(dom):
        return AuditFinding(
            email=row.email,
            severity="fail",
            code="university_subdomain",
            detail=f"Subdominio universitario {dom} — fuera de perfil batch presentación privada",
        )
    if dom.endswith(".gov.cl") and "laboratorio" not in row.email.lower():
        return AuditFinding(
            email=row.email,
            severity="warn",
            code="public_sector_review",
            detail=f"Sector público {dom} — revisar calidad del contacto",
        )
    return None


def audit_batch1_row(
    row: PresentacionBatchRow,
    *,
    gate_ctx: Any,
    excl: Any,
    cyberday_sent: frozenset[str],
    hold_emails: frozenset[str],
    same_domain_emails: frozenset[str],
    same_domain_domains: frozenset[str],
    batch2_emails: frozenset[str],
) -> list[AuditFinding]:
    findings: list[AuditFinding] = []
    em = normalize_export_email(row.email) or ""
    dom = (row.domain or domain_of(em) or "").lower()

    if not em or "@" not in em:
        findings.append(
            AuditFinding(em or row.email, "fail", "invalid_email", "Correo inválido")
        )
        return findings

    blocked, reason = check_presentacion_hard_block(
        em, row.organization, gate_ctx=gate_ctx, excl=excl, cyberday_sent=cyberday_sent
    )
    if blocked:
        findings.append(AuditFinding(em, "fail", reason, f"Bloqueo hard: {reason}"))

    if em in hold_emails:
        findings.append(
            AuditFinding(em, "fail", "hold_active_personalized", "En hold activo personalizado")
        )

    hold, hold_reason = is_presentacion_hold_active_case(
        em, organization=row.organization, domain=dom
    )
    if hold:
        findings.append(AuditFinding(em, "fail", "hold_active_case", hold_reason))

    if em in same_domain_emails:
        findings.append(
            AuditFinding(
                em,
                "fail",
                "same_domain_review_email",
                "Email en same-domain review — no auto-send",
            )
        )
    if dom in same_domain_domains:
        findings.append(
            AuditFinding(
                em,
                "fail",
                "same_domain_review_domain",
                f"Dominio {dom} en same-domain review (Phase 10D)",
            )
        )

    if em in batch2_emails:
        findings.append(
            AuditFinding(em, "fail", "in_batch2_followup", "Reservado para batch 2 follow-up")
        )

    reseller = _spot_check_reseller(row)
    if reseller:
        findings.append(reseller)

    if not findings:
        findings.append(AuditFinding(em, "ok", "approved", "Pasa validación pre-send"))
    return findings


def run_batch1_presend_audit(
    conn: sqlite3.Connection,
    out_dir: Path,
    *,
    gmail_user: str,
    sent_folders: tuple[str, ...],
) -> PresendAuditResult:
    out_dir = out_dir.resolve()
    batch1 = _load_batch_rows(out_dir / INPUT_BATCH1)

    cyberday_sent = load_cyberday_sent_emails(out_dir / "cyber_production_send_log.json")
    excl = load_exclusion_lists(out_dir)
    universe_ctx, _, _ = build_contacted_universe_context(
        conn, gmail_user=gmail_user, sent_folders=sent_folders
    )
    gate_ctx = universe_ctx.gate

    hold_emails: set[str] = set()
    hold_path = out_dir / "presentacion_hold_active_personalized.csv"
    if hold_path.is_file():
        with hold_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                em = normalize_export_email(row.get("email") or "") or ""
                if em:
                    hold_emails.add(em)

    same_domain_emails: set[str] = set()
    same_domain_domains: set[str] = set()
    sd_path = out_dir / "presentacion_same_domain_review_curated.csv"
    if sd_path.is_file():
        with sd_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                em = normalize_export_email(row.get("email") or "") or ""
                dom = (row.get("domain") or "").lower()
                if em:
                    same_domain_emails.add(em)
                if dom:
                    same_domain_domains.add(dom)

    batch2_emails: set[str] = set()
    b2_path = out_dir / "presentacion_batch2_followup_old_25.csv"
    if b2_path.is_file():
        with b2_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                em = normalize_export_email(row.get("email") or "") or ""
                if em:
                    batch2_emails.add(em)

    approved: list[PresentacionBatchRow] = []
    removed: list[dict[str, str]] = []
    all_findings: list[AuditFinding] = []
    warnings: list[AuditFinding] = []
    used_domains: set[str] = set()

    for row in batch1:
        findings = audit_batch1_row(
            row,
            gate_ctx=gate_ctx,
            excl=excl,
            cyberday_sent=cyberday_sent,
            hold_emails=frozenset(hold_emails),
            same_domain_emails=frozenset(same_domain_emails),
            same_domain_domains=frozenset(same_domain_domains),
            batch2_emails=frozenset(batch2_emails),
        )
        all_findings.extend(findings)
        fails = [f for f in findings if f.severity == "fail"]
        warns = [f for f in findings if f.severity == "warn"]
        warnings.extend(warns)

        dom = (row.domain or domain_of(row.email) or "").lower()
        if dom in used_domains:
            fails.append(
                AuditFinding(
                    row.email,
                    "fail",
                    "duplicate_domain_in_batch",
                    f"Dominio duplicado en batch: {dom}",
                )
            )

        if fails:
            removed.append(
                {
                    "email": row.email,
                    "domain": dom,
                    "organization": row.organization,
                    "reason_codes": "; ".join(f.code for f in fails),
                    "reason_detail": "; ".join(f.detail for f in fails),
                }
            )
            continue

        used_domains.add(dom)
        subj, body = template_presentacion_batch1_es(contact_name=row.contact_name)
        approved.append(
            PresentacionBatchRow(
                email=row.email,
                domain=dom,
                organization=row.organization,
                contact_name=row.contact_name,
                classification=row.classification,
                sector_guess=row.sector_guess,
                reason_for_inclusion=row.reason_for_inclusion,
                history_note=row.history_note,
                product_angle=row.product_angle,
                suggested_subject=subj,
                suggested_message=body,
                recommended_action=row.recommended_action,
                priority_score=row.priority_score,
                dedupe_key=row.dedupe_key or dom,
                primary_or_secondary="primary",
            )
        )

    replaced: list[dict[str, str]] = []
    excluded_emails = frozenset(
        {r.email.lower() for r in approved}
        | {r["email"].lower() for r in removed}
        | hold_emails
        | batch2_emails
        | cyberday_sent
    )
    if len(approved) < 25:
        replacements = _load_replacement_candidates(
            out_dir,
            excluded_domains=frozenset(used_domains),
            excluded_emails=excluded_emails,
            same_domain_domains=frozenset(same_domain_domains),
        )
        for cand in replacements:
            if len(approved) >= 25:
                break
            dom = cand.domain or domain_of(cand.email) or ""
            if dom in used_domains:
                continue
            findings = audit_batch1_row(
                cand,
                gate_ctx=gate_ctx,
                excl=excl,
                cyberday_sent=cyberday_sent,
                hold_emails=frozenset(hold_emails),
                same_domain_emails=frozenset(same_domain_emails),
                same_domain_domains=frozenset(same_domain_domains),
                batch2_emails=frozenset(batch2_emails),
            )
            if any(f.severity == "fail" for f in findings):
                continue
            ok, why = _replacement_is_eligible(cand)
            if not ok:
                continue
            subj, body = template_presentacion_batch1_es(contact_name=cand.contact_name)
            approved.append(
                PresentacionBatchRow(
                    email=cand.email,
                    domain=dom,
                    organization=cand.organization,
                    contact_name=cand.contact_name,
                    classification=cand.classification,
                    sector_guess=cand.sector_guess,
                    reason_for_inclusion=cand.reason_for_inclusion,
                    history_note=cand.history_note,
                    product_angle=cand.product_angle,
                    suggested_subject=subj,
                    suggested_message=body,
                    recommended_action=cand.recommended_action,
                    priority_score=cand.priority_score,
                    dedupe_key=cand.dedupe_key,
                    primary_or_secondary="primary",
                )
            )
            used_domains.add(dom)
            replaced.append(
                {
                    "replacement_email": cand.email,
                    "replacement_domain": dom,
                    "replacement_organization": cand.organization,
                    "source": "below_batch1_cutoff",
                    "priority_score": str(cand.priority_score),
                }
            )

    dry_run: list[dict[str, str]] = []
    for row in approved[:25]:
        greeting = _greeting(row.contact_name)
        dry_run.append(
            {
                "email": row.email,
                "organization": row.organization,
                "contact_name": row.contact_name,
                "greeting": greeting,
                "subject": PRESENTACION_BATCH1_SUBJECT,
                "reason": row.reason_for_inclusion,
            }
        )

    approved = approved[:25]

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "presend_audit_read_only",
        "input_count": len(batch1),
        "approved_count": len(approved),
        "removed_count": len(removed),
        "replaced_count": len(replaced),
        "warnings_count": len(warnings),
        "removed": removed,
        "replaced": replaced,
        "warnings": [
            {"email": w.email, "code": w.code, "detail": w.detail} for w in warnings
        ],
        "approved_emails": [r.email for r in approved],
        "duplicate_domains_in_input": len(batch1) - len({r.domain for r in batch1}),
    }

    return PresendAuditResult(
        approved=approved,
        removed=removed,
        replaced=replaced,
        warnings=warnings,
        findings=all_findings,
        dry_run=dry_run,
        summary=summary,
    )


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fields))
        w.writeheader()
        for row in rows:
            if isinstance(row, dict):
                w.writerow({k: row.get(k, "") for k in fields})
            else:
                d = row.to_csv_dict()
                d["audit_status"] = "approved"
                d["audit_notes"] = ""
                d["greeting"] = _greeting(row.contact_name)
                w.writerow({k: d.get(k, "") for k in fields})


def _render_audit_md(result: PresendAuditResult) -> str:
    s = result.summary
    lines = [
        "# Pre-send audit — Presentación OrigenLab Batch 1",
        "",
        f"- **Generado:** {s.get('generated_at', '')}",
        "- **Modo:** solo lectura — sin envíos Gmail, sin outreach writes",
        "",
        f"- Input: **{s.get('input_count', 0)}** filas",
        f"- Aprobados final: **{s.get('approved_count', 0)}**",
        f"- Removidos: **{s.get('removed_count', 0)}**",
        f"- Reemplazos: **{s.get('replaced_count', 0)}**",
        "",
        "## Removidos",
        "",
    ]
    if result.removed:
        for r in result.removed:
            lines.append(
                f"- `{r['email']}` ({r.get('organization', '')}) — "
                f"**{r.get('reason_codes', '')}**: {r.get('reason_detail', '')}"
            )
    else:
        lines.append("- (ninguno)")
    lines.extend(["", "## Reemplazos", ""])
    if result.replaced:
        for r in result.replaced:
            lines.append(
                f"- `{r['replacement_email']}` — {r.get('replacement_organization', '')} "
                f"(score {r.get('priority_score', '')})"
            )
    else:
        lines.append("- (ninguno)")
    lines.extend(["", "## Advertencias (no bloquean)", ""])
    if result.warnings:
        for w in result.warnings:
            lines.append(f"- `{w.email}` — {w.code}: {w.detail}")
    else:
        lines.append("- (ninguna)")
    lines.extend(["", "## Aprobados final", ""])
    for i, em in enumerate(s.get("approved_emails") or [], start=1):
        lines.append(f"{i}. `{em}`")
    lines.append("")
    return "\n".join(lines)


def write_presend_audit_outputs(result: PresendAuditResult, out_dir: Path) -> dict[str, Path]:
    out_dir = out_dir.resolve()
    paths = {
        "final": out_dir / OUTPUT_FINAL,
        "dry_run": out_dir / OUTPUT_DRY_RUN,
        "report_json": out_dir / OUTPUT_AUDIT_REPORT,
        "report_md": out_dir / OUTPUT_AUDIT_MD,
    }
    _write_csv(paths["final"], FINAL_CSV_FIELDS, result.approved)
    _write_csv(paths["dry_run"], DRY_RUN_FIELDS, result.dry_run)
    paths["report_json"].write_text(
        json.dumps(result.summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    paths["report_md"].write_text(_render_audit_md(result), encoding="utf-8")
    return paths
