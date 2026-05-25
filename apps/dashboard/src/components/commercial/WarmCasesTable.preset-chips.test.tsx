import { describe, expect, it } from "vitest";
import type { WarmCaseItem } from "../../api/commercialTypes";
import { applyWarmCaseTableView } from "../../lib/warmCaseTableView";

function row(partial: Partial<WarmCaseItem> & Pick<WarmCaseItem, "contact_email" | "category">): WarmCaseItem {
  return {
    case_id: partial.case_id ?? partial.contact_email,
    last_email_id: 1,
    last_seen_at: "2026-05-22T10:00:00Z",
    account_name: partial.account_name ?? "",
    subject: partial.subject ?? "",
    status: partial.status ?? "open",
    next_action: "",
    equipment_signal: "",
    snippet: "",
    gmail_url: null,
    ...partial,
  };
}

const ITEMS: WarmCaseItem[] = [
  row({
    contact_email: "serviciodetransferencias@bancochile.cl",
    category: "payment_admin",
    subject: "FACTURA 6",
  }),
  row({
    contact_email: "monica.silva@dhl.com",
    category: "vendor_logistics",
    subject: "PROPUESTA COMERCIAL DHL",
  }),
  row({
    contact_email: "cgaray@ceaf.cl",
    category: "client_reply",
    subject: "Remite OC N º 26172",
  }),
  row({
    contact_email: "contacto@origenlab.cl",
    category: "waiting_client",
    subject: "Re: Quotation Request",
  }),
];

describe("WarmCasesTable preset chips (applyWarmCaseTableView)", () => {
  it("Pagos/admin shows BancoChile row", () => {
    const visible = applyWarmCaseTableView(ITEMS, {
      search: "",
      status: "",
      category: "",
      sort: "last_seen_desc",
      hideInternalContacts: true,
      preset: "pagos_admin",
    });
    expect(visible.map((r) => r.contact_email)).toEqual([
      "serviciodetransferencias@bancochile.cl",
    ]);
  });

  it("Logística shows DHL row", () => {
    const visible = applyWarmCaseTableView(ITEMS, {
      search: "",
      status: "",
      category: "",
      sort: "last_seen_desc",
      hideInternalContacts: true,
      preset: "logistica",
    });
    expect(visible.map((r) => r.contact_email)).toEqual(["monica.silva@dhl.com"]);
  });

  it("Clientes reales shows CEAF and excludes contacto@origenlab.cl", () => {
    const visible = applyWarmCaseTableView(ITEMS, {
      search: "",
      status: "",
      category: "",
      sort: "last_seen_desc",
      hideInternalContacts: true,
      preset: "clientes_reales",
    });
    expect(visible.map((r) => r.contact_email)).toEqual(["cgaray@ceaf.cl"]);
  });
});
