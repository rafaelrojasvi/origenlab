import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CommercialDealsListUi } from "../../api/commercialDealsTypes";
import { CommercialDealHighlightCards } from "./CommercialDealHighlightCards";

const ceafServaDeal: CommercialDealsListUi = {
  table_available: true,
  read_only: true,
  data_source: "postgres_mirror",
  total: 1,
  limit: 20,
  items: [
    {
      client_org_name: "Centro de Estudios Avanzados en Fruticultura CEAF",
      supplier_org_name: "SERVA Electrophoresis GmbH",
      deal_status: "logistics_pending",
      margin_status: "needs_review",
      reconciliation_status: "reconciled_excluding_supplier_freight",
      freight_status: "dhl_account_or_external_freight",
      client_sale_net_clp: 1_260_000,
      client_sale_gross_clp: 1_499_400,
      client_payment_received_clp: 1_499_400,
      supplier_invoice_total_decimal: "363.00",
      supplier_amount_paid_decimal: "218.00",
      margin_net_clp: null,
      margin_pct: null,
      margin_blockers: ["Missing confirmed wise_clp_debit"],
      updated_at: "2026-05-22T12:00:00+00:00",
      product_lines: [],
    },
  ],
};

describe("CommercialDealHighlightCards", () => {
  it("shows BlueSlick and TEMED for CEAF × SERVA featured deal", () => {
    render(<CommercialDealHighlightCards data={ceafServaDeal} />);
    screen.getByText("Negocio destacado");
    screen.getByText("BlueSlick™ 250 ml");
    screen.getByText("TEMED 25 ml");
    expect(screen.getByRole("link", { name: "BlueSlick™ 250 ml" }).getAttribute("href")).toBe(
      "#/catalogo?product=serva-blueslick-250ml",
    );
    expect(screen.getByRole("link", { name: "TEMED 25 ml" }).getAttribute("href")).toBe(
      "#/catalogo?product=serva-temed-25ml",
    );
    expect(screen.getByText(/Envío cliente.*20\.000.*neto/)).toBeTruthy();
  });
});
