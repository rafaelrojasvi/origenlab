import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { EquipmentOpportunitiesResponse, WarmCasesResponse } from "../api/commercialTypes";
import type { TodayPanelData } from "../api/operatorTypes";
import { DashboardApp } from "./DashboardApp";

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
    warnings: [],
  },
};

const warmPayload: WarmCasesResponse = {
  meta: {
    data_source: "sqlite",
    read_only: true,
    reduced_mode: false,
    count: 4,
    enrichment_available: false,
    note: "",
  },
  items: [
    {
      case_id: "client-1",
      last_email_id: 1,
      last_seen_at: "2026-05-19T10:00:00-04:00",
      account_name: "ACME",
      contact_email: "buyer@acme.cl",
      subject: "Quote follow-up",
      category: "client_opportunity",
      status: "open",
      next_action: "reply",
      equipment_signal: "balance",
      snippet: "preview text",
      gmail_url: null,
    },
    {
      case_id: "supplier-1",
      last_email_id: 2,
      last_seen_at: "2026-05-18T10:00:00-04:00",
      account_name: "IKA",
      contact_email: "beatriz.bonon@ika.net.br",
      subject: "RE: price response",
      category: "supplier_quote_received",
      status: "waiting",
      next_action: "wait",
      equipment_signal: "",
      snippet: "supplier preview",
      gmail_url: null,
    },
    {
      case_id: "pay-1",
      last_email_id: 3,
      last_seen_at: "2026-05-17T10:00:00-04:00",
      account_name: "Banco",
      contact_email: "serviciodetransferencias@bancochile.cl",
      subject: "FACTURA 6",
      category: "payment_admin",
      status: "open",
      next_action: "review",
      equipment_signal: "",
      snippet: "payment preview",
      gmail_url: null,
    },
    {
      case_id: "dhl-1",
      last_email_id: 4,
      last_seen_at: "2026-05-16T10:00:00-04:00",
      account_name: "DHL",
      contact_email: "monica.silva@dhl.com",
      subject: "PROPUESTA COMERCIAL DHL",
      category: "logistics_admin",
      status: "open",
      next_action: "review",
      equipment_signal: "",
      snippet: "logistics preview",
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

vi.mock("../api/mirrorCommercialClient", () => ({
  fetchCommercialDealsMirror: vi.fn(),
}));

import {
  fetchEquipmentOpportunities,
  fetchTodayPanel,
  fetchWarmCases,
} from "../api/operatorClient";
import { fetchCommercialDealsMirror } from "../api/mirrorCommercialClient";

function mockAllOk() {
  vi.mocked(fetchTodayPanel).mockResolvedValue(panelSqlite);
  vi.mocked(fetchWarmCases).mockResolvedValue(warmPayload);
  vi.mocked(fetchEquipmentOpportunities).mockResolvedValue(equipmentPayload);
  vi.mocked(fetchCommercialDealsMirror).mockResolvedValue({
    table_available: true,
    read_only: true,
    data_source: "postgres_mirror",
    total: 1,
    limit: 20,
    items: [
      {
        client_org_name: "CEAF",
        supplier_org_name: "SERVA",
        deal_status: "logistics_pending",
        margin_status: "needs_review",
        reconciliation_status: "reconciled",
        freight_status: "pending",
        client_sale_net_clp: 1_260_000,
        client_sale_gross_clp: 1_499_400,
        client_payment_received_clp: 1_499_400,
        supplier_invoice_total_decimal: "363.00",
        supplier_amount_paid_decimal: "218.00",
        margin_net_clp: null,
        margin_pct: null,
        margin_blockers: [],
        updated_at: "2026-05-22T12:00:00+00:00",
      },
    ],
  });
}

async function navigateTo(label: string) {
  const nav = screen.getByRole("navigation", { name: "Dashboard navigation" });
  fireEvent.click(within(nav).getByRole("link", { name: label }));
  await waitFor(() => {
    expect(screen.getByRole("heading", { level: 1, name: label })).toBeTruthy();
  });
}

describe("DashboardApp shell (Phase 7B.1)", () => {
  beforeEach(() => {
    vi.stubEnv("MODE", "development");
    vi.stubEnv("VITE_ORIGENLAB_API_BASE_URL", "");
    window.location.hash = "#/";
    mockAllOk();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.clearAllMocks();
    window.location.hash = "";
  });

  it("sidebar renders all sections", async () => {
    render(<DashboardApp />);
    await waitFor(() => screen.getByText("READY"));

    const nav = screen.getByRole("navigation", { name: "Dashboard navigation" });
    for (const label of [
      "Today",
      "Inbox triage",
      "Opportunities",
      "Deals",
      "Suppliers",
      "Tenders",
      "Payments & logistics",
      "Contacts",
      "System",
    ]) {
      expect(within(nav).getByRole("link", { name: label })).toBeTruthy();
    }
  });

  it("Today summary renders queue count cards", async () => {
    render(<DashboardApp />);
    await waitFor(() => screen.getByText("READY"));

    screen.getByText("Queue summary");
    screen.getByText("Client opportunities");
    screen.getByText("Supplier quotes / follow-ups");
    screen.getByText("Deal evidence (warm)");
    screen.getByText("Deal evidence (warm)");
    screen.getByText("Tenders / equipment");
    expect(screen.queryByText(/Casos tibios \/ Warm cases/)).toBeNull();
  });

  it("Inbox page contains warm cases table", async () => {
    render(<DashboardApp />);
    await waitFor(() => screen.getByText("READY"));

    await navigateTo("Inbox triage");
    await waitFor(() => {
      screen.getByText("buyer@acme.cl");
    });
  });

  it("Suppliers page excludes client opportunities", async () => {
    render(<DashboardApp />);
    await waitFor(() => screen.getByText("READY"));

    await navigateTo("Suppliers");
    await waitFor(() => {
      screen.getByText("beatriz.bonon@ika.net.br");
    });
    expect(screen.queryByText("buyer@acme.cl")).toBeNull();
  });

  it("Payments & logistics excludes supplier and client rows", async () => {
    render(<DashboardApp />);
    await waitFor(() => screen.getByText("READY"));

    await navigateTo("Payments & logistics");
    await waitFor(() => {
      screen.getByText("serviciodetransferencias@bancochile.cl");
      screen.getByText("monica.silva@dhl.com");
    });
    expect(screen.queryByText("buyer@acme.cl")).toBeNull();
    expect(screen.queryByText("beatriz.bonon@ika.net.br")).toBeNull();
  });

  it("Deals page renders commercial deal table", async () => {
    render(<DashboardApp />);
    await waitFor(() => screen.getByText("READY"));

    await navigateTo("Deals");
    await waitFor(() => {
      screen.getByText("Commercial deals");
      screen.getByText("CEAF");
      screen.getByText("SERVA");
    });
  });

  it("global Refresh button reloads data", async () => {
    render(<DashboardApp />);
    await waitFor(() => screen.getByText("READY"));

    vi.mocked(fetchTodayPanel).mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));

    await waitFor(() => {
      expect(fetchTodayPanel).toHaveBeenCalled();
    });
  });
});
