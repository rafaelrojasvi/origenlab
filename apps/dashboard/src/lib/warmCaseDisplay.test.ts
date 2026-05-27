import { describe, expect, it } from "vitest";
import type { WarmCaseItem } from "../api/commercialTypes";
import { formatWarmCaseSubjectLine, warmCaseSubjectShowsInlineGroupCount } from "./warmCaseDisplay";

function crtopRow(partial: Partial<WarmCaseItem>): WarmCaseItem {
  return {
    case_id: "gmail-contacto-1",
    last_email_id: 1,
    last_seen_at: null,
    account_name: "CRTOP",
    contact_email: "ariel@crtopmachine.com",
    subject: "Re: Thank you very much for your inquiry about our reactor.",
    category: "supplier_quote_received",
    status: "open",
    next_action: "",
    equipment_signal: "reactor",
    snippet: "",
    gmail_url: null,
    grouped_email_count: 6,
    ...partial,
  };
}

describe("formatWarmCaseSubjectLine", () => {
  it("formats grouped CRTOP as product line with email count", () => {
    const line = formatWarmCaseSubjectLine(crtopRow({}));
    expect(line).toBe("CRTOP — Reactor OLT-HP-5L ×6");
    expect(warmCaseSubjectShowsInlineGroupCount(crtopRow({}))).toBe(true);
  });

  it("leaves non-CRTOP subjects unchanged", () => {
    const line = formatWarmCaseSubjectLine(
      crtopRow({
        contact_email: "buyer@hospital.cl",
        account_name: "Hospital",
        subject: "Cotización incubadora",
        grouped_email_count: 2,
      }),
    );
    expect(line).toBe("Cotización incubadora");
    expect(warmCaseSubjectShowsInlineGroupCount(crtopRow({
      contact_email: "buyer@hospital.cl",
      account_name: "Hospital",
      subject: "Cotización incubadora",
      grouped_email_count: 2,
    }))).toBe(false);
  });
});
