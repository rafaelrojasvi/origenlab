import { afterEach, describe, expect, it, vi } from "vitest";
import { OperatorApiError } from "./operatorClient";
import {
  MIRROR_COMMERCIAL_DEALS_PATH,
  fetchCommercialDealsMirror,
  mirrorCommercialDealsUrl,
} from "./mirrorCommercialClient";

describe("mirrorCommercialClient", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it("module does not expose deal detail mirror fetch", async () => {
    const mod = await import("./mirrorCommercialClient");
    expect(Object.keys(mod).sort()).toEqual(
      ["MIRROR_COMMERCIAL_DEALS_PATH", "fetchCommercialDealsMirror", "getOperatorApiBaseUrl", "mirrorCommercialDealsUrl"].sort(),
    );
    expect(MIRROR_COMMERCIAL_DEALS_PATH).toBe("/mirror/commercial/deals");
    expect(MIRROR_COMMERCIAL_DEALS_PATH).not.toMatch(/\{deal_key\}|\/deals\//);
  });

  it("mirrorCommercialDealsUrl targets GET /mirror/commercial/deals only", () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "https://api.origenlab.cl");
    const url = mirrorCommercialDealsUrl(20);
    expect(url).toContain(MIRROR_COMMERCIAL_DEALS_PATH);
    expect(url).toContain("limit=20");
    expect(url).not.toContain("purchase-events");
    expect(url).not.toContain("/mirror/commercial/purchase");
  });

  it("fetchCommercialDealsMirror uses GET with credentials include", async () => {
    vi.stubEnv("MODE", "development");
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:5173" } });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        table_available: true,
        read_only: true,
        data_source: "postgres_mirror",
        total: 0,
        limit: 20,
        items: [],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const body = await fetchCommercialDealsMirror();
    expect(body.table_available).toBe(true);
    expect(body.data_source).toBe("postgres_mirror");
    expect(fetchMock.mock.calls[0][0]).toContain(MIRROR_COMMERCIAL_DEALS_PATH);
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
  });

  it("fetchCommercialDealsMirror throws OperatorApiError on failure", async () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8001");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, statusText: "down", text: async () => "" }),
    );
    await expect(fetchCommercialDealsMirror()).rejects.toBeInstanceOf(OperatorApiError);
  });
});
