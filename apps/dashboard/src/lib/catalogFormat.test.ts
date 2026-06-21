import { describe, expect, it } from "vitest";
import {
  buildListCommercialDataSummary,
  buildListOfferSummary,
  catalogWebsiteHref,
  formatCommercialHistoryAmount,
  formatCatalogDate,
  formatCatalogMoney,
  formatCatalogQuantity,
} from "./catalogFormat";
import {
  crtopDetailFixture,
  ikaDetailFixture,
  servaBlueslickDetailFixture,
  servaTemedDetailFixture,
} from "../test/fixtures/catalogMirrorFixtures";

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

  it("builds SERVA table commercial summaries", () => {
    const blueslick = buildListOfferSummary(servaBlueslickDetailFixture().product!);
    expect(blueslick).toContain("Vendido a CEAF");
    expect(blueslick).toContain("Costo proveedor EUR 117,00");
    expect(blueslick).not.toContain("Sin oferta");

    const temed = buildListOfferSummary(servaTemedDetailFixture().product!);
    expect(temed).toContain("Vendido a CEAF");
    expect(temed).toContain("Costo proveedor EUR 31,00");
  });

  it("returns Sin dato comercial only without quotes or history", () => {
    expect(
      buildListOfferSummary({
        ...servaBlueslickDetailFixture().product!,
        commercial_history: [],
        supplier_offers: [],
        price_snapshots: [],
      }),
    ).toBe("Sin dato comercial registrado");
    expect(buildListCommercialDataSummary(servaBlueslickDetailFixture().product!)).toContain(
      "Vendido a CEAF",
    );
  });

  it("formats CLP and EUR commercial history amounts", () => {
    const detail = servaBlueslickDetailFixture().product!;
    const client = detail.commercial_history.find((h) => h.line_side === "client")!;
    const supplier = detail.commercial_history.find((h) => h.line_side === "supplier")!;
    expect(formatCommercialHistoryAmount(client)).toBe("$695.000");
    expect(formatCommercialHistoryAmount(supplier)).toBe("EUR 117,00");
  });

  it("builds IKA list offer summary", () => {
    const detail = ikaDetailFixture().product!;
    const summary = buildListOfferSummary(detail);
    expect(summary).toContain("112,00");
    expect(summary).toContain("Moneda pendiente");
    expect(summary).toContain("revisar");
  });

  describe("catalogWebsiteHref", () => {
    it("builds origenlab product URLs from safe slugs", () => {
      expect(catalogWebsiteHref("blueslick-42500")).toBe(
        "https://origenlab.cl/productos/blueslick-42500",
      );
      expect(catalogWebsiteHref("temed-25ml")).toBe("https://origenlab.cl/productos/temed-25ml");
      expect(catalogWebsiteHref("  blueslick-42500  ")).toBe(
        "https://origenlab.cl/productos/blueslick-42500",
      );
    });

    it("allows validated absolute https URLs", () => {
      expect(catalogWebsiteHref("https://origenlab.cl/productos/blueslick-42500")).toBe(
        "https://origenlab.cl/productos/blueslick-42500",
      );
      expect(catalogWebsiteHref("HTTPS://origenlab.cl/productos/foo")).toBe(
        "https://origenlab.cl/productos/foo",
      );
    });

    it("returns null for empty or missing slugs", () => {
      expect(catalogWebsiteHref(null)).toBeNull();
      expect(catalogWebsiteHref(undefined)).toBeNull();
      expect(catalogWebsiteHref("")).toBeNull();
      expect(catalogWebsiteHref("   ")).toBeNull();
    });

    it("rejects dangerous URL schemes and protocol-relative links", () => {
      expect(catalogWebsiteHref("javascript:alert(1)")).toBeNull();
      expect(catalogWebsiteHref("data:text/html,<script>alert(1)</script>")).toBeNull();
      expect(catalogWebsiteHref("vbscript:msgbox(1)")).toBeNull();
      expect(catalogWebsiteHref("//evil.example/phish")).toBeNull();
    });

    it("rejects http and malformed absolute URLs", () => {
      expect(catalogWebsiteHref("http://origenlab.cl/productos/foo")).toBeNull();
      expect(catalogWebsiteHref("https:")).toBeNull();
      expect(catalogWebsiteHref("https://")).toBeNull();
      expect(catalogWebsiteHref("not a url")).toBeNull();
      expect(catalogWebsiteHref("foo:bar")).toBeNull();
    });

    it("rejects whitespace tricks, control characters, and unsafe slug shapes", () => {
      expect(catalogWebsiteHref("blue slick")).toBeNull();
      expect(catalogWebsiteHref("blueslick\n-42500")).toBeNull();
      expect(catalogWebsiteHref("blueslick\t-42500")).toBeNull();
      expect(catalogWebsiteHref("../escape")).toBeNull();
      expect(catalogWebsiteHref("foo/bar")).toBeNull();
      expect(catalogWebsiteHref("-leading-hyphen")).toBeNull();
      expect(catalogWebsiteHref("slug%2ftraversal")).toBeNull();
    });

    it("rejects https URLs with embedded credentials", () => {
      expect(catalogWebsiteHref("https://user:pass@origenlab.cl/productos/foo")).toBeNull();
    });
  });
});
