import { describe, expect, it } from "vitest";
import {
  CATALOG_FORBIDDEN_KEYS,
  CATALOG_FORBIDDEN_PROSE_ARTIFACTS,
  parseCatalogProductDetailResponse,
  parseCatalogProductsListResponse,
} from "./catalogParse";
import { crtopDetailFixture, catalogListFixture } from "../test/fixtures/catalogMirrorFixtures";

describe("catalogParse", () => {
  it("strips forbidden keys from list and detail payloads", () => {
    const raw = {
      table_available: true,
      total: 1,
      limit: 100,
      items: [
        {
          product_key: "x",
          display_name: "Test",
          product_kind: "reagent",
          confidence: "operator_confirmed",
          gmail_url: "https://mail.google.com/mail/u/0/#inbox/abc",
          evidence_email_id: "secret",
          transfer_id: "t-1",
          body: "should not appear",
        },
      ],
      disclaimer: "ok",
    };
    const parsed = parseCatalogProductsListResponse(raw);
    const blob = JSON.stringify(parsed);
    for (const key of CATALOG_FORBIDDEN_KEYS) {
      expect(blob).not.toContain(`"${key}"`);
    }
    expect(blob).not.toContain("mail.google");
    expect(blob).not.toContain("should not appear");
  });

  it("redacts forbidden value patterns in prose fields", () => {
    const parsed = parseCatalogProductDetailResponse({
      table_available: true,
      product: {
        product_key: "x",
        display_name: "Cuenta bancaria SWIFT IBAN",
        product_kind: "reagent",
        confidence: "operator_confirmed",
        public_summary: "Beneficiario RUT 12.345.678-9",
      },
    });
    expect(parsed.product?.display_name).toBe("Producto sin nombre");
    expect(parsed.product?.public_summary).toBeNull();
  });

  it("preserves clean catalog prose without joined artifacts", () => {
    const list = parseCatalogProductsListResponse(catalogListFixture());
    const detail = parseCatalogProductDetailResponse(crtopDetailFixture());
    const blob = JSON.stringify({ list, detail }).toLowerCase();
    for (const artifact of CATALOG_FORBIDDEN_PROSE_ARTIFACTS) {
      expect(blob).not.toContain(artifact.toLowerCase());
    }
    expect(detail.product?.price_snapshots[0]?.amount_decimal).toBe("10600.00");
  });
});
