import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DashboardDataContext } from "../context/DashboardDataContext";
import { TodaySummaryPage } from "./TodaySummaryPage";

const BASE_PANEL = {
  health: {
    ok: true,
    service: "origenlab-api",
    mode: "operator-sqlite-readonly",
    backend: "sqlite" as const,
    postgres_configured: false,
  },
  operator: {
    verdict: "READY",
    sqlite_path: "/hidden/emails.sqlite",
    campaign_mode: null,
    operator_focus: null,
    outbound_readiness: "ready",
    warnings: [] as string[],
    daily_core_run: { exists: false },
  },
};

function renderToday(overrides: Record<string, unknown> = {}) {
  return render(
    <DashboardDataContext.Provider
      value={
        {
          data: BASE_PANEL,
          panelLoading: false,
          panelError: null,
          warm: { items: [], meta: null },
          equipment: { items: [], meta: null },
          commercialDeals: null,
          catalogProducts: { total: 6 },
          leadResearchSummary: null,
          mirrorBackend: false,
          loadPanel: async () => {},
          setContactEmail: () => {},
          ...overrides,
        } as never
      }
    >
      <TodaySummaryPage />
    </DashboardDataContext.Provider>,
  );
}

describe("TodaySummaryPage operator landing layout", () => {
  it("shows Qué revisar hoy before Estado del sistema", () => {
    renderToday();
    const body = document.body.textContent ?? "";
    expect(body.indexOf("Qué revisar hoy")).toBeGreaterThanOrEqual(0);
    expect(body.indexOf("Estado del sistema")).toBeGreaterThan(body.indexOf("Qué revisar hoy"));
  });

  it("shows business cards before Estado del sistema", () => {
    renderToday();
    const body = document.body.textContent ?? "";
    expect(body.indexOf("Clientes por responder")).toBeLessThan(body.indexOf("Estado del sistema"));
    expect(body.indexOf("Catálogo")).toBeLessThan(body.indexOf("Estado del sistema"));
  });

  it("shows read-only safety note once at the top", () => {
    renderToday();
    screen.getByText(/Solo lectura: este panel no envía correos ni aprueba contactos/);
    expect(screen.queryByText(/No aprueba envíos/)).toBeNull();
  });

  it("does not render forbidden action button labels", () => {
    renderToday();
    expect(screen.queryByRole("button", { name: /Enviar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Aplicar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Ejecutar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Validar stack/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Run$/i })).toBeNull();
    expect(screen.getAllByText("Ver sección →").length).toBeGreaterThan(0);
  });

  it("humanizes stale Postgres mirror warning in Atención section", () => {
    renderToday({
      data: {
        ...BASE_PANEL,
        operator: {
          ...BASE_PANEL.operator,
          warnings: ["Postgres mirror last sync older than 24h (2026-06-01T00:00:00Z)."],
        },
      },
    });
    screen.getByText(
      "El espejo Postgres no se ha sincronizado en más de 24h. Los datos pueden estar atrasados.",
    );
  });

  it("shows empty attention state when there are no warnings", () => {
    renderToday();
    screen.getByText("Sin advertencias por ahora.");
  });
});

describe("TodaySummaryPage equipment feed warning", () => {
  it("shows unavailable warning and N/D KPI when equipment reduced_mode", () => {
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
              },
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
            commercialDeals: {
              items: [],
              table_available: true,
              total: 0,
              limit: 20,
              read_only: true,
              data_source: "postgres_mirror",
            },
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
    screen.getByText("Catálogo");
  });
});

describe("TodaySummaryPage daily-core status", () => {
  it("renders missing daily_core_run in system status without duplicate safety note", () => {
    renderToday();

    const systemStatus = screen.getByTestId("today-system-status");
    within(systemStatus).getByText("Última ejecución daily-core");
    within(systemStatus).getByText("Sin ejecución registrada todavía.");
    expect(within(systemStatus).queryByText(/No aprueba envíos/)).toBeNull();
  });
});
