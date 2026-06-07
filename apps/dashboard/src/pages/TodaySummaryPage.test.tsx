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
  it("shows Qué revisar hoy once and Colas prioritarias as queue section title", () => {
    renderToday();
    expect(screen.getAllByText("Qué revisar hoy")).toHaveLength(1);
    screen.getByRole("heading", { level: 2, name: "Colas prioritarias" });
    screen.getByText(/Colas priorizadas según correos, oportunidades de equipos y señales comerciales cargadas/);
  });

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

  it("humanizes Global MAX outlier warning in Atención section", () => {
    renderToday({
      data: {
        ...BASE_PANEL,
        operator: {
          ...BASE_PANEL.operator,
          warnings: [
            "Global MAX(date_iso) outlier (2033-06-09T15:09:53+01:00) — prefer 2026-filtered freshness.",
          ],
        },
      },
    });
    screen.getByText(
      "Hay una fecha futura anómala en el archivo histórico. Para frescura diaria se usa la fecha filtrada de 2026.",
    );
    expect(screen.queryByText(/Global MAX\(date_iso\)/)).toBeNull();
  });

  it("humanizes FastLab not_contacted warning in Atención section", () => {
    renderToday({
      data: {
        ...BASE_PANEL,
        operator: {
          ...BASE_PANEL.operator,
          warnings: [
            "FastLab (contacto@fastlab.cl): corrected to not_contacted; no Gmail Sent evidence; future outreach requires deliberate manual review.",
          ],
        },
      },
    });
    screen.getByText(
      "FastLab quedó marcado como no contactado porque no hay evidencia en Gmail Enviados. Revisar manualmente antes de contactar.",
    );
    expect(screen.queryByText(/corrected to not_contacted/i)).toBeNull();
  });

  it("shows unknown operator warnings unchanged", () => {
    const raw = "Quiteca: institutional caution — jorgepc@quiteca.cl contacted April 2026.";
    renderToday({
      data: {
        ...BASE_PANEL,
        operator: {
          ...BASE_PANEL.operator,
          warnings: [raw],
        },
      },
    });
    screen.getByText(/Quiteca: institutional caution/);
  });

  it("shows empty attention state when there are no warnings", () => {
    renderToday();
    screen.getByText("Sin advertencias por ahora.");
  });
});

describe("TodaySummaryPage prospect review card", () => {
  it("renders Prospectos en revisión with review_count as the main value", () => {
    renderToday({
      leadResearchSummary: {
        table_available: true,
        total: 71,
        review_count: 71,
        blocked_count: 1,
        net_new_safe: 0,
        gmail_historico: 5,
        followup_antiguo: 0,
        caso_activo: 0,
        public_tender_review: 2,
        same_domain_review: 1,
        research_needed: 3,
        data_source: "postgres_mirror",
        read_only: true,
        disclaimer: "",
      },
    });

    screen.getByText("Prospectos en revisión");
    expect(screen.queryByText("Prospectos seguros")).toBeNull();
    screen.getByLabelText(/Prospectos en revisión: 71/);
    expect(screen.queryByLabelText(/Prospectos en revisión: 0/)).toBeNull();
  });

  it("shows net_new_safe in the hint when review_count is present", () => {
    renderToday({
      leadResearchSummary: {
        table_available: true,
        total: 71,
        review_count: 71,
        blocked_count: 1,
        net_new_safe: 0,
        gmail_historico: 5,
        followup_antiguo: 0,
        caso_activo: 0,
        public_tender_review: 2,
        same_domain_review: 1,
        research_needed: 3,
        data_source: "postgres_mirror",
        read_only: true,
        disclaimer: "",
      },
    });

    screen.getByText("0 nuevos seguros · revisar historial antes de contactar");
  });

  it("shows missing-summary hint when leadResearchSummary is null", () => {
    renderToday({ leadResearchSummary: null });
    screen.getByText("Sin resumen de prospectos cargado");
    screen.getByLabelText(/Prospectos en revisión: 0/);
  });

  it("shows prior-history warning when same_domain_review threshold is met", () => {
    renderToday({
      leadResearchSummary: {
        table_available: true,
        total: 10,
        review_count: 10,
        blocked_count: 0,
        net_new_safe: 2,
        gmail_historico: 0,
        followup_antiguo: 0,
        caso_activo: 0,
        public_tender_review: 0,
        same_domain_review: 3,
        research_needed: 0,
        data_source: "postgres_mirror",
        read_only: true,
        disclaimer: "",
      },
    });

    screen.getByTestId("today-prospect-prior-history-warning");
    screen.getByText(/Hay prospectos con historial previo/);
    expect(screen.queryByRole("button", { name: /Enviar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /Aplicar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /^Run$/i })).toBeNull();
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
