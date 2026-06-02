/** Client-side table pagination (no API calls). */

export const DEFAULT_CLIENT_PAGE_SIZE = 15;

export const CLIENT_PAGE_SIZE_OPTIONS = [15, 30, 50] as const;

export type ClientPageSizeOption = (typeof CLIENT_PAGE_SIZE_OPTIONS)[number] | "all";

export function paginateSlice<T>(
  rows: T[],
  page: number,
  pageSize: ClientPageSizeOption,
): {
  slice: T[];
  page: number;
  totalPages: number;
  from: number;
  to: number;
  visibleTotal: number;
} {
  const visibleTotal = rows.length;
  if (visibleTotal === 0) {
    return { slice: [], page: 1, totalPages: 1, from: 0, to: 0, visibleTotal: 0 };
  }
  if (pageSize === "all") {
    return {
      slice: rows,
      page: 1,
      totalPages: 1,
      from: 1,
      to: visibleTotal,
      visibleTotal,
    };
  }
  const totalPages = Math.max(1, Math.ceil(visibleTotal / pageSize));
  const safePage = Math.min(Math.max(1, page), totalPages);
  const start = (safePage - 1) * pageSize;
  const slice = rows.slice(start, start + pageSize);
  return {
    slice,
    page: safePage,
    totalPages,
    from: start + 1,
    to: start + slice.length,
    visibleTotal,
  };
}

export function formatWarmCasesTableFooter(args: {
  from: number;
  to: number;
  visibleTotal: number;
  loadedTotal: number;
  page: number;
  totalPages: number;
  sectionName?: string;
  globalQueueTotal?: number;
  presetLabel?: string;
  filtered?: boolean;
}): string {
  const {
    from,
    to,
    visibleTotal,
    loadedTotal,
    page,
    totalPages,
    sectionName,
    globalQueueTotal,
    presetLabel,
    filtered,
  } = args;

  const rangePart =
    visibleTotal === 0
      ? "Mostrando 0 casos"
      : from === to
        ? `Mostrando ${from} de ${visibleTotal}`
        : `Mostrando ${from}–${to} de ${visibleTotal}`;

  const sectionPart = sectionName ? ` en ${sectionName}` : " casos";
  const pagePart =
    totalPages > 1 || (visibleTotal > 0 && to - from + 1 < visibleTotal)
      ? ` · Página ${page} de ${totalPages}`
      : visibleTotal > DEFAULT_CLIENT_PAGE_SIZE
        ? ` · Página ${page} de ${totalPages}`
        : "";

  const globalPart =
    sectionName != null &&
    globalQueueTotal != null &&
    globalQueueTotal !== loadedTotal
      ? ` · ${globalQueueTotal} casos tibios en cola global`
      : "";

  const presetPart = presetLabel && !sectionName ? ` · vista: ${presetLabel}` : "";
  const filterPart =
    filtered && visibleTotal < loadedTotal ? " · filtros activos" : "";

  return `${rangePart}${sectionPart}${pagePart}${globalPart}${presetPart}${filterPart} · solo lectura`;
}

export function formatProspectosTableFooter(args: {
  loaded: number;
  total: number;
}): { primary: string; truncationNote?: string } {
  const { loaded, total } = args;
  if (loaded === 0) {
    return { primary: "Mostrando 0 prospectos · solo lectura" };
  }
  const primary = `Mostrando 1–${loaded} de ${total} prospectos · solo lectura`;
  const truncationNote =
    total > loaded
      ? "La API tiene más resultados que los cargados; ajustar filtros o cargar más en una fase futura."
      : undefined;
  return { primary, truncationNote };
}
