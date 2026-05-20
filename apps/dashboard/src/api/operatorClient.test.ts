import { afterEach, describe, expect, it, vi } from "vitest";
import {
  OperatorApiConfigError,
  OperatorApiError,
  fetchHealth,
  fetchOperatorStatus,
  getOperatorApiBaseUrl,
  operatorApiUrl,
  parseHealthResponse,
  parseOperatorStatusResponse,
} from "./operatorClient";

describe("operator API client", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.restoreAllMocks();
  });

  it("getOperatorApiBaseUrl throws in production when env is missing", () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "");
    expect(() => getOperatorApiBaseUrl()).toThrow(OperatorApiConfigError);
    expect(() => getOperatorApiBaseUrl()).toThrow(/VITE_ORIGENLAB_API_BASE_URL/);
  });

  it("getOperatorApiBaseUrl uses env in production (no localhost fallback)", () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "https://api.example.com/");
    expect(getOperatorApiBaseUrl()).toBe("https://api.example.com");
  });

  it("getOperatorApiBaseUrl strips trailing slash from env", () => {
    vi.stubEnv("MODE", "development");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://api.example.com/");
    expect(getOperatorApiBaseUrl()).toBe("http://api.example.com");
  });

  it("getOperatorApiBaseUrl is empty in dev when env unset (vite proxy)", () => {
    vi.stubEnv("MODE", "development");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "");
    expect(getOperatorApiBaseUrl()).toBe("");
  });

  it("operatorApiUrl builds operator status with staleness param", () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8001");
    const url = operatorApiUrl("/operator/status", { max_staleness_days: 14 });
    expect(url).toContain("/operator/status");
    expect(url).toContain("max_staleness_days=14");
  });

  it("parseHealthResponse normalizes backend", () => {
    const parsed = parseHealthResponse({
      ok: true,
      service: "origenlab-api",
      mode: "operator-postgres-readonly",
      backend: "postgres",
      postgres_configured: true,
    });
    expect(parsed.backend).toBe("postgres");
    expect(parsed.postgres_configured).toBe(true);
  });

  it("parseOperatorStatusResponse normalizes warnings", () => {
    const parsed = parseOperatorStatusResponse({
      verdict: "CAUTION",
      sqlite_path: "/data/emails.sqlite",
      campaign_mode: "warm",
      operator_focus: "follow-up",
      outbound_readiness: "mirror_stale",
      warnings: ["sync older than 7d"],
    });
    expect(parsed.verdict).toBe("CAUTION");
    expect(parsed.warnings).toEqual(["sync older than 7d"]);
  });

  it("fetchHealth uses GET only", async () => {
    vi.stubEnv("MODE", "development");
    vi.stubGlobal("window", { location: { origin: "http://127.0.0.1:5173" } });
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        service: "origenlab-api",
        mode: "operator-sqlite-readonly",
        backend: "sqlite",
        postgres_configured: false,
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    const body = await fetchHealth();
    expect(body.backend).toBe("sqlite");
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("fetchOperatorStatus throws OperatorApiError on failure", async () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8001");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503, statusText: "down", text: async () => "" }));
    await expect(fetchOperatorStatus()).rejects.toBeInstanceOf(OperatorApiError);
  });

  it("operatorApiUrl builds warm cases GET path", () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "https://api.example.com");
    const url = operatorApiUrl("/cases/warm", { limit: 30, positive_signal_only: false });
    expect(url).toContain("/cases/warm");
    expect(url).toContain("positive_signal_only=false");
  });

  it("operatorApiUrl builds equipment opportunities GET path", () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "https://api.example.com");
    const url = operatorApiUrl("/opportunities/equipment", { limit: 30 });
    expect(url).toContain("/opportunities/equipment");
    expect(url).toContain("limit=30");
  });
});
