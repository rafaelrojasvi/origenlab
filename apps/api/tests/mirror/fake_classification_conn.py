"""Mock Postgres connection for mirror classification tests."""

from __future__ import annotations

from typing import Any

from fake_conn import MirrorFakeConn, _FakeCursor


class ClassificationFakeConn(MirrorFakeConn):
    def __init__(self) -> None:
        super().__init__()
        self.tables[("reporting", "email_classification_canonical")] = True
        self.classification_rows: list[dict[str, Any]] = [
            {
                "email_id": 1,
                "date_iso": "2026-05-10T12:00:00",
                "folder": "INBOX",
                "from_addr": "buyer@lab.cl",
                "to_addrs": "contacto@origenlab.cl",
                "subject": "Solicitud de cotización",
                "predicted_label": "quote_request_inbound",
                "confidence": "high_confidence",
                "ambiguous": False,
                "recommended_action": "responder_solicitud",
                "etiqueta_ui": "Posible solicitud",
                "evidence": "quote_strong",
            },
            {
                "email_id": 2,
                "date_iso": "2026-05-09T10:00:00",
                "folder": "[Gmail]/Enviados",
                "from_addr": "contacto@origenlab.cl",
                "to_addrs": "buyer@lab.cl",
                "subject": "Cotización adjunta",
                "predicted_label": "cotizacion_sent",
                "confidence": "high_confidence",
                "ambiguous": False,
                "recommended_action": "revisar_cotizacion",
                "etiqueta_ui": "Posible cotización enviada",
                "evidence": "sent_keywords",
            },
            {
                "email_id": 3,
                "date_iso": "2026-05-08T09:00:00",
                "folder": "INBOX",
                "from_addr": "compras@empresa.cl",
                "to_addrs": "contacto@origenlab.cl",
                "subject": "Orden de compra 1234",
                "predicted_label": "purchase_or_order_signal",
                "confidence": "high_confidence",
                "ambiguous": False,
                "recommended_action": "revisar_cliente_activo",
                "etiqueta_ui": "Posible compra / orden",
                "evidence": "purchase_strong",
            },
        ]

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        s = " ".join(sql.split()).lower()
        if "from reporting.email_classification_canonical" in s:
            if "group by predicted_label" in s:
                counts: dict[str, int] = {}
                for row in self.classification_rows:
                    lbl = str(row["predicted_label"])
                    counts[lbl] = counts.get(lbl, 0) + 1
                return _FakeCursor(
                    [{"predicted_label": k, "n": v} for k, v in sorted(counts.items())]
                )
            if "group by recommended_action" in s:
                counts_a: dict[str, int] = {}
                for row in self.classification_rows:
                    act = str(row["recommended_action"])
                    counts_a[act] = counts_a.get(act, 0) + 1
                return _FakeCursor(
                    [
                        {"recommended_action": k, "n": v}
                        for k, v in sorted(counts_a.items(), key=lambda x: -x[1])
                    ]
                )
            if "count(*)" in s:
                label = None
                if params and len(params) >= 1 and "predicted_label" in s:
                    label = params[0]
                rows = self.classification_rows
                if label:
                    rows = [r for r in rows if r["predicted_label"] == label]
                return _FakeCursor([{"n": len(rows)}])
            if "select subject" in s and params:
                action = params[0]
                subs = [
                    {"subject": r["subject"]}
                    for r in self.classification_rows
                    if r["recommended_action"] == action
                ][:3]
                return _FakeCursor(subs)
            if "select email_id" in s:
                label = None
                if params and "predicted_label" in s:
                    label = params[0]
                rows = list(self.classification_rows)
                if label:
                    rows = [r for r in rows if r["predicted_label"] == label]
                lim = params[-1] if params else len(rows)
                return _FakeCursor(rows[: int(lim)])
        return super().execute(sql, params)
