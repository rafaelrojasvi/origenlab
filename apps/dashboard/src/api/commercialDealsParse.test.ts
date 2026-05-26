import { describe, expect, it } from "vitest";
import { parseCommercialDealUiRow, parseCommercialDealsListResponse } from "./commercialDealsParse";

describe("commercialDealsParse", () => {
  it("keeps only safe scalar fields on list parse", () => {
    const parsed = parseCommercialDealsListResponse({
      table_available: true,
      read_only: true,
      data_source: "postgres_mirror",
      total: 1,
      limit: 20,
      items: [
        {
          deal_key: "secret-deal-key",
          client_org_name: "CEAF",
          supplier_org_name: "SERVA",
          deal_status: "logistics_pending",
          margin_status: "needs_review",
          reconciliation_status: "reconciled",
          freight_status: "pending",
          client_sale_net_clp: 1_260_000,
          client_sale_gross_clp: 1_499_400,
          client_payment_received_clp: 1_499_400,
          supplier_invoice_total_decimal: "363.00",
          supplier_amount_paid_decimal: "218.00",
          margin_net_clp: null,
          margin_pct: 0.12,
          margin_blockers: ["Missing wise_clp_debit"],
          updated_at: "2026-05-22T12:00:00+00:00",
          transfer_id: "xfer-1",
          client_contact_email: "buyer@ceaf.cl",
          client_po_number: "PO-174",
          extract_snippet: "raw evidence",
          product_line_summaries: [{ product_name: "BlueSlick" }],
        },
      ],
    });

    expect(parsed.table_available).toBe(true);
    expect(parsed.items).toHaveLength(1);
    const row = parsed.items[0];
    expect(row.client_org_name).toBe("CEAF");
    expect(row.margin_pct).toBe(0.12);
    expect(row.margin_blockers).toEqual(["Missing wise_clp_debit"]);
    expect(row).not.toHaveProperty("deal_key");
    expect(row).not.toHaveProperty("transfer_id");
    expect(row).not.toHaveProperty("client_contact_email");
    expect(row).not.toHaveProperty("client_po_number");
    expect(row).not.toHaveProperty("extract_snippet");
    expect(row).not.toHaveProperty("product_line_summaries");
  });

  it("parsed row exposes only allowlisted UI keys", () => {
    const row = parseCommercialDealUiRow({
      client_org_name: "A",
      supplier_org_name: "B",
      deal_status: "open",
      margin_status: "computed",
      supplier_invoice_total_minor: 36300,
      ref_code: "REF-1",
      description: "raw line description",
      counterparty_email: "secret@bank.cl",
    });
    expect(Object.keys(row).sort()).toEqual(
      [
        "client_org_name",
        "supplier_org_name",
        "deal_status",
        "margin_status",
        "reconciliation_status",
        "freight_status",
        "client_sale_net_clp",
        "client_sale_gross_clp",
        "client_payment_received_clp",
        "supplier_invoice_total_decimal",
        "supplier_amount_paid_decimal",
        "margin_net_clp",
        "margin_pct",
        "margin_blockers",
        "updated_at",
      ].sort(),
    );
  });

  it("parseCommercialDealUiRow strips forbidden keys", () => {
    const row = parseCommercialDealUiRow({
      client_org_name: "A",
      supplier_org_name: "B",
      deal_status: "open",
      margin_status: "computed",
      operation_id: "op-99",
      gmail_url: "https://mail.google.com/",
      source_path: "/tmp/evidence.pdf",
    });
    expect(row.client_org_name).toBe("A");
    expect(row).not.toHaveProperty("operation_id");
    expect(row).not.toHaveProperty("gmail_url");
    expect(row).not.toHaveProperty("source_path");
  });
});
