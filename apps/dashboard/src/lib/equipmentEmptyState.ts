import type { EquipmentTableFilters } from "./equipmentTableView";

const GENERIC_SEARCH_EMPTY = "Ninguna oportunidad coincide con la búsqueda actual.";

const TRIAGE_ONLY_EMPTY =
  'No hay oportunidades con este filtro de triage. Prueba "Todas" o limpia los filtros.';

const TRIAGE_AND_SEARCH_EMPTY =
  'No hay oportunidades que coincidan con este filtro de triage y búsqueda. Prueba ajustar la búsqueda, elegir "Todas" o limpiar los filtros.';

export function getEquipmentFilterEmptyMessage(filters: EquipmentTableFilters): string {
  const hasSearch = Boolean(filters.search.trim());
  const hasTriage = filters.triage !== "all";

  if (hasTriage && !hasSearch) {
    return TRIAGE_ONLY_EMPTY;
  }
  if (hasTriage && hasSearch) {
    return TRIAGE_AND_SEARCH_EMPTY;
  }
  return GENERIC_SEARCH_EMPTY;
}
