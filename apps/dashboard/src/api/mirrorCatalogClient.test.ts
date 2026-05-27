import { afterEach, describe, expect, it, vi } from "vitest";
import { OperatorApiError } from "./operatorClient";
import {
  MIRROR_CATALOG_PRODUCTS_PATH,
  fetchCatalogProductDetailMirror,
  fetchCatalogProductsMirror,
  mirrorCatalogProductDetailUrl,
  mirrorCatalogProductsUrl,
} from "./mirrorCatalogClient";

describe("mirrorCatalogClient", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("mirrorCatalogProductsUrl supports list filters", () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "https://api.origenlab.cl");
    const url = mirrorCatalogProductsUrl({
      q: "IKA",
      brand: "CRTOP",
      equipment_class: "reactor",
      category_key: "lab_reactor",
      limit: 50,
    });
    expect(url).toContain(MIRROR_CATALOG_PRODUCTS_PATH);
    expect(url).toContain("q=IKA");
    expect(url).toContain("brand=CRTOP");
    expect(url).toContain("equipment_class=reactor");
    expect(url).toContain("category_key=lab_reactor");
    expect(url).toContain("limit=50");
  });

  it("mirrorCatalogProductDetailUrl encodes product key", () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "https://api.origenlab.cl");
    const url = mirrorCatalogProductDetailUrl("crtop-olt-hp-5l");
    expect(url).toContain("/mirror/catalog/products/crtop-olt-hp-5l");
  });

  it("fetchCatalogProductsMirror uses GET with credentials include", async () => {
    vi.stubEnv("MODE", "development");
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:5173" } });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        table_available: true,
        total: 0,
        limit: 100,
        items: [],
        data_source: "postgres_mirror",
        read_only: true,
        disclaimer: "ok",
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await fetchCatalogProductsMirror();
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
  });

  it("fetchCatalogProductDetailMirror throws OperatorApiError on failure", async () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8001");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 404, statusText: "missing", text: async () => "" }),
    );
    await expect(fetchCatalogProductDetailMirror("missing")).rejects.toBeInstanceOf(OperatorApiError);
  });
});
