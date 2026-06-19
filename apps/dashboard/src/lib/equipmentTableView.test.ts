import { describe, expect, it } from "vitest";
import type { EquipmentOpportunityItem } from "../api/commercialTypes";
import {
  DEFAULT_EQUIPMENT_FILTERS,
  applyEquipmentTableView,
  equipmentFiltersActive,
  filterEquipment,
  sortEquipment,
} from "./equipmentTableView";
import { getEquipmentWatchlistKey } from "./equipmentWatchlist";

const NOW = new Date("2026-06-15T12:00:00Z");

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
  {
    priority_rank: 3,
    codigo_licitacion: "LP-3",
    buyer: "Clinica Central",
    region: "RM",
    close_date: "17/06/2026",
    equipment_category: "microscope",
    item_description: "Microscope",
    next_action: "quote_now",
    safe_channel: "mercado_publico_bid",
    supplier_needed: "no",
    contact_status: "review_required",
    contact_email: "lab@clinica.cl",
    operator_note: "quote queue",
  },
  {
    priority_rank: 4,
    codigo_licitacion: "LP-4",
    buyer: "Servicio Salud",
    region: "BioBio",
    close_date: "01/08/2026",
    equipment_category: "incubator",
    item_description: "Incubator",
    next_action: "monitor",
    safe_channel: "mercado_publico_only",
    supplier_needed: "no",
    contact_status: "no_verified_buyer_email",
    contact_email: "",
    operator_note: "no email",
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

  it("keeps all rows when triage is all", () => {
    const filtered = filterEquipment(rows, DEFAULT_EQUIPMENT_FILTERS, { now: NOW });
    expect(filtered).toHaveLength(rows.length);
  });

  it("filters quote_now rows by triage key", () => {
    const filtered = filterEquipment(
      rows,
      { ...DEFAULT_EQUIPMENT_FILTERS, triage: "quote_now" },
      { now: NOW },
    );
    expect(filtered).toHaveLength(1);
    expect(filtered[0].codigo_licitacion).toBe("LP-3");
  });

  it("filters closing_soon rows with deterministic now", () => {
    const filtered = filterEquipment(
      rows,
      { ...DEFAULT_EQUIPMENT_FILTERS, triage: "closing_soon" },
      { now: NOW },
    );
    expect(filtered.map((row) => row.codigo_licitacion)).toEqual(["LP-3"]);
  });

  it("filters missing_contact rows by triage key", () => {
    const filtered = filterEquipment(
      rows,
      { ...DEFAULT_EQUIPMENT_FILTERS, triage: "missing_contact" },
      { now: NOW },
    );
    expect(filtered).toHaveLength(1);
    expect(filtered[0].codigo_licitacion).toBe("LP-4");
  });

  it("filters supplier_needed rows by triage key", () => {
    const filtered = filterEquipment(
      rows,
      { ...DEFAULT_EQUIPMENT_FILTERS, triage: "supplier_needed" },
      { now: NOW },
    );
    expect(filtered).toHaveLength(1);
    expect(filtered[0].codigo_licitacion).toBe("LP-1");
  });

  it("filters mercado_publico_only rows by triage key", () => {
    const filtered = filterEquipment(
      rows,
      { ...DEFAULT_EQUIPMENT_FILTERS, triage: "mercado_publico_only" },
      { now: NOW },
    );
    expect(filtered).toHaveLength(1);
    expect(filtered[0].codigo_licitacion).toBe("LP-4");
  });

  it("combines search and triage filters", () => {
    const filtered = filterEquipment(
      rows,
      { ...DEFAULT_EQUIPMENT_FILTERS, search: "clinica", triage: "quote_now" },
      { now: NOW },
    );
    expect(filtered).toHaveLength(1);
    expect(filtered[0].buyer).toBe("Clinica Central");
  });

  it("treats default filters as inactive", () => {
    expect(equipmentFiltersActive(DEFAULT_EQUIPMENT_FILTERS)).toBe(false);
  });

  it("treats triage filter as active when not all", () => {
    expect(
      equipmentFiltersActive({
        ...DEFAULT_EQUIPMENT_FILTERS,
        triage: "supplier_needed",
      }),
    ).toBe(true);
  });

  it("keeps all rows when watchlist is all", () => {
    const filtered = filterEquipment(rows, DEFAULT_EQUIPMENT_FILTERS, {
      now: NOW,
      savedKeys: new Set([getEquipmentWatchlistKey(rows[0])]),
    });
    expect(filtered).toHaveLength(rows.length);
  });

  it("filters saved rows by watchlist key", () => {
    const savedKeys = new Set([getEquipmentWatchlistKey(rows[2])]);
    const filtered = filterEquipment(
      rows,
      { ...DEFAULT_EQUIPMENT_FILTERS, watchlist: "saved" },
      { savedKeys },
    );
    expect(filtered).toHaveLength(1);
    expect(filtered[0].codigo_licitacion).toBe("LP-3");
  });

  it("combines saved filter with triage and search", () => {
    const savedKeys = new Set([
      getEquipmentWatchlistKey(rows[2]),
      getEquipmentWatchlistKey(rows[3]),
    ]);
    const filtered = filterEquipment(
      rows,
      {
        ...DEFAULT_EQUIPMENT_FILTERS,
        watchlist: "saved",
        triage: "quote_now",
        search: "clinica",
      },
      { now: NOW, savedKeys },
    );
    expect(filtered).toHaveLength(1);
    expect(filtered[0].buyer).toBe("Clinica Central");
  });

  it("treats watchlist filter as active when not all", () => {
    expect(
      equipmentFiltersActive({
        ...DEFAULT_EQUIPMENT_FILTERS,
        watchlist: "saved",
      }),
    ).toBe(true);
  });
});
