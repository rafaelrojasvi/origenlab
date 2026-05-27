import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { DashboardDataContext } from "../context/DashboardDataContext";
import { SystemPage } from "./SystemPage";

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

describe("SystemPage", () => {
  it("explains full archive vs canonical Gmail subset", () => {
    render(wrap(<SystemPage />));
    screen.getByText(/216\s*000/);
    screen.getByText(/1\s*100/);
    screen.getByText(/contacto@origenlab\.cl/);
    expect(screen.getByText(/subconjunto canónico/i)).toBeTruthy();
    expect(screen.getByText(/todo el archivo histórico/i)).toBeTruthy();
  });
});
