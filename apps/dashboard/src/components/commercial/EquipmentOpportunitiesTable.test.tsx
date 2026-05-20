import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
      />,
    );

    screen.getByText("Universidad Ejemplo");
    screen.getByText("LP-001");
    screen.getByText(/fit=90/);
    expect(screen.queryByText(/source_path/)).toBeNull();
    expect(screen.queryByText(/body/)).toBeNull();
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
      />,
    );
    screen.getByText(/No equipment opportunities returned/);
  });
});
