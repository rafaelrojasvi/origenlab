"""Mock Postgres connection for lead_intel mirror API tests."""

from __future__ import annotations

from typing import Any

from fake_conn import MirrorFakeConn, _FakeCursor


class LeadFakeConn(MirrorFakeConn):
    """Postgres fake with sample prospects in lead_intel.* tables."""

    def __init__(self) -> None:
        super().__init__()
        self.tables[("lead_intel", "prospect")] = True
        self.tables[("lead_intel", "evidence")] = True
        self.tables[("lead_intel", "recommendation")] = True
        self.tables[("lead_intel", "block_reason")] = True
        self.prospects: list[dict[str, Any]] = [
            {
                "prospect_key": "contacto-acme-cl",
                "organization_name": "Acme Labs",
                "contact_name": None,
                "email": "contacto@acme.cl",
                "domain": "acme.cl",
                "sector": "Laboratorios privados",
                "region": "RM",
                "buyer_type": "laboratorio_privado",
                "likely_need": "Equipos",
                "product_angle": "centrífugas",
                "evidence_url": "https://www.acme.cl/",
                "evidence_note": "Sitio oficial",
                "source": "sitio_oficial",
                "final_score": 95,
                "confidence": "alta",
                "classification": "net_new_safe_review",
                "spanish_message_angle": "Equipos de laboratorio",
                "risk_flags": "",
                "block_or_review_reason": "prospecto_nuevo_seguro",
                "recommended_next_action": "Redactar correo inicial",
                "status": "net_new_safe_review",
                "campaign_bucket": "private_lab",
                "is_blocked": False,
                "source_type": "deepsearch",
                "dataset_label": "phase10b_deepsearch",
                "gmail_first_contacted_at": None,
                "gmail_last_contacted_at": None,
                "gmail_sent_count": None,
                "gmail_received_count": None,
                "gmail_latest_subject_safe": None,
            },
            {
                "prospect_key": "gmail-historico-cl",
                "organization_name": "Gmail Histórico Co",
                "contact_name": "Ana",
                "email": "ana@gmailhist.cl",
                "domain": "gmailhist.cl",
                "sector": "Laboratorios",
                "region": "RM",
                "buyer_type": "laboratorio_privado",
                "likely_need": None,
                "product_angle": "equipos",
                "evidence_url": None,
                "evidence_note": None,
                "source": "gmail_archive",
                "final_score": 80,
                "confidence": "alta",
                "classification": "old_gmail_prospect_review",
                "spanish_message_angle": "Presentación OrigenLab",
                "risk_flags": "",
                "block_or_review_reason": "gmail_historico",
                "recommended_next_action": "Revisar antes de presentación",
                "status": "revision_individual",
                "campaign_bucket": "private_lab",
                "is_blocked": False,
                "source_type": "gmail_historico",
                "dataset_label": "presentacion_batch1_final_send_25.csv",
                "gmail_first_contacted_at": "2024-01-15",
                "gmail_last_contacted_at": "2025-06-01",
                "gmail_sent_count": 4,
                "gmail_received_count": 1,
                "gmail_latest_subject_safe": "Consulta equipos",
            },
            {
                "prospect_key": "followup-antiguo-cl",
                "organization_name": "Follow-up Antiguo Co",
                "contact_name": None,
                "email": "old@followup.cl",
                "domain": "followup.cl",
                "sector": "Laboratorios",
                "region": "RM",
                "buyer_type": "laboratorio_privado",
                "likely_need": None,
                "product_angle": "balances",
                "evidence_url": None,
                "evidence_note": None,
                "source": "gmail_archive",
                "final_score": 75,
                "confidence": "media",
                "classification": "old_followup_review",
                "spanish_message_angle": "Seguimiento",
                "risk_flags": "",
                "block_or_review_reason": "followup_antiguo",
                "recommended_next_action": "Seguimiento personalizado",
                "status": "revision_individual",
                "campaign_bucket": "private_lab",
                "is_blocked": False,
                "source_type": "followup_antiguo",
                "dataset_label": "presentacion_batch2_followup_old_25.csv",
                "gmail_first_contacted_at": "2023-03-01",
                "gmail_last_contacted_at": "2024-11-20",
                "gmail_sent_count": 6,
                "gmail_received_count": 2,
                "gmail_latest_subject_safe": "Re: cotización",
            },
            {
                "prospect_key": "caso-activo-cl",
                "organization_name": "Caso Activo Hold",
                "contact_name": "Pedro",
                "email": "pedro@casoactivo.cl",
                "domain": "casoactivo.cl",
                "sector": None,
                "region": None,
                "buyer_type": None,
                "likely_need": None,
                "product_angle": None,
                "evidence_url": None,
                "evidence_note": None,
                "source": "warm_case_hold",
                "final_score": 0,
                "confidence": None,
                "classification": "active_case_hold",
                "spanish_message_angle": "Caso personalizado",
                "risk_flags": "",
                "block_or_review_reason": "CESMEC hold",
                "recommended_next_action": "hold_personalized_no_generic_campaign",
                "status": "hold_personalizado",
                "campaign_bucket": "active_case",
                "is_blocked": False,
                "source_type": "caso_activo",
                "dataset_label": "presentacion_hold_active_personalized.csv",
                "gmail_first_contacted_at": None,
                "gmail_last_contacted_at": None,
                "gmail_sent_count": None,
                "gmail_received_count": None,
                "gmail_latest_subject_safe": None,
            },
            {
                "prospect_key": "blocked-blocked-cl",
                "organization_name": "Blocked Co",
                "contact_name": None,
                "email": "blocked@blocked.cl",
                "domain": "blocked.cl",
                "sector": None,
                "region": None,
                "buyer_type": None,
                "likely_need": None,
                "product_angle": None,
                "evidence_url": None,
                "evidence_note": "Ya contactado",
                "source": None,
                "final_score": 0,
                "confidence": None,
                "classification": "already_contacted_block",
                "spanish_message_angle": None,
                "risk_flags": "dominio_en_historial_origenlab",
                "block_or_review_reason": "email_en_lista_contactados",
                "recommended_next_action": "No contactar",
                "status": "blocked",
                "campaign_bucket": "blocked",
                "is_blocked": True,
                "source_type": "deepsearch",
                "dataset_label": None,
                "gmail_first_contacted_at": None,
                "gmail_last_contacted_at": None,
                "gmail_sent_count": None,
                "gmail_received_count": None,
                "gmail_latest_subject_safe": None,
            },
            {
                "prospect_key": "other-origenlab-cl",
                "organization_name": "Old Domain Co",
                "contact_name": None,
                "email": "other@origenlab.cl",
                "domain": "origenlab.cl",
                "sector": "Laboratorios",
                "region": "RM",
                "buyer_type": "laboratorio_privado",
                "likely_need": None,
                "product_angle": "balances",
                "evidence_url": "https://example.com/",
                "evidence_note": "Evidencia",
                "source": "test",
                "final_score": 70,
                "confidence": "alta",
                "classification": "same_domain_contacted_review",
                "spanish_message_angle": "Revisar dominio",
                "risk_flags": "dominio_en_historial_origenlab",
                "block_or_review_reason": "dominio_con_envios_previos",
                "recommended_next_action": "Revisar historial",
                "status": "same_domain_review",
                "campaign_bucket": "same_domain",
                "is_blocked": False,
                "source_type": "deepsearch",
                "dataset_label": "phase10b_deepsearch",
                "gmail_first_contacted_at": None,
                "gmail_last_contacted_at": None,
                "gmail_sent_count": None,
                "gmail_received_count": None,
                "gmail_latest_subject_safe": None,
            },
            {
                "prospect_key": "hospitaldemo-cl",
                "organization_name": "Hospital Demo",
                "contact_name": None,
                "email": None,
                "domain": "hospitaldemo.cl",
                "sector": "Licitaciones",
                "region": "Valparaíso",
                "buyer_type": "public_tender",
                "likely_need": None,
                "product_angle": "incubadoras",
                "evidence_url": "https://www.mercadopublico.cl/",
                "evidence_note": "Base pública",
                "source": "mercadopublico",
                "final_score": 88,
                "confidence": "media",
                "classification": "public_tender_review",
                "spanish_message_angle": "Licitación equipamiento",
                "risk_flags": "",
                "block_or_review_reason": "licitacion_publica",
                "recommended_next_action": "Revisar bases",
                "status": "public_tender_review",
                "campaign_bucket": "public_tender",
                "is_blocked": False,
                "source_type": "deepsearch",
                "dataset_label": "phase10b_deepsearch",
                "gmail_first_contacted_at": None,
                "gmail_last_contacted_at": None,
                "gmail_sent_count": None,
                "gmail_received_count": None,
                "gmail_latest_subject_safe": None,
            },
        ]
        self.evidence = [
            {
                "prospect_key": "contacto-acme-cl",
                "evidence_kind": "public_url",
                "evidence_url": "https://www.acme.cl/",
                "evidence_note": "Sitio oficial",
                "source": "sitio_oficial",
                "confidence": "alta",
            }
        ]
        self.recommendation = {
            "prospect_key": "contacto-acme-cl",
            "campaign_bucket": "private_lab",
            "recommended_message_angle": "Equipos de laboratorio",
            "recommended_next_action": "Redactar correo inicial",
            "why_this_lead": "Equipos · centrífugas",
            "suggested_subject": "Consulta técnica — Acme Labs",
            "suggested_body_preview": "Estimados/as equipo de Acme Labs...",
            "safety_note": "Revisión humana requerida. No enviar automáticamente.",
        }
        self.block_reasons = [
            {
                "prospect_key": "blocked-blocked-cl",
                "reason_code": "already_contacted_block",
                "reason_label": "Ya contactado",
            }
        ]

    def _apply_filters(self, sql: str, params: list[Any]) -> list[dict[str, Any]]:
        rows = list(self.prospects)
        s = " ".join(sql.split()).lower()
        idx = 0
        if "is_blocked = true" in s:
            rows = [r for r in rows if r["is_blocked"]]
        elif "is_blocked = false" in s:
            rows = [r for r in rows if not r["is_blocked"]]
        if "source_type = %s" in s:
            st = str(params[idx])
            rows = [r for r in rows if r.get("source_type") == st]
            idx += 1
        if "classification = %s" in s:
            cls = str(params[idx])
            rows = [r for r in rows if r["classification"] == cls]
            idx += 1
        if "sector ilike" in s:
            needle = str(params[idx]).strip("%").lower()
            rows = [r for r in rows if needle in (r.get("sector") or "").lower()]
            idx += 1
        if "organization_name ilike" in s:
            like = str(params[idx]).strip("%").lower()
            rows = [
                r
                for r in rows
                if like in r["organization_name"].lower()
                or like in (r.get("email") or "").lower()
                or like in (r.get("contact_name") or "").lower()
                or like in (r.get("domain") or "").lower()
            ]
            idx += 4
        return rows

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        s = " ".join(sql.split()).lower()
        p = list(params) if params is not None else []

        if "information_schema.tables" in s:
            schema = p[0] if p else ""
            table = p[1] if len(p) > 1 else ""
            ok = self.tables.get((schema, table), False)
            return _FakeCursor([{"?": 1}] if ok else [])

        if "count(*) as c from lead_intel.prospect" in s:
            filtered = self._apply_filters(sql, p) if "where" in s else list(self.prospects)
            return _FakeCursor([{"c": len(filtered)}])

        if "from lead_intel.prospect" in s and "order by final_score" in s:
            if "where" in s:
                filter_params = p[:-1]
                limit = int(p[-1])
            else:
                filter_params = []
                limit = int(p[0])
            filtered = self._apply_filters(sql, filter_params)
            return _FakeCursor(filtered[:limit])

        if "from lead_intel.prospect" in s and "prospect_key = %s" in s:
            key = str(p[0])
            for row in self.prospects:
                if row["prospect_key"] == key:
                    return _FakeCursor([row])
            return _FakeCursor([])

        if "from lead_intel.evidence" in s:
            key = str(p[0])
            return _FakeCursor([e for e in self.evidence if e["prospect_key"] == key])

        if "from lead_intel.recommendation" in s:
            key = str(p[0])
            if self.recommendation.get("prospect_key") == key:
                return _FakeCursor([self.recommendation])
            return _FakeCursor([])

        if "from lead_intel.block_reason" in s:
            key = str(p[0])
            return _FakeCursor([b for b in self.block_reasons if b["prospect_key"] == key])

        if "count(*) as total" in s and "filter (where" in s:
            total = len(self.prospects)
            review = sum(1 for r in self.prospects if not r["is_blocked"])
            blocked = total - review
            return _FakeCursor(
                [
                    {
                        "total": total,
                        "review_count": review,
                        "blocked_count": blocked,
                        "net_new_safe": sum(
                            1 for r in self.prospects if r["classification"] == "net_new_safe_review"
                        ),
                        "public_tender_review": sum(
                            1
                            for r in self.prospects
                            if r["classification"] == "public_tender_review"
                        ),
                        "same_domain_review": sum(
                            1
                            for r in self.prospects
                            if r["classification"] == "same_domain_contacted_review"
                        ),
                        "research_needed": sum(
                            1
                            for r in self.prospects
                            if r["classification"] == "research_only_contact_needed"
                        ),
                        "gmail_historico": sum(
                            1
                            for r in self.prospects
                            if r.get("source_type") == "gmail_historico" and not r["is_blocked"]
                        ),
                        "followup_antiguo": sum(
                            1
                            for r in self.prospects
                            if r.get("source_type") == "followup_antiguo" and not r["is_blocked"]
                        ),
                        "caso_activo": sum(
                            1 for r in self.prospects if r.get("source_type") == "caso_activo"
                        ),
                    }
                ]
            )

        return super().execute(sql, params)
