import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EquipmentOpportunitiesResponse, WarmCasesResponse } from "../api/commercialTypes";
import type { TodayPanelData } from "../api/operatorTypes";
import { TodayPage } from "./TodayPage";

const panelSqlite: TodayPanelData = {
  health: {
    ok: true,
    service: "origenlab-api",
    mode: "operator-sqlite-readonly",
    backend: "sqlite",
    postgres_configured: false,
  },
  operator: {
    verdict: "READY",
    sqlite_path: "/tmp/emails.sqlite",
    campaign_mode: "default",
    operator_focus: "warm_cases",
    outbound_readiness: "ready",
    warnings: ["low volume this week"],
  },
};

const warmPayload: WarmCasesResponse = {
  meta: {
    data_source: "sqlite",
    read_only: true,
    reduced_mode: false,
    count: 1,
    enrichment_available: false,
    note: "",
  },
  items: [
    {
      case_id: "gmail-contacto-1",
      last_email_id: 1,
      last_seen_at: "2026-05-19T10:00:00-04:00",
      account_name: "ACME",
      contact_email: "buyer@acme.cl",
      subject: "Quote follow-up",
      category: "client_reply",
      status: "open",
      next_action: "reply",
      equipment_signal: "balance",
      snippet: "preview text",
      gmail_url: null,
    },
  ],
};

const equipmentPayload: EquipmentOpportunitiesResponse = {
  meta: {
    data_source: "active_current_csv",
    read_only: true,
    count: 1,
    source_path: "/secret/path/queue.csv",
    campaign_mode: "equipment_first",
    reduced_mode: false,
    note: "",
  },
  items: [
    {
      priority_rank: 1,
      codigo_licitacion: "LP-99",
      buyer: "Hospital Regional",
      region: "RM",
      close_date: "15/06/2026",
      equipment_category: "incubator",
      item_description: "CO2 incubator",
      next_action: "monitor",
      safe_channel: "mercado_publico_bid",
      supplier_needed: "no",
      contact_status: "pending",
      contact_email: "procurement@hospital.cl",
      operator_note: "intel",
    },
  ],
};

vi.mock("../api/operatorClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/operatorClient")>();
  return {
    ...actual,
    fetchTodayPanel: vi.fn(),
    fetchWarmCases: vi.fn(),
    fetchEquipmentOpportunities: vi.fn(),
    fetchContactProfile: vi.fn(),
    getOperatorApiBaseUrl: vi.fn(() => ""),
  };
});

import {
  fetchContactProfile,
  fetchEquipmentOpportunities,
  fetchTodayPanel,
  fetchWarmCases,
} from "../api/operatorClient";

describe("TodayPage", () => {
  beforeEach(() => {
    vi.stubEnv("MODE", "development");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
  });

  function mockAllOk() {
    vi.mocked(fetchTodayPanel).mockResolvedValue(panelSqlite);
    vi.mocked(fetchWarmCases).mockResolvedValue(warmPayload);
    vi.mocked(fetchEquipmentOpportunities).mockResolvedValue(equipmentPayload);
  }

  it("shows legacy :8000 dev warning when env points at wrong port", () => {
    vi.stubEnv("MODE", "development");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "http://127.0.0.1:8000");
    mockAllOk();
    render(<TodayPage />);
    screen.getByText(/Local dev misconfiguration/);
    screen.getByText(/unset VITE_ORIGENLAB_API_BASE_URL/);
  });

  it("renders Dashboard-0 operator status and Dashboard-1 tables", async () => {
    mockAllOk();
    render(<TodayPage />);

    await waitFor(() => {
      screen.getByText("READY");
    });

    screen.getByText("SQLite");
    screen.getByText(/Casos tibios \/ Warm cases/);
    screen.getByText(/Oportunidades de equipos/);
    screen.getByText("buyer@acme.cl");
    screen.getByText("Hospital Regional");
    expect(screen.queryByText(/\/tmp\/emails\.sqlite/)).toBeNull();
    expect(screen.queryByText(/\/secret\/path/)).toBeNull();
    expect(screen.queryByText(/body_preview/)).toBeNull();
  });

  it("shows postgres mirror labels when backend is postgres", async () => {
    vi.mocked(fetchTodayPanel).mockResolvedValue({
      ...panelSqlite,
      health: {
        ...panelSqlite.health,
        backend: "postgres",
        mode: "operator-postgres-readonly",
        postgres_configured: true,
      },
      operator: { ...panelSqlite.operator, verdict: "CAUTION" },
    });
    vi.mocked(fetchWarmCases).mockResolvedValue({
      ...warmPayload,
      meta: { ...warmPayload.meta, data_source: "postgres_mirror" },
    });
    vi.mocked(fetchEquipmentOpportunities).mockResolvedValue({
      ...equipmentPayload,
      meta: { ...equipmentPayload.meta, data_source: "postgres_mirror" },
    });

    render(<TodayPage />);

    await waitFor(() => {
      screen.getByText("Postgres mirror");
    });
    expect(screen.getAllByText(/not send\/outreach truth/).length).toBeGreaterThan(0);
  });

  it("renders operator error while tables can still load", async () => {
    vi.mocked(fetchTodayPanel).mockRejectedValue(new Error("panel down"));
    vi.mocked(fetchWarmCases).mockResolvedValue(warmPayload);
    vi.mocked(fetchEquipmentOpportunities).mockResolvedValue(equipmentPayload);

    render(<TodayPage />);

    await waitFor(() => {
      screen.getByText(/Could not load operator status/);
    });
    screen.getByText("buyer@acme.cl");
  });

  it("renders warm cases error state", async () => {
    mockAllOk();
    vi.mocked(fetchWarmCases).mockRejectedValue(new Error("warm failed"));

    render(<TodayPage />);

    await waitFor(() => {
      screen.getByText(/Warm cases: warm failed/);
    });
    screen.getByRole("button", { name: "Retry" });
  });

  it("opens read-only contact profile from warm case email", async () => {
    mockAllOk();
    vi.mocked(fetchContactProfile).mockResolvedValue({
      meta: { data_source: "sqlite", read_only: true, reduced_mode: false, note: "" },
      contact: {
        email: "buyer@acme.cl",
        normalized_email: "buyer@acme.cl",
        name: "Buyer",
        domain: "acme.cl",
        organization_name: "ACME",
        organization_domain: "acme.cl",
        last_seen_at: null,
        first_seen_at: null,
        message_count: 1,
      },
      outreach: {
        state: "open",
        last_contacted_at: null,
        source: null,
        notes: null,
        do_not_repeat: false,
        suppressed_email: false,
        suppressed_domain: false,
      },
      sent_history: { sent_count: 0, latest_sent_at: null, latest_subject: null },
      warnings: [],
    });

    render(<TodayPage />);
    await waitFor(() => screen.getByText("READY"));

    fireEvent.click(screen.getByRole("button", { name: "buyer@acme.cl" }));

    await waitFor(() => {
      screen.getByText("Read-only contact profile");
      screen.getByText("Buyer");
    });
    expect(screen.queryByText(/sqlite_path|source_path|body_preview/i)).toBeNull();
  });

  it("opens contact profile from equipment row when email exists", async () => {
    mockAllOk();
    vi.mocked(fetchContactProfile).mockResolvedValue({
      meta: { data_source: "sqlite", read_only: true, reduced_mode: false, note: "" },
      contact: {
        email: "procurement@hospital.cl",
        normalized_email: "procurement@hospital.cl",
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
    });

    render(<TodayPage />);
    await waitFor(() => screen.getByText("Hospital Regional"));

    fireEvent.click(screen.getByRole("button", { name: "procurement@hospital.cl" }));

    await waitFor(() => {
      screen.getByText("Read-only contact profile");
    });
  });
});
