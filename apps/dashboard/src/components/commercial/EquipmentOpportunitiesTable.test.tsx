import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { EquipmentOpportunityItem } from "../../api/commercialTypes";
import { EquipmentOpportunitiesTable } from "./EquipmentOpportunitiesTable";

const row: EquipmentOpportunityItem = {
  priority_rank: 1,
  codigo_licitacion: "LP-001",
  buyer: "Universidad Ejemplo",
  region: "RM",
  close_date: "01/06/2026",
  equipment_category: "centrifuge",
  item_description: "High-speed centrifuge",
  next_action: "quote_now",
  safe_channel: "mercado_publico_bid",
  supplier_needed: "yes",
  contact_status: "no_verified_buyer_email",
  contact_email: "buyer@hospital.cl",
  operator_note: "fit=90",
};

describe("EquipmentOpportunitiesTable", () => {
  it("renders safe columns only", () => {
    render(
      <EquipmentOpportunitiesTable
        backend="sqlite"
        items={[row]}
        meta={{
          data_source: "active_current_csv",
          reduced_mode: false,
          note: "",
          count: 1,
          campaign_mode: "equipment_first",
        }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );

    screen.getByText("Universidad Ejemplo");
    screen.getByText("LP-001");
    screen.getByText(/fit=90/);
    expect(screen.queryByText(/source_path/)).toBeNull();
    expect(screen.queryByText(/body_preview/)).toBeNull();
  });

  it("renders minimal row without crashing", () => {
    render(
      <EquipmentOpportunitiesTable
        backend="postgres"
        items={[
          {
            priority_rank: 0,
            codigo_licitacion: "",
            buyer: "",
            region: "",
            close_date: "",
            equipment_category: "",
            item_description: "",
            next_action: "",
            safe_channel: "",
            supplier_needed: "",
            contact_status: "",
            contact_email: "",
            operator_note: "",
          },
        ]}
        meta={{
          data_source: "postgres_mirror",
          reduced_mode: false,
          note: "",
          count: 1,
          campaign_mode: null,
        }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("shows error and empty states", () => {
    const { rerender } = render(
      <EquipmentOpportunitiesTable
        backend="sqlite"
        items={[]}
        meta={null}
        loading={false}
        error="Equipment API down"
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    screen.getByText("Equipment API down");

    rerender(
      <EquipmentOpportunitiesTable
        backend="sqlite"
        items={[]}
        meta={{ data_source: "active_current_csv", reduced_mode: false, note: "", count: 0, campaign_mode: null }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    screen.getByText(/No hay oportunidades de equipos en la cola actual/);
  });

  it("opens contact drilldown when contact email is present", () => {
    const onContactSelect = vi.fn();
    render(
      <EquipmentOpportunitiesTable
        backend="sqlite"
        items={[row]}
        meta={{
          data_source: "active_current_csv",
          reduced_mode: false,
          note: "",
          count: 1,
          campaign_mode: "equipment_first",
        }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={onContactSelect}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "buyer@hospital.cl" }));
    expect(onContactSelect).toHaveBeenCalledWith("buyer@hospital.cl");
  });

  it("filters by search and shows no-match message", () => {
    render(
      <EquipmentOpportunitiesTable
        backend="sqlite"
        items={[row]}
        meta={{
          data_source: "active_current_csv",
          reduced_mode: false,
          note: "",
          count: 1,
          campaign_mode: "equipment_first",
        }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText("Search equipment opportunities"), {
      target: { value: "zzznomatch" },
    });
    screen.getByText(/Ninguna oportunidad coincide con la búsqueda actual/);
    expect(screen.queryByText("Universidad Ejemplo")).toBeNull();
  });

  it("does not invent contact email when field is empty", () => {
    render(
      <EquipmentOpportunitiesTable
        backend="sqlite"
        items={[{ ...row, contact_email: "" }]}
        meta={{
          data_source: "active_current_csv",
          reduced_mode: false,
          note: "",
          count: 1,
          campaign_mode: null,
        }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /@/ })).toBeNull();
  });

  it("shows unavailable panel when feed is in reduced mode", () => {
    render(
      <EquipmentOpportunitiesTable
        backend="sqlite"
        items={[]}
        meta={{
          data_source: "active_current_csv",
          reduced_mode: true,
          note: "Cola equipment_first no encontrada.",
          count: 0,
          campaign_mode: "equipment_first",
        }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );

    const panel = screen.getByTestId("equipment-feed-unavailable");
    screen.getByText("Fuente de licitaciones no disponible");
    expect(panel.textContent).toMatch(/No significa que no existan oportunidades/);
    expect(panel.textContent).toMatch(/equipment_first_operator_queue/);
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows zero-items message when feed is available but empty", () => {
    render(
      <EquipmentOpportunitiesTable
        backend="sqlite"
        items={[]}
        meta={{
          data_source: "active_current_csv",
          reduced_mode: false,
          note: "",
          count: 0,
          campaign_mode: "equipment_first",
        }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );

    screen.getByText("No hay oportunidades de equipos en la cola actual.");
    expect(screen.queryByTestId("equipment-feed-unavailable")).toBeNull();
  });
});

