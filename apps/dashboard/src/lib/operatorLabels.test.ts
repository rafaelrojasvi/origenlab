import { describe, expect, it } from "vitest";
import { formatOperatorToken } from "./operatorLabels";

describe("operatorLabels", () => {
  it("maps warm category and status tokens", () => {
    expect(formatOperatorToken("waiting_client", "warm_category").label).toBe("Esperando cliente");
    expect(formatOperatorToken("quote_sent", "warm_category").label).toBe("Cotización enviada");
    expect(formatOperatorToken("waiting_client", "warm_category").raw).toBe("waiting_client");
  });

  it("maps equipment action and contact status tokens", () => {
    expect(formatOperatorToken("needs_supplier_quote", "equipment_next_action").label).toBe(
      "Requiere cotización de proveedor",
    );
    expect(formatOperatorToken("no_verified_buyer_email", "equipment_contact_status").label).toBe(
      "Sin correo verificado del comprador",
    );
  });

  it("maps audit warm categories and next actions", () => {
    expect(formatOperatorToken("vendor_logistics", "warm_category").label).toContain("Logística");
    expect(formatOperatorToken("payment_admin", "warm_category").label).toContain("Pago");
    expect(formatOperatorToken("auto_reply", "warm_category").label).toBe("Respuesta automática");
    expect(formatOperatorToken("vendor_logistics", "warm_next_action").label).toContain("logística");
    expect(formatOperatorToken("payment_admin", "warm_next_action").label).toContain("pago");
  });

  it("falls back to Sin clasificar for unknown values", () => {
    const out = formatOperatorToken("custom_token", "warm_status");
    expect(out.raw).toBe("custom_token");
    expect(out.label).toBe("Sin clasificar");
    expect(out.title).toMatch(/no mapeada/i);
  });

  it("shows human-readable warm next-action sentences directly", () => {
    expect(
      formatOperatorToken(
        "Cotización enviada; monitorear respuesta del cliente.",
        "warm_next_action",
      ).label,
    ).toBe("Cotización enviada; monitorear respuesta del cliente.");
  });

  it("shows human-readable equipment next-action sentences directly", () => {
    expect(
      formatOperatorToken("Revisar ficha técnica antes de cotizar.", "equipment_next_action").label,
    ).toBe("Revisar ficha técnica antes de cotizar.");
  });

  it("keeps mapped warm next-action tokens", () => {
    expect(formatOperatorToken("follow", "warm_next_action").label).toBe("Dar seguimiento");
    expect(formatOperatorToken("supplier_reply", "warm_next_action").label).toBe(
      "Revisar propuesta del proveedor",
    );
  });

  it("falls back to Sin clasificar for unknown non-action tokens", () => {
    expect(formatOperatorToken("custom_token", "warm_category").label).toBe("Sin clasificar");
  });
});
