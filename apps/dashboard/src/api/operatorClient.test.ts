import { afterEach, describe, expect, it, vi } from "vitest";
import {
  OperatorApiConfigError,
  OperatorApiError,
  contactDetailPath,
  fetchContactProfile,
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
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
  });

  it("all operator API fetches send credentials include for Cloudflare Access", async () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "https://api.origenlab.cl");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        verdict: "OK",
        sqlite_path: "",
        campaign_mode: null,
        operator_focus: null,
        outbound_readiness: "n/a",
        warnings: [],
      }),
    });
    vi.stubGlobal("fetch", fetchMock);

    await fetchOperatorStatus();
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({
        method: "GET",
        credentials: "include",
        headers: { Accept: "application/json" },
      }),
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
    const url = operatorApiUrl("/cases/warm", { limit: 100, positive_signal_only: false });
    expect(url).toContain("/cases/warm");
    expect(url).toContain("positive_signal_only=false");
    expect(url).toContain("limit=100");
  });

  it("contactDetailPath URL-encodes email for GET /contacts/{email}", () => {
    expect(contactDetailPath("buyer+tag@acme.cl")).toBe(
      "/contacts/buyer%2Btag%40acme.cl",
    );
    expect(contactDetailPath("  buyer@acme.cl  ")).toBe("/contacts/buyer%40acme.cl");
  });

  it("contactDetailPath rejects invalid email before fetch", () => {
    expect(() => contactDetailPath("not-an-email")).toThrow(OperatorApiError);
    expect(() => contactDetailPath("")).toThrow(OperatorApiError);
  });

  it("fetchContactProfile uses GET only and handles API errors", async () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8001");
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 422,
      statusText: "Unprocessable",
      text: async () => "invalid email",
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchContactProfile("x@y.z")).rejects.toBeInstanceOf(OperatorApiError);
    expect(fetchMock.mock.calls[0][1]).toEqual(
      expect.objectContaining({ method: "GET", credentials: "include" }),
    );
    expect(fetchMock.mock.calls[0][0]).toContain("/contacts/");
  });

  it("fetchContactProfile parses successful response", async () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8001");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({
          meta: { data_source: "sqlite", read_only: true, reduced_mode: false, note: "" },
          contact: {
            email: "a@b.cl",
            normalized_email: "a@b.cl",
            name: "",
            domain: "",
            organization_name: "",
            organization_domain: "",
            last_seen_at: null,
            first_seen_at: null,
            message_count: 0,
          },
          outreach: {
            state: null,
            last_contacted_at: null,
            source: null,
            notes: null,
            do_not_repeat: false,
            suppressed_email: false,
            suppressed_domain: false,
          },
          sent_history: { sent_count: 0, latest_sent_at: null, latest_subject: null },
          warnings: [],
        }),
      }),
    );

    const profile = await fetchContactProfile("a@b.cl");
    expect(profile.contact.normalized_email).toBe("a@b.cl");
  });

  it("operatorApiUrl builds equipment opportunities GET path", () => {
    vi.stubEnv("MODE", "production");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "https://api.example.com");
    const url = operatorApiUrl("/opportunities/equipment", { limit: 30 });
    expect(url).toContain("/opportunities/equipment");
    expect(url).toContain("limit=30");
  });
});
