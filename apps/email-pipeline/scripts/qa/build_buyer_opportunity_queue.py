#!/usr/bin/env python3
# -----------------------------------------------------------------------------
# LEGACY_DO_NOT_USE: Superseded by scripts/qa/build_equipment_first_opportunity_queue.py
# and build_equipment_first_operator_queue.py. Retained for audit/tests only — do not
# use for current operator export, send planning, or equipment-first workflows.
# See docs/SCRIPT_MAP.md and reports/out/active/current/manifest.json.
# -----------------------------------------------------------------------------
"""Cross-check tender/private-lab buyer imports and emit A/B outreach queues.

LEGACY_DO_NOT_USE for equipment-first public-tender work (2026-05+).
Superseded by:
  - scripts/qa/build_equipment_first_opportunity_queue.py
  - scripts/qa/build_equipment_first_operator_queue.py
Do not use buyer_opportunity_crosscheck_* or tender_buyer_outreach_queue_* as canonical export inputs.
See reports/out/active/current/manifest.json and docs/AGENTS.md.
"""

from __future__ import annotations

import argparse
import csv
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from origenlab_email_pipeline.core.safety import print_script_deprecation_warning
REPORTS = ROOT / "reports/out/active/current"
DEFAULT_DB = Path("/home/rafael/data/origenlab-email/sqlite/emails.sqlite")

PRIORITY_TENDER_CODES: dict[str, tuple[str, str, str]] = {
    "1057898-51-LP26": ("SERVICIO DE SALUD NUBLE", "centrifuge_equipment", "high"),
    "2171-3-LE26": ("HOSPITAL SAN AGUSTIN DE LA LIGUA", "centrifuge_equipment", "high"),
    "1057501-252-LP26": ("COMPLEJO ASISTENCIAL DR. SOTERO DEL RIO", "centrifuge_maintenance", "high"),
    "1657-8-LE26": ("SUBSECRETARIA DE SALUD PUBLICA", "lab_water_microbiology", "high"),
    "1497-6-LE26": ("SUBSECRETARIA DE SALUD PUBLICA", "lab_water_microbiology", "high"),
    "1497-3-LE26": ("SUBSECRETARIA DE SALUD PUBLICA", "lab_food_analysis", "high"),
    "1511-30-LP26": ("Hospital de Constitución", "bacteriology_reagents", "high"),
    "1511-31-LP26": ("Hospital de Constitución", "sterilization_supplies", "medium"),
}

PRIORITY_BUYER_SUBSTRINGS = (
    "SERVICIO DE SALUD NUBLE",
    "HOSPITAL SAN AGUSTIN DE LA LIGUA",
    "COMPLEJO ASISTENCIAL DR. SOTERO DEL RIO",
    "SUBSECRETARIA DE SALUD PUBLICA",
    "Hospital de Constitución",
)

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")


def _load_email_set(path: Path, norm_col: str = "email_norm") -> set[str]:
    out: set[str] = set()
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if norm_col in row and row[norm_col]:
                out.add(row[norm_col].lower().strip())
            for k, v in row.items():
                if v and "email" in k.lower() and "@" in v:
                    out.add(v.lower().strip())
    return out


def _parse_emails(raw: str) -> list[str]:
    if not raw or "[email" in raw.lower():
        return []
    found = EMAIL_RE.findall(raw.replace(";", " "))
    return [e.lower().strip() for e in found]


class CrossChecker:
    def __init__(self, db_path: Path, reports_dir: Path | None = None) -> None:
        base = reports_dir or REPORTS
        self.dnr = _load_email_set(base / "do_not_repeat_master.csv")
        self.contacted = _load_email_set(base / "outreach_contacted_all.csv") | _load_email_set(
            base.parent / "outreach_contacted_all.csv"
        )
        self.marketing = _load_email_set(base.parent / "all_known_marketing_contacts_dedup.csv")
        self.conn = sqlite3.connect(db_path)
        self.ocs = {
            r[0].lower(): r[1]
            for r in self.conn.execute(
                "SELECT contact_email_norm, state FROM outreach_contact_state"
            )
        }

    def classify_email(self, email: str) -> tuple[str, str]:
        if not email or "@" not in email:
            return "needs_manual_contact_research", ""
        em = email.lower().strip()
        flags: list[str] = []
        if em in self.dnr:
            flags.append("do_not_repeat_master")
        if em in self.contacted:
            flags.append("outreach_contacted_all")
        if em in self.marketing:
            flags.append("marketing_dedup")
        st = self.ocs.get(em)
        if st in ("contacted", "replied", "snoozed"):
            flags.append(f"outreach_state={st}")
        sent = self.conn.execute(
            """
            SELECT id, date_iso FROM emails
            WHERE source_file LIKE 'gmail:%Enviados%'
              AND lower(recipients) LIKE ?
            ORDER BY date_iso DESC LIMIT 1
            """,
            (f"%{em}%",),
        ).fetchone()
        if sent:
            flags.append(f"gmail_sent:{sent[0]}")
        if flags:
            return "do_not_contact", "; ".join(flags)
        return "clean_new_target", ""

    def gmail_touch_for_buyer(self, buyer: str, limit: int = 3) -> str:
        needle = buyer[:40].lower()
        rows = self.conn.execute(
            """
            SELECT id, date_iso, subject FROM emails
            WHERE source_file LIKE 'gmail:contacto@origenlab.cl/%'
              AND date_iso >= date('now', '-365 days')
              AND (
                lower(sender) LIKE ?
                OR lower(recipients) LIKE ?
                OR lower(body_text_clean) LIKE ?
                OR lower(subject) LIKE ?
              )
            ORDER BY date_iso DESC
            LIMIT ?
            """,
            (f"%{needle}%", f"%{needle}%", f"%{needle}%", f"%{needle}%", limit),
        ).fetchall()
        parts = [f"{r[0]}:{r[1][:10]}" for r in rows]
        return "; ".join(parts)


def _row_base(**kwargs: str) -> dict[str, str]:
    keys = (
        "account",
        "contact_name",
        "contact_email",
        "subject",
        "latest_date",
        "product_line",
        "warm_signal",
        "current_status",
        "recommended_next_action",
        "priority",
        "owner_note",
        "gmail_search_terms",
        "tender_codes",
        "source_type",
        "ab_queue",
        "suppression_flags",
    )
    return {k: kwargs.get(k, "") for k in keys}


def build_rows(checker: CrossChecker, reports_dir: Path | None = None) -> list[dict[str, str]]:
    base = reports_dir or REPORTS
    rows: list[dict[str, str]] = []

    # --- Private labs ---
    priv_path = base / "origenlab_private_lab_targets_20260518.csv"
    with priv_path.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            emails = _parse_emails(r.get("contact_email", ""))
            per_email = [(e, *checker.classify_email(e)) for e in emails]
            clean = [e for e, st, _ in per_email if st == "clean_new_target"]
            if any(st == "do_not_contact" for _, st, _ in per_email):
                status = "do_not_contact"
            elif not emails:
                status = "needs_manual_contact_research"
            elif clean:
                status = "clean_new_target"
            else:
                status = "needs_manual_contact_research"
            flags = " | ".join(f"{e}:{fl}" for e, _, fl in per_email if fl)
            ab = "A" if status == "clean_new_target" and clean else ""
            action = (
                "Queue A: private-lab technical outreach (verified clean email)"
                if ab == "A"
                else (r.get("accion_sugerida") or "Suppress or research contact before send")
            )
            rows.append(
                _row_base(
                    account=r.get("institucion", ""),
                    contact_email="; ".join(clean) if clean else ("; ".join(emails) if emails else ""),
                    latest_date="",
                    product_line=(r.get("linea_origenlab_sugerida") or "")[:120],
                    warm_signal=(r.get("fit_signal") or "")[:300],
                    current_status=status,
                    recommended_next_action=action[:200],
                    priority=r.get("prioridad", "B"),
                    owner_note=flags[:300],
                    gmail_search_terms=clean[0] if clean else (emails[0] if emails else r.get("institucion", "")),
                    source_type="private_lab_targets",
                    ab_queue=ab,
                    suppression_flags=flags[:300],
                )
            )

    # --- Priority tender lines (one row per code) ---
    tend_path = base / "origenlab_relevant_tenders_20260518.csv"
    with tend_path.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            code = (r.get("codigo_licitacion") or "").strip()
            if code not in PRIORITY_TENDER_CODES:
                continue
            buyer, pline, pri = PRIORITY_TENDER_CODES[code]
            touch = checker.gmail_touch_for_buyer(buyer)
            rows.append(
                _row_base(
                    account=buyer,
                    subject=(r.get("titulo") or "")[:200],
                    latest_date=r.get("fecha_cierre", ""),
                    product_line=pline,
                    warm_signal=(r.get("senales") or "")[:300],
                    current_status="needs_manual_contact_research",
                    recommended_next_action=(
                        f"Queue B: tender intelligence — {r.get('accion_sugerida', '')[:120]}"
                    ),
                    priority=pri,
                    owner_note=(
                        f"score={r.get('score')}; cierre={r.get('fecha_cierre')}; "
                        f"no buyer email in import; prior_gmail={touch or 'none'}"
                    )[:300],
                    gmail_search_terms=code,
                    tender_codes=code,
                    source_type="relevant_tenders_priority",
                    ab_queue="B",
                )
            )

    # --- Buyer accounts (priority institutions only; account-level B queue) ---
    acct_path = base / "origenlab_buyer_accounts_from_tenders_20260518.csv"
    seen_accounts: set[str] = set()
    with acct_path.open(newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            buyer = (r.get("comprador") or "").strip()
            if not any(p.lower() in buyer.lower() for p in PRIORITY_BUYER_SUBSTRINGS):
                continue
            if buyer in seen_accounts:
                continue
            seen_accounts.add(buyer)
            codes = r.get("codigos", "")
            touch = checker.gmail_touch_for_buyer(buyer)
            pri_codes = [c.strip() for c in codes.split(";") if c.strip() in PRIORITY_TENDER_CODES]
            rows.append(
                _row_base(
                    account=buyer,
                    subject=(r.get("titulos_ejemplo") or "")[:200],
                    latest_date=r.get("proximo_cierre", ""),
                    product_line=(r.get("linea_origenlab_sugerida") or "")[:120],
                    warm_signal=(r.get("senales") or "")[:300],
                    current_status="needs_manual_contact_research",
                    recommended_next_action=(
                        "Queue B: map lab/abastecimiento contact from tender + CRM; "
                        "no cold generic blast"
                    ),
                    priority="high" if pri_codes else r.get("prioridad", "B"),
                    owner_note=(
                        f"licitaciones={r.get('licitaciones_relevantes')}; "
                        f"codes={codes[:120]}; prior_gmail={touch or 'none'}"
                    )[:300],
                    gmail_search_terms=pri_codes[0] if pri_codes else buyer[:40],
                    tender_codes=codes[:250],
                    source_type="buyer_accounts_priority",
                    ab_queue="B",
                )
            )

    return rows


def write_outputs(rows: list[dict[str, str]], date_suffix: str) -> tuple[Path, Path]:
    fields = list(rows[0].keys()) if rows else []
    full_path = REPORTS / f"buyer_opportunity_crosscheck_{date_suffix}.csv"
    ab_path = REPORTS / f"buyer_opportunity_ab_queue_{date_suffix}.csv"
    with full_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    ab_rows = [r for r in rows if r.get("ab_queue") in ("A", "B")]
    with ab_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(ab_rows)
    return full_path, ab_path


def write_markdown(rows: list[dict[str, str]], date_suffix: str) -> Path:
    md_path = REPORTS / f"tender_buyer_outreach_queue_{date_suffix}.md"
    a_rows = [r for r in rows if r.get("ab_queue") == "A"]
    b_rows = [r for r in rows if r.get("ab_queue") == "B"]
    suppressed = [r for r in rows if r.get("current_status") == "do_not_contact"]

    lines = [
        f"# Tender & buyer opportunity queue — {date_suffix}",
        "",
        "**Imports reviewed:**",
        "- `origenlab_buyer_accounts_from_tenders_20260518.csv`",
        "- `origenlab_relevant_tenders_20260518.csv`",
        "- `origenlab_private_lab_targets_20260518.csv`",
        "",
        "**Cross-check sources:** `do_not_repeat_master.csv`, `outreach_contacted_all.csv`,",
        "`all_known_marketing_contacts_dedup.csv`, Gmail Sent/Enviados (SQLite), `outreach_contact_state`.",
        "",
        "**Constraints:** No emails sent. No Gmail mutations. No invented emails.",
        "Public tenders keep **tender code** visible; buyer emails require manual research.",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|------:|",
        f"| Rows in crosscheck export | {len(rows)} |",
        f"| **Queue A** (clean private-lab email) | {len(a_rows)} |",
        f"| **Queue B** (priority tender/account intelligence) | {len(b_rows)} |",
        f"| Suppressed private targets | {len(suppressed)} |",
        "",
        "---",
        "",
        "## Queue A — ready private-lab outreach (clean email)",
        "",
    ]
    if a_rows:
        lines.append("| Account | Email | Product line | Gmail search |")
        lines.append("|---------|-------|--------------|--------------|")
        for r in a_rows:
            lines.append(
                f"| {r['account']} | {r['contact_email']} | {r['product_line'][:50]} | `{r['gmail_search_terms']}` |"
            )
    else:
        lines.append("_None — all private targets with listed emails are suppressed or need research._")

    lines.extend(["", "---", "", "## Queue B — priority tender & account intelligence", ""])
    lines.append("| Priority | Account | Tender code(s) | Subject / signal | Close | Action |")
    lines.append("|----------|---------|----------------|------------------|-------|--------|")
    for r in sorted(b_rows, key=lambda x: (x.get("priority") != "high", x.get("account", ""))):
        codes = r.get("tender_codes", "")[:80]
        if len(r.get("tender_codes", "")) > 80:
            codes += "…"
        lines.append(
            f"| {r['priority']} | {r['account'][:45]} | `{codes}` | {r['subject'][:55]} | "
            f"{r['latest_date'][:16]} | {r['recommended_next_action'][:60]} |"
        )

    lines.extend(["", "---", "", "## Suppressed private-lab contacts", ""])
    if suppressed:
        lines.append("| Account | Email(s) | Suppression |")
        lines.append("|---------|----------|-------------|")
        for r in suppressed:
            lines.append(f"| {r['account']} | {r['contact_email']} | {r['suppression_flags'][:120]} |")
    else:
        lines.append("_None._")

    lines.extend(
        [
            "",
            "---",
            "",
            "## Operator notes",
            "",
            "1. **Ñuble centrifuge** (`1057898-51-LP26`) — UMT centrifuges for new regional hospital; closes ~2026-06-04.",
            "   No verified buyer email in import. Research hospital lab / Servicio de Salud Ñuble abastecimiento.",
            "2. **La Ligua centrifuge** (`2171-3-LE26`) — clinical lab centrifuge in *Inversión 2026*; closes ~2026-05-26.",
            "3. **Sótero del Río** (`1057501-252-LP26`) — tube centrifuge **maintenance** (Abbott/Kubota/Thermo); account has 8 active lab tenders.",
            "4. **SSP / SEREMI** — Coquimbo micro/chemical (`1657-8-LE26`), Los Ríos water (`1497-6-LE26`), food sampling (`1497-3-LE26`).",
            "5. **Hospital Constitución** — bacteriology reagents (`1511-30-LP26`) + sterilization (`1511-31-LP26`).",
            "6. **Do not cold-blast** Red Salud / UFRO / Sanderson centrifuge contacts contacted 2026-05-18 (see `centrifuge_outreach_candidates_20260518.csv`).",
            "",
            "**CSV exports:** `buyer_opportunity_crosscheck_{date_suffix}.csv`, `buyer_opportunity_ab_queue_{date_suffix}.csv`",
            "",
        ]
    )
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def main() -> None:
    print_script_deprecation_warning(
        "scripts/qa/build_buyer_opportunity_queue.py",
        replacement=(
            "scripts/qa/build_equipment_first_opportunity_queue.py and "
            "scripts/qa/build_equipment_first_operator_queue.py"
        ),
        note="LEGACY_DO_NOT_USE — audit/tests only; not for equipment-first export or send planning.",
    )
    parser = argparse.ArgumentParser()
    parser.add_argument("--date-suffix", default="20260518")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()
    checker = CrossChecker(args.db, reports_dir=REPORTS)
    rows = build_rows(checker, reports_dir=REPORTS)
    full_path, ab_path = write_outputs(rows, args.date_suffix)
    md_path = write_markdown(rows, args.date_suffix)
    a = sum(1 for r in rows if r.get("ab_queue") == "A")
    b = sum(1 for r in rows if r.get("ab_queue") == "B")
    print(f"Wrote {full_path} ({len(rows)} rows)")
    print(f"Wrote {ab_path} (A={a}, B={b})")
    print(f"Wrote {md_path}")


if __name__ == "__main__":
    main()
