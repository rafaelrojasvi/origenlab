import { afterEach, describe, expect, it, vi } from "vitest";
import { apiUrl, fetchDashboardSummary, getApiBaseUrl } from "./client";

describe("api client", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("getApiBaseUrl strips trailing slash", () => {
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8000/");
    expect(getApiBaseUrl()).toBe("http://127.0.0.1:8000");
  });

  it("apiUrl defaults to canonical summary without scope param", () => {
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8000");
    const url = apiUrl("/dashboard/summary");
    expect(url).toBe("http://127.0.0.1:8000/dashboard/summary");
    expect(url).not.toContain("scope=");
  });

  it("apiUrl adds archive scope when requested", () => {
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8000");
    expect(apiUrl("/dashboard/summary", { scope: "archive" })).toContain("scope=archive");
  });

  it("fetchDashboardSummary calls canonical endpoint by default", async () => {
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8000");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ scope: "canonical", contact_count: 10 }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const body = await fetchDashboardSummary();
    expect(body.scope).toBe("canonical");
    expect(fetchMock.mock.calls[0][0]).toBe("http://127.0.0.1:8000/dashboard/summary");
  });
});
