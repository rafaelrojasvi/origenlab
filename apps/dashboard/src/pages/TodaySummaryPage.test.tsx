import { render, screen } from "@testing-library/react";
import { describe, it } from "vitest";
import { DashboardDataContext } from "../context/DashboardDataContext";
import { TodaySummaryPage } from "./TodaySummaryPage";

describe("TodaySummaryPage equipment feed warning", () => {
  it("shows unavailable warning and N/D KPI when equipment reduced_mode", () => {
    render(
      <DashboardDataContext.Provider
        value={
          {
            data: {
              health: { ok: true, service: "origenlab-api", mode: "operator-sqlite-readonly", backend: "sqlite" },
              operator: { verdict: "READY", outbound_readiness: "ready", warnings: [] },
            },
            panelLoading: false,
            panelError: null,
            warm: { items: [], meta: null },
            equipment: {
              items: [],
              meta: {
                reduced_mode: true,
                count: 0,
                data_source: "active_current_csv",
                read_only: true,
                note: "missing queue",
                campaign_mode: "equipment_first",
              },
            },
            commercialDeals: { items: [], table_available: true, total: 0, limit: 20, read_only: true, data_source: "postgres_mirror" },
            catalogProducts: { total: 6 },
            mirrorBackend: false,
            loadPanel: async () => {},
            setContactEmail: () => {},
          } as never
        }
      >
        <TodaySummaryPage />
      </DashboardDataContext.Provider>,
    );

    screen.getByTestId("today-equipment-feed-unavailable");
    screen.getByText("Fuente de licitaciones no disponible");
    screen.getByLabelText(/Licitaciones \/ equipos: N\/D/);
    screen.getByText("Productos catalogados");
  });
});

describe("TodaySummaryPage daily-core status", () => {
  it("renders missing daily_core_run as no run registered", () => {
    render(
      <DashboardDataContext.Provider
        value={
          {
            data: {
              health: {
                ok: true,
                service: "origenlab-api",
                mode: "operator-sqlite-readonly",
                backend: "sqlite",
                postgres_configured: false,
              },
              operator: {
                verdict: "READY",
                sqlite_path: "/hidden/emails.sqlite",
                campaign_mode: null,
                operator_focus: null,
                outbound_readiness: "ready",
                warnings: [],
              },
            },
            panelLoading: false,
            panelError: null,
            warm: { items: [], meta: null },
            equipment: { items: [], meta: null },
            commercialDeals: null,
            catalogProducts: null,
            leadResearchSummary: null,
            mirrorBackend: false,
            loadPanel: async () => {},
            setContactEmail: () => {},
          } as never
        }
      >
        <TodaySummaryPage />
      </DashboardDataContext.Provider>,
    );

    screen.getByText("Última ejecución daily-core");
    screen.getByText("Sin ejecución registrada todavía.");
  });
});
