import { describe, expect, it } from "vitest";
import { DEFAULT_EQUIPMENT_FILTERS } from "./equipmentTableView";
import { getEquipmentFilterEmptyMessage } from "./equipmentEmptyState";

describe("getEquipmentFilterEmptyMessage", () => {
  it("returns generic search copy for default filters", () => {
    expect(getEquipmentFilterEmptyMessage(DEFAULT_EQUIPMENT_FILTERS)).toBe(
      "Ninguna oportunidad coincide con la búsqueda actual.",
    );
  });

  it("returns triage copy when only triage is active", () => {
    expect(
      getEquipmentFilterEmptyMessage({
        ...DEFAULT_EQUIPMENT_FILTERS,
        triage: "quote_now",
      }),
    ).toBe('No hay oportunidades con este filtro de triage. Prueba "Todas" o limpia los filtros.');
  });

  it("returns combined copy when triage and search are active", () => {
    expect(
      getEquipmentFilterEmptyMessage({
        ...DEFAULT_EQUIPMENT_FILTERS,
        triage: "missing_contact",
        search: "hospital",
      }),
    ).toBe(
      'No hay oportunidades que coincidan con este filtro de triage y búsqueda. Prueba ajustar la búsqueda, elegir "Todas" o limpiar los filtros.',
    );
  });

  it("treats whitespace-only search as empty search", () => {
    expect(
      getEquipmentFilterEmptyMessage({
        ...DEFAULT_EQUIPMENT_FILTERS,
        triage: "supplier_needed",
        search: "   ",
      }),
    ).toBe('No hay oportunidades con este filtro de triage. Prueba "Todas" o limpia los filtros.');
  });

  it("does not use triage copy when only sort changes", () => {
    expect(
      getEquipmentFilterEmptyMessage({
        ...DEFAULT_EQUIPMENT_FILTERS,
        sort: "buyer",
      }),
    ).toBe("Ninguna oportunidad coincide con la búsqueda actual.");
  });

  it("returns watchlist copy when saved filter is active", () => {
    expect(
      getEquipmentFilterEmptyMessage({
        ...DEFAULT_EQUIPMENT_FILTERS,
        watchlist: "saved",
      }),
    ).toBe(
      "No hay oportunidades guardadas con los filtros actuales. Guarda oportunidades para revisarlas después o limpia los filtros.",
    );
  });
});
