/** Client-side table pagination (no API calls). */

export const DEFAULT_CLIENT_PAGE_SIZE = 15;

export const CLIENT_PAGE_SIZE_OPTIONS = [15, 30, 50] as const;

export type ClientPageSizeOption = (typeof CLIENT_PAGE_SIZE_OPTIONS)[number] | "all";

export type PageNumberToken = number | "ellipsis";

/** Numbered page controls with ellipsis for large page counts (e.g. 1 … 4 5 6 7 8 … 12). */
export function getVisiblePageNumbers(
  page: number,
  totalPages: number,
  siblingCount = 1,
): PageNumberToken[] {
  if (totalPages <= 0) {
    return [];
  }
  if (totalPages === 1) {
    return [1];
  }

  const delta = siblingCount;
  const range: number[] = [];
  const left = page - delta;
  const right = page + delta + 1;

  for (let i = 1; i <= totalPages; i += 1) {
    if (i === 1 || i === totalPages || (i >= left && i < right)) {
      range.push(i);
    }
  }

  const withEllipsis: PageNumberToken[] = [];
  let prev: number | undefined;
  for (const i of range) {
    if (prev !== undefined) {
      if (i - prev === 2) {
        withEllipsis.push(prev + 1);
      } else if (i - prev !== 1) {
        withEllipsis.push("ellipsis");
      }
    }
    withEllipsis.push(i);
    prev = i;
  }
  return withEllipsis;
}

/** Alias for paginateSlice — client-side batching of in-memory rows. */
export const paginateClientItems = paginateSlice;

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

export function formatPagedFooterLabel(args: {
  from: number;
  to: number;
  visibleTotal: number;
  page: number;
  totalPages: number;
  extraParts?: string[];
}): string {
  const { from, to, visibleTotal, page, totalPages, extraParts = [] } = args;

  const rangePart =
    visibleTotal === 0
      ? "Mostrando 0"
      : from === to
        ? `Mostrando ${from} de ${visibleTotal}`
        : `Mostrando ${from}–${to} de ${visibleTotal}`;

  const pagePart =
    totalPages > 1 ? ` · Página ${page} de ${totalPages}` : "";

  const extras = extraParts.length > 0 ? ` · ${extraParts.join(" · ")}` : "";

  return `${rangePart}${pagePart}${extras} · solo lectura`;
}

export function formatProspectosTableFooter(args: {
  from: number;
  to: number;
  loaded: number;
  apiTotal: number;
  page: number;
  totalPages: number;
}): { primary: string; truncationNote?: string } {
  const { from, to, loaded, apiTotal, page, totalPages } = args;
  if (loaded === 0) {
    return { primary: "Mostrando 0 prospectos · solo lectura" };
  }

  const rangePart =
    from === to
      ? `Mostrando ${from} de ${loaded} cargados`
      : `Mostrando ${from}–${to} de ${loaded} cargados`;

  const apiPart = apiTotal > loaded ? ` · API total ${apiTotal}` : "";
  const pagePart = totalPages > 1 ? ` · Página ${page} de ${totalPages}` : "";

  const primary = `${rangePart}${apiPart}${pagePart} · solo lectura`;
  const truncationNote =
    apiTotal > loaded
      ? "La API tiene más resultados que los cargados; usar filtros o una fase futura de carga paginada."
      : undefined;
  return { primary, truncationNote };
}
