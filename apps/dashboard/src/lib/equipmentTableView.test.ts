import { describe, expect, it } from "vitest";
import type { EquipmentOpportunityItem } from "../api/commercialTypes";
import {
  DEFAULT_EQUIPMENT_FILTERS,
  applyEquipmentTableView,
  filterEquipment,
  sortEquipment,
} from "./equipmentTableView";

const rows: EquipmentOpportunityItem[] = [
  {
    priority_rank: 2,
    codigo_licitacion: "LP-2",
    buyer: "Hospital Sur",
    region: "RM",
    close_date: "20/06/2026",
    equipment_category: "balance",
    item_description: "Analytical balance",
    next_action: "quote",
    safe_channel: "bid",
    supplier_needed: "no",
    contact_status: "pending",
    contact_email: "",
    operator_note: "fit=80",
  },
  {
    priority_rank: 1,
    codigo_licitacion: "LP-1",
    buyer: "Universidad Norte",
    region: "Valpo",
    close_date: "01/06/2026",
    equipment_category: "centrifuge",
    item_description: "Centrifuge unit",
    next_action: "monitor",
    safe_channel: "mp",
    supplier_needed: "yes",
    contact_status: "ok",
    contact_email: "procurement@uni.cl",
    operator_note: "urgent",
  },
];

describe("equipmentTableView", () => {
  it("filters by buyer and note", () => {
    const filtered = filterEquipment(rows, { ...DEFAULT_EQUIPMENT_FILTERS, search: "universidad" });
    expect(filtered).toHaveLength(1);
    expect(filtered[0].buyer).toMatch(/Universidad/);
  });

  it("sorts by priority rank ascending", () => {
    const sorted = sortEquipment(rows, "rank_asc");
    expect(sorted[0].priority_rank).toBe(1);
  });

  it("sorts by close date", () => {
    const sorted = sortEquipment(rows, "close_date_asc");
    expect(sorted[0].codigo_licitacion).toBe("LP-1");
  });

  it("apply combines search and sort", () => {
    const out = applyEquipmentTableView(rows, {
      ...DEFAULT_EQUIPMENT_FILTERS,
      search: "hospital",
      sort: "buyer",
    });
    expect(out).toHaveLength(1);
    expect(out[0].buyer).toBe("Hospital Sur");
  });
});
