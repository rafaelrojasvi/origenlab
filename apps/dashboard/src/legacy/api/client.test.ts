import { afterEach, describe, expect, it, vi } from "vitest";
import { apiUrl, fetchDashboardSummary, getApiBaseUrl } from "./client";

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("getApiBaseUrl strips trailing slash in production", () => {
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8001/");
    vi.stubEnv("MODE", "production");
    expect(getApiBaseUrl()).toBe("http://127.0.0.1:8001");
  });

  it("getApiBaseUrl is empty in dev for vite proxy", () => {
    vi.stubEnv("MODE", "development");
    expect(getApiBaseUrl()).toBe("");
  });

  it("apiUrl defaults to canonical mirror summary without scope param", () => {
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8001");
    vi.stubEnv("MODE", "production");
    const url = apiUrl("/mirror/dashboard/summary");
    expect(url).toBe("http://127.0.0.1:8001/mirror/dashboard/summary");
    expect(url).not.toContain("scope=");
  });

  it("apiUrl uses relative path in dev mode", () => {
    vi.stubEnv("MODE", "development");
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:5173" } });
    expect(apiUrl("/mirror/dashboard/summary")).toBe(
      "http://127.0.0.1:5173/mirror/dashboard/summary",
    );
  });

  it("apiUrl adds archive scope when requested", () => {
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8001");
    expect(apiUrl("/mirror/dashboard/summary", { scope: "archive" })).toContain("scope=archive");
  });

  it("apiUrl builds commercial purchase-events mirror path in dev mode", () => {
    vi.stubEnv("MODE", "development");
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:5173" } });
    const url = apiUrl("/mirror/commercial/purchase-events", { limit: 20 });
    expect(url).toBe("http://127.0.0.1:5173/mirror/commercial/purchase-events?limit=20");
  });

  it("fetchDashboardSummary calls canonical mirror endpoint by default", async () => {
    vi.stubEnv("MODE", "development");
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:5173" } });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ scope: "canonical", contact_count: 10 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const body = await fetchDashboardSummary();
    expect(body.scope).toBe("canonical");
    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:5173/mirror/dashboard/summary");
  });
});
