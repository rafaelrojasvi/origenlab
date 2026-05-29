"""Process DeepSearch prospect CSVs into safe review lists (Phase 10B)."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from origenlab_email_pipeline.business_mart import domain_of, emails_in
from origenlab_email_pipeline.candidate_export_gate import normalize_export_email
from origenlab_email_pipeline.marketing_export_context import DEFAULT_EXCLUDE_DOMAINS
from origenlab_email_pipeline.marketing_supplier_domains import is_supplier_email_domain

DEEPSEARCH_COLUMNS: tuple[str, ...] = (
    "organization_name",
    "contact_name",
    "email",
    "domain",
    "role_title",
    "sector",
    "region",
    "buyer_type",
    "likely_need",
    "product_angle",
    "evidence_url",
    "evidence_note",
    "source",
    "priority_score",
    "confidence",
    "recommended_message_angle",
    "risk_flags",
)

REVIEW_OUTPUT_FIELDS: tuple[str, ...] = (
    "organization_name",
    "contact_name",
    "email",
    "domain",
    "sector",
    "region",
    "buyer_type",
    "input_priority_score",
    "final_score",
    "classification",
    "spanish_message_angle",
    "product_angle",
    "evidence_url",
    "evidence_note",
    "source",
    "confidence",
    "risk_flags",
    "block_or_review_reason",
    "recommended_next_action",
)

BLOCKED_OUTPUT_FIELDS: tuple[str, ...] = (
    "organization_name",
    "contact_name",
    "email",
    "domain",
    "sector",
    "region",
    "buyer_type",
    "input_priority_score",
    "final_score",
    "classification",
    "spanish_message_angle",
    "product_angle",
    "evidence_url",
    "evidence_note",
    "source",
    "confidence",
    "block_reason",
    "risk_flags",
    "recommended_next_action",
)

# Classification labels (stable codes)
CLASS_ALREADY_CONTACTED = "already_contacted_block"
CLASS_BOUNCED = "bounced_block"
CLASS_SUPPRESSED = "suppressed_block"
CLASS_SUPPLIER_INTERNAL = "supplier_or_internal_block"
CLASS_SAME_DOMAIN = "same_domain_contacted_review"
CLASS_RESEARCH_ONLY = "research_only_contact_needed"
CLASS_PUBLIC_TENDER = "public_tender_review"
CLASS_NET_NEW = "net_new_safe_review"

_BLOCKED = frozenset(
    {
        CLASS_ALREADY_CONTACTED,
        CLASS_BOUNCED,
        CLASS_SUPPRESSED,
        CLASS_SUPPLIER_INTERNAL,
    }
)

_GENERIC_LOCALS = frozenset(
    {
        "info",
        "contacto",
        "contact",
        "atencion",
        "atencionalcliente",
        "comunicaciones",
        "ventas",
        "administracion",
        "recepcion",
    }
)

_PRODUCT_BOOST_KEYWORDS: tuple[tuple[str, int], ...] = (
    (r"centr[ií]fug", 4),
    (r"sonicador|ultra\s*turrax|homogeniz", 4),
    (r"balanza|balance", 3),
    (r"incubadora", 3),
    (r"reactor", 3),
    (r"sample\s*prep|preparaci[oó]n de muestra", 3),
)

_BUYER_BOOST: dict[str, int] = {
    "laboratorio_privado": 8,
    "laboratorio_alimentos": 8,
    "laboratorio_acuicola": 9,
    "laboratorio_agua": 7,
    "laboratorio_ambiental": 7,
    "centro_ensayos": 6,
    "centro_investigacion": 5,
    "instituto_investigacion": 5,
    "laboratorio_universitario": 4,
    "laboratorio_clinico_hospitalario": 5,
    "public_tender_universidad": 6,
    "public_tender_opportunity": 8,
    "qc_alimentos": 7,
    "qc_farmaceutico": 6,
}

_SPANISH_ANGLES: tuple[tuple[str, str], ...] = (
    (r"homogeniz|sonicador|ultra\s*turrax|preparaci[oó]n de muestra", "Preparación de muestras: homogeneizadores, sonicadores y centrífugas"),
    (r"balanza|balance|incubadora|control de calidad|qc", "Control de calidad: balanzas, incubadoras y equipos de laboratorio"),
    (r"agua|ambiental|h[ií]dric", "Equipos para laboratorio ambiental/aguas"),
    (r"acu[ií]cola|salm[oó]n|hidrobiol", "Equipos para laboratorio acuícola/salmones"),
    (r"licitaci[oó]n|mercado\s*p[uú]blico|tender", "Apoyo técnico para licitación pública"),
    (r"investigaci[oó]n|universidad|centro", "Equipamiento para centro de investigación"),
)


@dataclass(frozen=True)
class ExclusionLists:
    contacted_emails: frozenset[str]
    contacted_domains: frozenset[str]
    bounced_emails: frozenset[str]
    bounced_domains: frozenset[str]
    suppressed_emails: frozenset[str]
    supplier_domains: frozenset[str]
    internal_domains: frozenset[str]


@dataclass
class ProcessedProspect:
    row: dict[str, str]
    classification: str
    input_priority_score: int
    final_score: int
    spanish_message_angle: str
    block_or_review_reason: str
    recommended_next_action: str

    @property
    def is_blocked(self) -> bool:
        return self.classification in _BLOCKED

    def to_review_dict(self) -> dict[str, str]:
        r = self.row
        return {
            "organization_name": r.get("organization_name", ""),
            "contact_name": r.get("contact_name", ""),
            "email": r.get("email", ""),
            "domain": r.get("domain", ""),
            "sector": r.get("sector", ""),
            "region": r.get("region", ""),
            "buyer_type": r.get("buyer_type", ""),
            "input_priority_score": str(self.input_priority_score),
            "final_score": str(self.final_score),
            "classification": self.classification,
            "spanish_message_angle": self.spanish_message_angle,
            "product_angle": r.get("product_angle", ""),
            "evidence_url": r.get("evidence_url", ""),
            "evidence_note": r.get("evidence_note", ""),
            "source": r.get("source", ""),
            "confidence": r.get("confidence", ""),
            "risk_flags": r.get("risk_flags", ""),
            "block_or_review_reason": self.block_or_review_reason,
            "recommended_next_action": self.recommended_next_action,
        }

    def to_blocked_dict(self) -> dict[str, str]:
        r = self.row
        if self.classification == CLASS_ALREADY_CONTACTED:
            action = "No contactar: ya contactado"
        else:
            action = self.recommended_next_action
        return {
            "organization_name": r.get("organization_name", ""),
            "contact_name": r.get("contact_name", ""),
            "email": r.get("email", ""),
            "domain": r.get("domain", ""),
            "sector": r.get("sector", ""),
            "region": r.get("region", ""),
            "buyer_type": r.get("buyer_type", ""),
            "input_priority_score": str(self.input_priority_score),
            "final_score": "0",
            "classification": self.classification,
            "spanish_message_angle": self.spanish_message_angle,
            "product_angle": r.get("product_angle", ""),
            "evidence_url": r.get("evidence_url", ""),
            "evidence_note": r.get("evidence_note", ""),
            "source": r.get("source", ""),
            "confidence": r.get("confidence", ""),
            "block_reason": self.block_or_review_reason,
            "risk_flags": r.get("risk_flags", ""),
            "recommended_next_action": action,
        }


@dataclass
class ProcessResult:
    prospects: list[ProcessedProspect]
    summary: dict[str, Any]
    input_files: list[str] = field(default_factory=list)


def _norm_domain(raw: str | None) -> str:
    d = (raw or "").strip().lower()
    if d.startswith("@"):
        d = d[1:]
    return d


def _norm_email(raw: str | None) -> str | None:
    return normalize_export_email(raw or "")


def parse_risk_flags(raw: str | None) -> set[str]:
    if not raw:
        return set()
    parts = re.split(r"[;|,]", str(raw))
    return {p.strip().lower() for p in parts if p.strip()}


def _int_score(raw: str | None, default: int = 0) -> int:
    try:
        return int(float(str(raw or "").strip()))
    except ValueError:
        return default


def load_exclusion_lists(exclusion_dir: Path) -> ExclusionLists:
    """Load Phase 10A.1 CSV exclusion sets (read-only)."""
    exact_path = exclusion_dir / "contacted_exact_emails_for_exclusion.csv"
    domains_path = exclusion_dir / "contacted_domains_for_exclusion.csv"
    bounced_path = exclusion_dir / "bounced_emails_for_exclusion.csv"
    suppressed_path = exclusion_dir / "suppressed_contacts_for_exclusion.csv"

    contacted_emails: set[str] = set()
    if exact_path.is_file():
        with exact_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                em = _norm_email(row.get("normalized_email") or row.get("email"))
                if em:
                    contacted_emails.add(em)

    contacted_domains: set[str] = set()
    supplier_domains: set[str] = set()
    internal_domains: set[str] = set()
    if domains_path.is_file():
        with domains_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                dom = _norm_domain(row.get("domain"))
                if not dom:
                    continue
                sent = _int_score(row.get("sent_count"))
                status = (row.get("recommended_status") or "").strip().lower()
                if sent > 0 or status == "already_contacted":
                    contacted_domains.add(dom)
                if (row.get("supplier_bool") or "").lower() == "true":
                    supplier_domains.add(dom)
                if (row.get("internal_bool") or "").lower() == "true":
                    internal_domains.add(dom)
                if "supplier_domain" in (row.get("reason_codes") or ""):
                    supplier_domains.add(dom)

    bounced_emails: set[str] = set()
    bounced_domains: set[str] = set()
    if bounced_path.is_file():
        with bounced_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                em = _norm_email(row.get("normalized_email") or row.get("email"))
                if em:
                    bounced_emails.add(em)
                    d = domain_of(em)
                    if d:
                        bounced_domains.add(d)

    suppressed_emails: set[str] = set()
    if suppressed_path.is_file():
        with suppressed_path.open(encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                em = _norm_email(row.get("normalized_email") or row.get("email"))
                if em:
                    suppressed_emails.add(em)

    internal_domains |= {d.strip().lower() for d in DEFAULT_EXCLUDE_DOMAINS if d.strip()}

    return ExclusionLists(
        contacted_emails=frozenset(contacted_emails),
        contacted_domains=frozenset(contacted_domains),
        bounced_emails=frozenset(bounced_emails),
        bounced_domains=frozenset(bounced_domains),
        suppressed_emails=frozenset(suppressed_emails),
        supplier_domains=frozenset(supplier_domains),
        internal_domains=frozenset(internal_domains),
    )


def load_deepsearch_rows(input_dir: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Load all CSV files from input_dir matching DeepSearch schema."""
    rows: list[dict[str, str]] = []
    files_used: list[str] = []
    if not input_dir.is_dir():
        return rows, files_used
    for path in sorted(input_dir.glob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                continue
            fields = {c.strip() for c in reader.fieldnames if c}
            if "organization_name" not in fields:
                continue
            for raw in reader:
                row = {k: (raw.get(k) or "").strip() for k in DEEPSEARCH_COLUMNS}
                row["email"] = (_norm_email(row.get("email")) or "")
                row["domain"] = _norm_domain(row.get("domain") or domain_of(row.get("email") or ""))
                rows.append(row)
            files_used.append(str(path))
    return rows, files_used


def _is_public_tender(row: dict[str, str], flags: set[str]) -> bool:
    buyer = (row.get("buyer_type") or "").lower()
    if "public_tender" in buyer or buyer.startswith("public_tender"):
        return True
    if "mercado_publico" in (row.get("source") or "").lower():
        return True
    if "lead_status=public_tender" in " ".join(flags):
        return True
    url = (row.get("evidence_url") or "").lower()
    return "mercadopublico.cl" in url


def _is_generic_email(email: str) -> bool:
    if not email or "@" not in email:
        return False
    local = email.split("@", 1)[0].lower()
    return local in _GENERIC_LOCALS or local.startswith("info") or local.startswith("atencion")


def _has_named_contact(row: dict[str, str]) -> bool:
    name = (row.get("contact_name") or "").strip()
    return len(name) >= 3 and not name.lower().startswith("contacto")


def classify_prospect(row: dict[str, str], excl: ExclusionLists) -> tuple[str, str]:
    """Return (classification, reason_code)."""
    email = row.get("email") or ""
    domain = row.get("domain") or ""
    flags = parse_risk_flags(row.get("risk_flags"))

    if email and email in excl.contacted_emails:
        return CLASS_ALREADY_CONTACTED, "email_en_lista_contactados"

    if email and email in excl.bounced_emails:
        return CLASS_BOUNCED, "email_rebote"

    if domain and domain in excl.bounced_domains:
        return CLASS_BOUNCED, "dominio_con_rebotes"

    if email and email in excl.suppressed_emails:
        return CLASS_SUPPRESSED, "email_suprimido"

    if domain in excl.internal_domains:
        return CLASS_SUPPLIER_INTERNAL, "dominio_interno"

    if domain in excl.supplier_domains or (
        domain and is_supplier_email_domain(f"x@{domain}", excl.supplier_domains)
    ):
        return CLASS_SUPPLIER_INTERNAL, "dominio_proveedor"

    if "low_fit" in flags:
        return CLASS_SUPPLIER_INTERNAL, "low_fit"

    if _is_public_tender(row, flags):
        return CLASS_PUBLIC_TENDER, "licitacion_o_compra_publica"

    if not email:
        if "sin_email_publico" in flags or "validar_contacto_publico" in flags:
            return CLASS_RESEARCH_ONLY, "sin_email_publico"
        if _is_public_tender(row, flags):
            return CLASS_PUBLIC_TENDER, "licitacion_sin_email"
        return CLASS_RESEARCH_ONLY, "falta_email_directo"

    if domain and domain in excl.contacted_domains:
        if "same_organization_review" in flags or "dominio_en_historial_origenlab" in flags:
            return CLASS_SAME_DOMAIN, "mismo_dominio_ya_contactado"
        return CLASS_SAME_DOMAIN, "dominio_con_envios_previos"

    if "same_organization_review" in flags:
        return CLASS_SAME_DOMAIN, "revision_misma_organizacion"

    if "dominio_en_historial_origenlab" in flags:
        return CLASS_SAME_DOMAIN, "dominio_en_historial"

    return CLASS_NET_NEW, "prospecto_nuevo_seguro"


def spanish_message_angle(row: dict[str, str]) -> str:
    blob = " ".join(
        [
            row.get("product_angle") or "",
            row.get("likely_need") or "",
            row.get("buyer_type") or "",
            row.get("recommended_message_angle") or "",
        ]
    ).lower()
    for pattern, angle in _SPANISH_ANGLES:
        if re.search(pattern, blob, re.I):
            return angle
    return "Equipamiento para laboratorio con soporte técnico local OrigenLab"


def compute_final_score(
    row: dict[str, str],
    *,
    classification: str,
    input_score: int,
    flags: set[str],
) -> int:
    score = input_score
    buyer = (row.get("buyer_type") or "").lower()
    score += _BUYER_BOOST.get(buyer, 0)

    blob = " ".join(
        [row.get("product_angle") or "", row.get("likely_need") or "", row.get("sector") or ""]
    ).lower()
    for pattern, boost in _PRODUCT_BOOST_KEYWORDS:
        if re.search(pattern, blob, re.I):
            score += boost

    email = row.get("email") or ""
    if email:
        score += 5
    if _has_named_contact(row):
        score += 4
    if _is_public_tender(row, flags):
        score += 6
    if "mercadopublico" in (row.get("evidence_url") or "").lower():
        score += 4
    if "sernapesca" in (row.get("source") or "").lower():
        score += 3

    # Downrank
    if not email:
        score -= 12
    if classification == CLASS_SAME_DOMAIN:
        score -= 8
    if _is_generic_email(email):
        score -= 5
    if "low_fit" in flags:
        score -= 15
    if "sin_email_publico" in flags:
        score -= 6
    if re.search(r"reactivo|reagent|consumible", blob, re.I):
        score -= 10
    if (row.get("confidence") or "").lower() == "media":
        score -= 2
    elif (row.get("confidence") or "").lower() == "baja":
        score -= 5

    return max(0, min(100, score))


def recommended_next_action(classification: str, row: dict[str, str]) -> str:
    if classification == CLASS_NET_NEW:
        if row.get("email"):
            return "Redactar correo inicial personalizado y registrar en cola de revisión humana"
        return "Buscar contacto directo de laboratorio antes de outreach"
    if classification == CLASS_PUBLIC_TENDER:
        return "Monitorear bases Mercado Público y preparar ficha técnica / equivalencias"
    if classification == CLASS_SAME_DOMAIN:
        return "Revisar si conviene contactar otra persona del mismo dominio o esperar respuesta"
    if classification == CLASS_RESEARCH_ONLY:
        return "Investigar email del responsable de laboratorio en sitio web o directorio"
    if classification == CLASS_ALREADY_CONTACTED:
        return "No contactar: ya contactado"
    return "Sin acción — bloqueado por política de no repetición"


def process_deepsearch_prospects(
    rows: Iterable[dict[str, str]],
    excl: ExclusionLists,
) -> list[ProcessedProspect]:
    out: list[ProcessedProspect] = []
    for row in rows:
        flags = parse_risk_flags(row.get("risk_flags"))
        classification, reason = classify_prospect(row, excl)
        input_score = _int_score(row.get("priority_score"), 50)
        is_blocked = classification in _BLOCKED
        final_score = (
            0
            if is_blocked
            else compute_final_score(
                row, classification=classification, input_score=input_score, flags=flags
            )
        )
        angle = spanish_message_angle(row)
        action = recommended_next_action(classification, row)
        out.append(
            ProcessedProspect(
                row=row,
                classification=classification,
                input_priority_score=input_score,
                final_score=final_score,
                spanish_message_angle=angle,
                block_or_review_reason=reason,
                recommended_next_action=action,
            )
        )
    return out


def dedupe_prospects(prospects: list[ProcessedProspect]) -> list[ProcessedProspect]:
    """Keep highest final_score per email, else per domain+organization."""
    by_email: dict[str, ProcessedProspect] = {}
    by_org_domain: dict[str, ProcessedProspect] = {}
    no_key: list[ProcessedProspect] = []

    def better(a: ProcessedProspect, b: ProcessedProspect) -> ProcessedProspect:
        return a if a.final_score >= b.final_score else b

    for p in prospects:
        em = p.row.get("email") or ""
        if em:
            by_email[em] = better(p, by_email[em]) if em in by_email else p
            continue
        key = f"{p.row.get('organization_name','')}|{p.row.get('domain','')}".lower()
        if key.strip("|"):
            by_org_domain[key] = better(p, by_org_domain[key]) if key in by_org_domain else p
        else:
            no_key.append(p)

    merged = list(by_email.values()) + list(by_org_domain.values()) + no_key
    merged.sort(key=lambda x: (-x.final_score, x.row.get("organization_name", "")))
    return merged


def build_summary(prospects: list[ProcessedProspect], input_files: list[str]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    for p in prospects:
        counts[p.classification] = counts.get(p.classification, 0) + 1
    review = [p for p in prospects if not p.is_blocked]
    blocked = [p for p in prospects if p.is_blocked]
    return {
        "input_files": input_files,
        "total_rows_processed": len(prospects),
        "review_rows": len(review),
        "blocked_rows": len(blocked),
        "classification_counts": counts,
        "net_new_safe_count": counts.get(CLASS_NET_NEW, 0),
        "public_tender_review_count": counts.get(CLASS_PUBLIC_TENDER, 0),
        "same_domain_review_count": counts.get(CLASS_SAME_DOMAIN, 0),
        "research_only_count": counts.get(CLASS_RESEARCH_ONLY, 0),
    }


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(fieldnames), lineterminator="\n")
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})


def _prospect_section_bucket(p: ProcessedProspect) -> str:
    buyer = (p.row.get("buyer_type") or "").lower()
    if p.classification == CLASS_PUBLIC_TENDER or "public_tender" in buyer:
        return "public_tender"
    if p.classification == CLASS_SAME_DOMAIN:
        return "same_domain"
    if "universidad" in (p.row.get("sector") or "").lower() or "centro_investigacion" in buyer:
        return "university"
    if any(
        x in buyer
        for x in ("laboratorio_privado", "laboratorio_alimentos", "laboratorio_acuicola", "laboratorio_agua")
    ):
        return "private_lab"
    if "laboratorio" in buyer or "centro_ensayos" in buyer:
        return "private_lab"
    return "other"


def _format_top25_entry(p: ProcessedProspect, n: int) -> list[str]:
    r = p.row
    contact = r.get("contact_name") or "—"
    email = r.get("email") or "—"
    lines = [
        f"### {n}. {r.get('organization_name', 'Sin nombre')}",
        "",
        f"- **Contacto:** {contact} ({email})",
        f"- **Ángulo de producto:** {r.get('product_angle', '—')}",
        f"- **Mensaje sugerido:** {p.spanish_message_angle}",
        f"- **Evidencia:** [{r.get('source', 'fuente')}]({r.get('evidence_url', '')}) — {r.get('evidence_note', '')}",
        f"- **Por qué importa:** {r.get('likely_need', '—')} (puntuación final {p.final_score})",
        f"- **Próxima acción:** {p.recommended_next_action}",
        "",
    ]
    return lines


def write_top25_markdown(
    prospects: list[ProcessedProspect],
    path: Path,
    *,
    limit_per_section: int = 8,
) -> None:
    review = [p for p in prospects if not p.is_blocked]
    buckets: dict[str, list[ProcessedProspect]] = {
        "private_lab": [],
        "public_tender": [],
        "university": [],
        "same_domain": [],
    }
    for p in review:
        b = _prospect_section_bucket(p)
        if b in buckets:
            buckets[b].append(p)
        elif p.classification == CLASS_SAME_DOMAIN:
            buckets["same_domain"].append(p)

    for key in buckets:
        buckets[key].sort(key=lambda x: -x.final_score)

    sections = [
        ("Top prospectos net-new — laboratorios privados / QC", "private_lab"),
        ("Top oportunidades públicas / licitaciones", "public_tender"),
        ("Top universidades y centros de investigación", "university"),
        ("Revisión mismo dominio — alto valor", "same_domain"),
    ]

    lines = [
        "# Top 25 — prospectos DeepSearch (revisión)",
        "",
        "Lista priorizada para revisión humana. **No enviar correos automáticamente.**",
        "",
    ]
    n_global = 0
    for title, key in sections:
        lines.append(f"## {title}")
        lines.append("")
        items = buckets[key][:limit_per_section]
        if not items:
            lines.append("_Sin candidatos en esta categoría._")
            lines.append("")
            continue
        for i, p in enumerate(items, 1):
            n_global += 1
            lines.extend(_format_top25_entry(p, n_global))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_follow_up_top25(
    follow_up_csv: Path,
    out_path: Path,
    *,
    limit: int = 25,
) -> None:
    if not follow_up_csv.is_file():
        out_path.write_text(
            "# Top 25 — seguimiento (sin archivo fuente)\n\n"
            f"No se encontró `{follow_up_csv.name}`.\n",
            encoding="utf-8",
        )
        return
    rows: list[dict[str, str]] = []
    with follow_up_csv.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            rows.append({k: (v or "").strip() for k, v in row.items()})
    rows.sort(key=lambda r: r.get("last_contacted_at", ""), reverse=True)
    lines = [
        "# Top 25 — candidatos a seguimiento (contacto previo)",
        "",
        "Extraído de `follow_up_candidates_review.csv`. Solo revisión — no envío automático.",
        "",
    ]
    for i, r in enumerate(rows[:limit], 1):
        lines.extend(
            [
                f"### {i}. {r.get('organization_name') or r.get('domain', '—')}",
                "",
                f"- **Email:** {r.get('normalized_email', '—')}",
                f"- **Último contacto:** {r.get('last_contacted_at', '—')}",
                f"- **Asunto:** {r.get('latest_subject_safe', '—')}",
                f"- **Ángulo:** {r.get('recommended_follow_up_angle', '—')}",
                "",
            ]
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_summary_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# Resumen — procesamiento DeepSearch (Phase 10B)",
        "",
        "Procesamiento **solo lectura**. Sin envíos ni escrituras a SQLite.",
        "",
        "| Métrica | Valor |",
        "|--------|------:|",
    ]
    for key, val in summary.items():
        if key == "classification_counts":
            continue
        if isinstance(val, (int, float)):
            lines.append(f"| {key} | {val:,} |")
    lines.append("")
    lines.append("## Clasificación")
    lines.append("")
    counts = summary.get("classification_counts") or {}
    for k in sorted(counts.keys()):
        lines.append(f"- `{k}`: {counts[k]:,}")
    lines.append("")
    lines.append("## Archivos generados")
    lines.append("")
    lines.append("- `new_customer_targets_review.csv` — candidatos para revisión")
    lines.append("- `new_customer_targets_blocked.csv` — bloqueados por no-repetición")
    lines.append("- `new_customer_targets_top25.md` — top priorizados por segmento")
    lines.append("- `follow_up_candidates_top25.md` — seguimiento a contactos previos")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_all_outputs(
    prospects: list[ProcessedProspect],
    summary: dict[str, Any],
    out_dir: Path,
    *,
    follow_up_csv: Path | None = None,
) -> dict[str, Path]:
    review_rows = [p.to_review_dict() for p in prospects if not p.is_blocked]
    blocked_rows = [p.to_blocked_dict() for p in prospects if p.is_blocked]
    review_rows.sort(key=lambda r: -int(r.get("final_score") or 0))
    blocked_rows.sort(key=lambda r: (r.get("classification", ""), r.get("organization_name", "")))

    paths = {
        "review_csv": out_dir / "new_customer_targets_review.csv",
        "blocked_csv": out_dir / "new_customer_targets_blocked.csv",
        "top25_md": out_dir / "new_customer_targets_top25.md",
        "summary_md": out_dir / "new_customer_targets_summary.md",
        "follow_up_md": out_dir / "follow_up_candidates_top25.md",
    }
    _write_csv(paths["review_csv"], REVIEW_OUTPUT_FIELDS, review_rows)
    _write_csv(paths["blocked_csv"], BLOCKED_OUTPUT_FIELDS, blocked_rows)
    write_top25_markdown(prospects, paths["top25_md"])
    write_summary_markdown(summary, paths["summary_md"])
    follow = follow_up_csv or (out_dir / "follow_up_candidates_review.csv")
    write_follow_up_top25(follow, paths["follow_up_md"])
    return paths


def run_process(
    input_dir: Path,
    exclusion_dir: Path,
    out_dir: Path,
) -> ProcessResult:
    rows, input_files = load_deepsearch_rows(input_dir)
    excl = load_exclusion_lists(exclusion_dir)
    processed = process_deepsearch_prospects(rows, excl)
    deduped = dedupe_prospects(processed)
    summary = build_summary(deduped, input_files)
    write_all_outputs(deduped, summary, out_dir)
    return ProcessResult(prospects=deduped, summary=summary, input_files=input_files)
