import { describe, expect, it } from "vitest";
import type { WarmCaseItem } from "../api/commercialTypes";
import {
  buildWarmCaseDetailView,
  sanitizeOperatorPreview,
} from "./warmCaseDetailStrategy";

function row(overrides: Partial<WarmCaseItem>): WarmCaseItem {
  return {
    case_id: "1",
    last_email_id: 1,
    last_seen_at: null,
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

describe("warmCaseDetailStrategy (español)", () => {
  it("estrategia de cotización de proveedor", () => {
    const detail = buildWarmCaseDetailView(row({ category: "supplier_quote_received" }));
    expect(detail.recommendedStrategy).toMatch(/oportunidad de cliente/i);
    expect(detail.linkedSection).toBe("suppliers");
    expect(detail.categoryLabel).toBe("Cotización de proveedor recibida");
  });

  it("estrategia de pago administrativo", () => {
    const detail = buildWarmCaseDetailView(
      row({
        category: "payment_admin",
        contact_email: "pay@bancochile.cl",
        subject: "FACTURA 6",
      }),
    );
    expect(detail.recommendedStrategy).toMatch(/no uses este hilo para cotizar/i);
    expect(detail.linkedSection).toBe("payments-logistics");
  });

  it("estrategia de evidencia de negocio", () => {
    const detail = buildWarmCaseDetailView(
      row({
        category: "deal_evidence_candidate",
        subject: "Remite OC",
        account_name: "CEAF",
      }),
    );
    expect(detail.recommendedStrategy).toMatch(/Negocios/i);
    expect(detail.linkedSection).toBe("deals");
  });

  it("sanitizeOperatorPreview oculta datos sensibles", () => {
    const text = sanitizeOperatorPreview(
      "See https://mail.google.com/x and cuenta 12345678901234",
    );
    expect(text).not.toMatch(/https?:\/\//);
    expect(text).toContain("[oculto]");
  });
});
