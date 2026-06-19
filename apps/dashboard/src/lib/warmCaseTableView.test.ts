import { describe, expect, it } from "vitest";
import type { WarmCaseItem } from "../api/commercialTypes";
import {
  DEFAULT_WARM_FILTERS,
  applyWarmCaseTableView,
  categoryRank,
  clearWarmCaseTableFilters,
  filterWarmCases,
  sortWarmCases,
  warmCaseSearchHaystack,
} from "./warmCaseTableView";

const rows: WarmCaseItem[] = [
  {
    case_id: "a",
    last_email_id: 1,
    last_seen_at: "2026-05-10T10:00:00Z",
    account_name: "ACME Lab",
    contact_email: "buyer@acme.cl",
    subject: "Centrifuge quote",
    category: "client_reply",
    status: "open",
    next_action: "follow",
    equipment_signal: "centrifuge",
    snippet: "preview one",
    gmail_url: null,
  },
  {
    case_id: "b",
    last_email_id: 2,
    last_seen_at: "2026-05-19T10:00:00Z",
    account_name: "Other Org",
    contact_email: "vendor@supplier.com",
    subject: "Supplier ping",
    category: "supplier_reply",
    status: "waiting",
    next_action: "wait",
    equipment_signal: "",
    snippet: "preview two",
    gmail_url: null,
  },
];

describe("warmCaseTableView", () => {
  it("search haystack includes domain and organization", () => {
    expect(warmCaseSearchHaystack(rows[0])).toContain("acme.cl");
    expect(warmCaseSearchHaystack(rows[0])).toContain("acme lab");
  });

  it("filters by search text", () => {
    const filtered = filterWarmCases(rows, {
      ...DEFAULT_WARM_FILTERS,
      preset: "todo",
      search: "supplier",
    });
    expect(filtered).toHaveLength(1);
    expect(filtered[0].contact_email).toBe("vendor@supplier.com");
  });

  it("filters by status and category", () => {
    const filtered = filterWarmCases(rows, {
      ...DEFAULT_WARM_FILTERS,
      preset: "todo",
      status: "open",
      category: "client_reply",
    });
    expect(filtered).toHaveLength(1);
    expect(filtered[0].case_id).toBe("a");
  });

  it("sorts by last_seen descending", () => {
    const sorted = sortWarmCases(rows, "last_seen_desc");
    expect(sorted[0].case_id).toBe("b");
  });

  it("categoryRank covers Phase 7A categories and unknowns sort last", () => {
    expect(categoryRank("bounce_problem")).toBeLessThan(categoryRank("payment_admin"));
    expect(categoryRank("supplier_quote_received")).toBeLessThan(categoryRank("client_response"));
    expect(categoryRank("client_opportunity")).toBeGreaterThan(categoryRank("waiting_client"));
    expect(categoryRank("not-a-real-category" as WarmCaseItem["category"])).toBe(99);
  });

  it("sorts by category using Phase 7A ranks", () => {
    const mixed: WarmCaseItem[] = [
      { ...rows[0], case_id: "pay", category: "payment_admin" },
      { ...rows[0], case_id: "client", category: "client_response" },
      { ...rows[0], case_id: "sup", category: "supplier_quote_received" },
      { ...rows[0], case_id: "noise", category: "system_noise" },
    ];
    const sorted = sortWarmCases(mixed, "category");
    expect(sorted.map((r) => r.case_id)).toEqual(["noise", "pay", "sup", "client"]);
  });

  it("apply combines filter and sort", () => {
    const out = applyWarmCaseTableView(rows, {
      ...DEFAULT_WARM_FILTERS,
      search: "acme",
      sort: "contact",
    });
    expect(out).toHaveLength(1);
    expect(out[0].contact_email).toBe("buyer@acme.cl");
  });

  it("hides internal contacts by default in DEFAULT_WARM_FILTERS", () => {
    const withInternal: WarmCaseItem[] = [
      ...rows,
      {
        ...rows[0],
        case_id: "internal",
        contact_email: "contacto@origenlab.cl",
      },
    ];
    const hidden = applyWarmCaseTableView(withInternal, DEFAULT_WARM_FILTERS);
    expect(hidden.map((r) => r.contact_email)).not.toContain("contacto@origenlab.cl");
    expect(hidden.map((r) => r.contact_email)).toContain("buyer@acme.cl");
    expect(hidden.map((r) => r.contact_email)).not.toContain("vendor@supplier.com");
  });

  it("default preset Clientes reales excludes supplier_reply", () => {
    const out = applyWarmCaseTableView(rows, DEFAULT_WARM_FILTERS);
    expect(out).toHaveLength(1);
    expect(out[0].contact_email).toBe("buyer@acme.cl");
  });

  it("clearWarmCaseTableFilters resets to Clientes reales defaults", () => {
    const cleared = clearWarmCaseTableFilters();
    expect(cleared).toEqual(DEFAULT_WARM_FILTERS);
    expect(cleared.preset).toBe("clientes_reales");
    expect(cleared.hideInternalContacts).toBe(true);
  });

  it("hides internal origenlab and labdelivery contacts when enabled", () => {
    const withInternal: WarmCaseItem[] = [
      ...rows,
      {
        ...rows[0],
        case_id: "internal",
        contact_email: "contacto@origenlab.cl",
      },
    ];
    const hidden = filterWarmCases(withInternal, {
      ...DEFAULT_WARM_FILTERS,
      preset: "todo",
      hideInternalContacts: true,
    });
    expect(hidden.map((r) => r.contact_email)).not.toContain("contacto@origenlab.cl");
    expect(hidden.map((r) => r.contact_email)).toContain("buyer@acme.cl");
  });

  it("filters by local review label", () => {
    const filtered = filterWarmCases(
      rows,
      { ...DEFAULT_WARM_FILTERS, preset: "todo", review: "util" },
      { reviewLabels: { a: "util" } },
    );
    expect(filtered).toHaveLength(1);
    expect(filtered[0].case_id).toBe("a");
  });
});
