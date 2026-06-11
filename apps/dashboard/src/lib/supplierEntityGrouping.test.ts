import { describe, expect, it } from "vitest";
import type { WarmCaseItem } from "../api/commercialTypes";
import {
  groupSupplierWarmCases,
  resolveSupplierGroupId,
  roleBadgeForCategory,
} from "./supplierEntityGrouping";

function row(
  email: string,
  category: WarmCaseItem["category"],
  account = "",
  subject = "",
  lastSeen: string | null = null,
): WarmCaseItem {
  return {
    case_id: email,
    last_email_id: 1,
    last_seen_at: lastSeen,
    account_name: account,
    contact_email: email,
    subject,
    category,
    status: "open",
    next_action: "",
    equipment_signal: "",
    snippet: "",
    gmail_url: null,
  };
}

describe("supplierEntityGrouping", () => {
  it("groups known suppliers with count summaries", () => {
    const groups = groupSupplierWarmCases([
      row("a@serva.de", "supplier_followup", "SERVA", "SERVA thread", "2026-05-20T10:00:00-04:00"),
      row("b@ika.net.br", "supplier_quote_received", "IKA", "IKA quote", "2026-05-19T10:00:00-04:00"),
      row("c@ortoalresa.com", "supplier_quote_received"),
    ]);
    expect(groups.map((g) => g.label)).toEqual(["SERVA", "IKA", "Ortoalresa"]);
    expect(groups[0].summaryLabel).toBe("1 caso en espejo");
    expect(groups[1].summaryLabel).toBe("1 caso en espejo");
    expect(groups[0].latestSubject).toBe("SERVA thread");
    expect(groups[1].roleBadge).toBe("Cotización recibida");
    expect(groups[0].roleBadge).toBe("Seguimiento");
  });

  it("resolveSupplierGroupId maps ika domain", () => {
    expect(resolveSupplierGroupId(row("x@ika.net.br", "supplier_quote_received"))).toBe("ika");
  });

  it("includes grouped email count in summary when present", () => {
    const groups = groupSupplierWarmCases([
      {
        ...row("b@ika.net.br", "supplier_quote_received", "IKA", "IKA quote"),
        grouped_email_count: 13,
      },
    ]);
    expect(groups[0]?.summaryLabel).toBe("1 caso en espejo · 13+ mensajes Gmail detectados");
  });

  it("roleBadgeForCategory maps quote and follow-up", () => {
    expect(roleBadgeForCategory("supplier_quote_received")).toBe("Cotización recibida");
    expect(roleBadgeForCategory("supplier_followup")).toBe("Seguimiento");
  });
});
