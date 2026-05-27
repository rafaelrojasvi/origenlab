import { describe, expect, it } from "vitest";
import {
  buildListOfferSummary,
  formatCatalogDate,
  formatCatalogMoney,
  formatCatalogQuantity,
} from "./catalogFormat";
import { crtopDetailFixture, ikaDetailFixture } from "../test/fixtures/catalogMirrorFixtures";

describe("catalogFormat", () => {
  it("formats USD with thousands separator", () => {
    expect(formatCatalogMoney("10600.00", "USD")).toBe("USD 10.600,00");
  });

  it("formats null currency as Moneda pendiente label path", () => {
    expect(formatCatalogMoney("112.00", null)).toBe("112,00");
  });

  it("formats ISO dates in Spanish", () => {
    expect(formatCatalogDate("2026-05-27T00:00:00Z")).toBe("27 may 2026");
  });

  it("formats quantity as unidades", () => {
    expect(formatCatalogQuantity("3", "ea")).toBe("3 unidades");
    expect(formatCatalogQuantity("1", "ea")).toBe("1 unidad");
  });

  it("builds CRTOP list offer summary", () => {
    const detail = crtopDetailFixture().product!;
    expect(buildListOfferSummary(detail)).toContain("USD 10.600,00");
    expect(buildListOfferSummary(detail)).toContain("EXW");
    expect(buildListOfferSummary(detail)).toContain("1 unidad");
  });

  it("builds IKA list offer summary", () => {
    const detail = ikaDetailFixture().product!;
    const summary = buildListOfferSummary(detail);
    expect(summary).toContain("112,00");
    expect(summary).toContain("Moneda pendiente");
    expect(summary).toContain("revisar");
  });
});
