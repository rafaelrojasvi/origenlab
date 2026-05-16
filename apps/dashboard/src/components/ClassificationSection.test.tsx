import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ClassificationSection } from "./ClassificationSection";

describe("ClassificationSection", () => {
  it("renders classification KPI cards", () => {
    render(
      <ClassificationSection
        summary={{
          scope: "canonical",
          table_available: true,
          status: "ok",
          total_rows: 3,
          counts_by_label: {},
          kpi: {
            posibles_solicitudes: 2,
            cotizaciones_enviadas: 1,
            seguimientos: 0,
            rebotes_malos_correos: 0,
            proveedores: 0,
            sin_clasificar: 0,
          },
          disclaimer: "Heurística",
        }}
        recent={{ scope: "canonical", table_available: true, items: [], total: 0, limit: 20, label_filter: null }}
        actions={{ scope: "canonical", table_available: true, groups: [], disclaimer: "" }}
      />,
    );
    expect(screen.getByText("Posibles solicitudes")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
  });
});
