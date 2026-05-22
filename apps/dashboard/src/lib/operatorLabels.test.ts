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
      "Requiere cotización proveedor",
    );
    expect(formatOperatorToken("no_verified_buyer_email", "equipment_contact_status").label).toBe(
      "Sin email verificado",
    );
  });

  it("falls back to spaced raw token for unknown values", () => {
    const out = formatOperatorToken("custom_token", "warm_status");
    expect(out.raw).toBe("custom_token");
    expect(out.label).toBe("custom token");
  });
});
