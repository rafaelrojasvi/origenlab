"""Mock Postgres connection for mirror commercial deal ledger tests."""

from __future__ import annotations

import json
from typing import Any

from fake_conn import MirrorFakeConn, _FakeCursor


class CommercialDealsFakeConn(MirrorFakeConn):
    def __init__(self) -> None:
        super().__init__()
        self.tables[("commercial", "deal")] = True
        self.deals: list[dict[str, Any]] = [
            {
                "deal_key": "serva-ceaf-oc-26172-po-174-26",
                "client_org_name": "Centro de Estudios Avanzados en Fruticultura CEAF",
                "supplier_org_name": "SERVA Electrophoresis GmbH",
                "deal_status": "logistics_pending",
                "margin_status": "needs_review",
                "reconciliation_status": "reconciled_excluding_supplier_freight",
                "freight_status": "dhl_account_or_external_freight",
                "client_sale_net_clp": 1_260_000,
                "client_iva_amount_clp": 239_400,
                "client_sale_gross_clp": 1_499_400,
                "client_payment_received_clp": 1_499_400,
                "supplier_invoice_total_decimal": "363.00",
                "supplier_invoice_total_minor": 36300,
                "supplier_amount_paid_decimal": "218.00",
                "supplier_amount_paid_minor": 21800,
                "margin_net_clp": None,
                "margin_pct": None,
                "updated_at": "2026-05-22T12:00:00+00:00",
                "product_line_summaries": [
                    {
                        "side": "client",
                        "line_kind": "product",
                        "product_name": "BlueSlick™ 250 ml",
                        "category": "electrophoresis_reagent",
                        "quantity": "1",
                        "unit": "ea",
                        "currency": "CLP",
                        "line_net_amount": 695_000,
                    }
                ],
                "cost_summaries_by_type": [
                    {
                        "cost_kind": "fx_spread",
                        "currency": "CLP",
                        "total_amount_integer": 0,
                        "row_count": 0,
                    }
                ],
                "payment_summaries_masked": [
                    {
                        "direction": "inbound",
                        "payment_method": "bank_transfer",
                        "paid_at": "2026-05-22",
                        "currency": "CLP",
                        "amount_gross_integer": 1_499_400,
                    }
                ],
                "margin_blockers": [
                    "Missing confirmed wise_clp_debit (Wise CLP debit (card settlement))",
                ],
            }
        ]

    def execute(self, sql: str, params: Any = None) -> _FakeCursor:
        s = " ".join(sql.split()).lower()
        if "from commercial.deal" in s and "where deal_key" in s:
            key = str(params[0]).strip()
            rows = [r for r in self.deals if r["deal_key"] == key]
            return _FakeCursor(rows)
        if "from commercial.deal" in s and "order by" in s:
            limit = int(params[0]) if params else 20
            return _FakeCursor(self.deals[:limit])
        if "count(*)" in s and "commercial.deal" in s:
            return _FakeCursor([{"n": len(self.deals)}])
        return super().execute(sql, params)
