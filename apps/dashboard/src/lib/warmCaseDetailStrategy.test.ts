import { describe, expect, it } from "vitest";
import type { WarmCaseItem } from "../api/commercialTypes";
import {
  buildWarmCaseDetailView,
  sanitizeOperatorPreview,
} from "./warmCaseDetailStrategy";

function row(overrides: Partial<WarmCaseItem>): WarmCaseItem {
  return {
    case_id: "case-1",
    last_email_id: 1,
    last_seen_at: "2026-05-19T10:00:00-04:00",
    account_name: "IKA",
    contact_email: "beatriz.bonon@ika.net.br",
    subject: "RE: RV10.70 price",
    category: "supplier_quote_received",
    status: "waiting",
    next_action: "supplier_reply",
    equipment_signal: "rotary evaporator",
    snippet: "Price list attached",
    gmail_url: "https://mail.google.com/mail/u/0/#inbox/secret",
    ...overrides,
  };
}

describe("warmCaseDetailStrategy", () => {
  it("supplier_quote_received strategy mentions margin and client opportunity", () => {
    const detail = buildWarmCaseDetailView(row({ category: "supplier_quote_received" }));
    expect(detail.recommendedStrategy).toMatch(/client opportunity/i);
    expect(detail.recommendedStrategy).toMatch(/margin/i);
    expect(detail.linkedSection).toBe("suppliers");
  });

  it("payment_admin strategy says do not quote", () => {
    const detail = buildWarmCaseDetailView(
      row({
        category: "payment_admin",
        contact_email: "pay@bancochile.cl",
        subject: "FACTURA 6",
        next_action: "payment_admin",
      }),
    );
    expect(detail.recommendedStrategy).toMatch(/do not treat/i);
    expect(detail.linkedSection).toBe("payments-logistics");
  });

  it("deal_evidence_candidate strategy points to deals", () => {
    const detail = buildWarmCaseDetailView(
      row({
        category: "deal_evidence_candidate",
        subject: "Remite OC",
        account_name: "CEAF",
      }),
    );
    expect(detail.recommendedStrategy).toMatch(/commercial deals/i);
    expect(detail.recommendedStrategy).toMatch(/duplicate quote/i);
    expect(detail.linkedSection).toBe("deals");
  });

  it("sanitizeOperatorPreview redacts urls and long numeric ids", () => {
    const text = sanitizeOperatorPreview(
      "See https://mail.google.com/x and cuenta 12345678901234 RUT 12.345.678-9",
    );
    expect(text).not.toMatch(/https?:\/\//);
    expect(text).not.toMatch(/12345678901234/);
    expect(text).toContain("[redacted]");
  });
});
