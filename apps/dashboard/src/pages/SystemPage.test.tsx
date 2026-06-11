import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DashboardDataContext } from "../context/DashboardDataContext";
import { SystemPage } from "./SystemPage";

const BASE_AUTOMATION_STATUS = {
  generated_at_utc: "2026-06-10T18:30:00+00:00",
  active_current_dir: "/hidden/active/current",
  verdict: "healthy",
  daily_core: {
    exists: true,
    status: "success",
    returncode: 0,
    generated_at_utc: "2026-06-10T18:12:48+00:00",
    age_seconds: 1032,
    steps: 8,
  },
  mail_auto_refresh: {
    state_exists: true,
    paused: false,
    lock_live: false,
    dirty: false,
    pending: false,
    last_successful_refresh_at: "2026-06-10T18:12:48+00:00",
    last_seen_inbox_total: 403,
    last_seen_sent_total: 971,
    consecutive_failures: 0,
  },
  dashboard_auto_mirror: {
    state_exists: true,
    paused: false,
    lock_live: false,
    last_successful_mirror_at: "2026-06-10T18:18:33+00:00",
    last_mirrored_daily_core_generated_at: "2026-06-10T18:12:48+00:00",
    mirror_matches_daily_core: true,
    cooldown_seconds: 900,
    cooldown_remaining_seconds: 0,
    consecutive_failures: 0,
  },
  cron: { note: "not inspected by API" },
  recommended_action: "none",
  warnings: [],
};

vi.mock("../api/operatorClient", () => ({
  fetchOperatorAutomationStatus: vi.fn(),
}));

import { fetchOperatorAutomationStatus } from "../api/operatorClient";

const mockFetchAutomation = vi.mocked(fetchOperatorAutomationStatus);

function wrap(ui: ReactNode) {
  return (
    <DashboardDataContext.Provider
      value={
        {
          data: {
            health: { ok: true, service: "origenlab-api", mode: "operator-sqlite-readonly", backend: "sqlite" },
            operator: { verdict: "READY", outbound_readiness: "ready", warnings: [] },
          },
          warm: { items: [], meta: null },
          equipment: {
            items: [],
            meta: {
              reduced_mode: false,
              count: 0,
              data_source: "active_current_csv",
              read_only: true,
              note: "",
              campaign_mode: null,
            },
          },
          commercialDeals: null,
          panelLoading: false,
          panelError: null,
          catalogProducts: null,
          mirrorBackend: false,
          loadPanel: async () => {},
          setContactEmail: () => {},
        } as never
      }
    >
      {ui}
    </DashboardDataContext.Provider>
  );
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("SystemPage", () => {
  it("explains full archive vs canonical Gmail subset", () => {
    mockFetchAutomation.mockResolvedValue(BASE_AUTOMATION_STATUS as never);
    render(wrap(<SystemPage />));
    screen.getByText(/216\s*000/);
    screen.getByText(/1\s*100/);
    screen.getByText(/contacto@origenlab\.cl/);
    expect(screen.getByText(/subconjunto canónico/i)).toBeTruthy();
    expect(screen.getByText(/todo el archivo histórico/i)).toBeTruthy();
  });

  it("renders operator automation section with safety note", async () => {
    mockFetchAutomation.mockResolvedValue(BASE_AUTOMATION_STATUS as never);
    render(wrap(<SystemPage />));
    screen.getByTestId("system-automation-section");
    screen.getByRole("heading", { name: "Automatización operador" });
    screen.getByText(/no ejecuta refresh, mirror ni envíos/i);
    await waitFor(() => {
      screen.getByTestId("automation-health-card");
    });
    screen.getByText("Estado de automatización");
  });
});
