import { describe, expect, it } from "vitest";
import {
  dealStatusLabel,
  freightStatusLabel,
  formatProductLineLabel,
  marginStatusLabel,
  reconciliationStatusLabel,
  resolveDealProductLines,
} from "./commercialDealFormat";

describe("commercialDealFormat status labels", () => {
  it("maps audit deal status tokens to Spanish", () => {
    expect(dealStatusLabel("logistics_pending")).toBe("Logística pendiente");
    expect(marginStatusLabel("needs_review")).toBe("Requiere revisión");
    expect(reconciliationStatusLabel("reconciled_excluding_supplier_freight")).toBe(
      "Conciliado sin flete proveedor",
    );
    expect(freightStatusLabel("dhl_account_or_external_freight")).toBe("DHL / flete externo");
    expect(
      dealStatusLabel("paid_by_client__supplier_payment_sent__logistics_pending"),
    ).toBe("Cliente pagó · proveedor pagado parcial · logística pendiente");
  });
});

describe("resolveDealProductLines", () => {
  it("falls back to CEAF × SERVA product lines when API omits summaries", () => {
    const lines = resolveDealProductLines([], "CEAF", "SERVA Electrophoresis GmbH");
    expect(lines.map((l) => l.product_name)).toEqual([
      "BlueSlick™ 250 ml",
      "TEMED 25 ml",
      "Envío cliente",
    ]);
    expect(formatProductLineLabel(lines[2])).toContain("20.000");
  });
});
