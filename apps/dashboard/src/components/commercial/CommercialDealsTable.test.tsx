import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CommercialDealsListUi } from "../../api/commercialDealsTypes";
import { CommercialDealsTable } from "./CommercialDealsTable";

const sampleDeal: CommercialDealsListUi = {
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
    },
  ],
};

describe("CommercialDealsTable", () => {
  it("renders redacted deal rows and mirror labels", () => {
    render(
      <CommercialDealsTable data={sampleDeal} loading={false} error={null} onRetry={() => {}} />,
    );

    screen.getByText("Negocios comerciales");
    expect(screen.getAllByText(/Espejo Postgres · solo lectura · vista redactada/).length).toBeGreaterThan(0);
    screen.getByText("Centro de Estudios Avanzados en Fruticultura CEAF");
    screen.getByText("SERVA Electrophoresis GmbH");
    expect(screen.getAllByText("needs_review").length).toBeGreaterThan(0);
    screen.getByText(/Missing confirmed wise_clp_debit/);
    expect(screen.getByText(/EUR 363\.00/)).toBeTruthy();
  });

  it("shows safe empty state when table is available but items are empty", () => {
    render(
      <CommercialDealsTable
        data={{
          table_available: true,
          read_only: true,
          data_source: "postgres_mirror",
          total: 0,
          limit: 20,
          items: [],
        }}
        loading={false}
        error={null}
        onRetry={() => {}}
      />,
    );

    screen.getByText("El espejo de negocios aún no está sincronizado.");
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows safe empty state when mirror is unavailable", () => {
    render(
      <CommercialDealsTable
        data={{
          table_available: false,
          read_only: true,
          data_source: "postgres_mirror",
          total: 0,
          limit: 20,
          items: [],
        }}
        loading={false}
        error={null}
        onRetry={() => {}}
      />,
    );

    screen.getByText("El espejo de negocios aún no está sincronizado.");
  });

  it("has no row links or action buttons beyond section retry", () => {
    const { container } = render(
      <CommercialDealsTable data={sampleDeal} loading={false} error={null} onRetry={() => {}} />,
    );
    expect(container.querySelectorAll("a[href]").length).toBe(0);
    expect(container.querySelectorAll("button").length).toBe(0);
  });

  it("does not render forbidden private fields", () => {
    const { container } = render(
      <CommercialDealsTable data={sampleDeal} loading={false} error={null} onRetry={() => {}} />,
    );
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/transfer_id|operation_id|client_contact_email|client_po_number/i);
    expect(text).not.toMatch(/buyer@|procurement@|gmail\.com/i);
    expect(text).not.toMatch(/serva-ceaf-oc-26172|PO-174|extract_snippet/i);
    expect(screen.queryByText(/purchase-events/i)).toBeNull();
  });
});
