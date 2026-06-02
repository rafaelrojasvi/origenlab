import { describe, expect, it } from "vitest";
import {
  formatPagedFooterLabel,
  formatProspectosTableFooter,
  formatWarmCasesTableFooter,
  getVisiblePageNumbers,
  paginateSlice,
} from "./clientTablePagination";

describe("getVisiblePageNumbers", () => {
  it("lists every page when count is small", () => {
    expect(getVisiblePageNumbers(2, 4)).toEqual([1, 2, 3, 4]);
  });

  it("inserts ellipsis for large page counts", () => {
    expect(getVisiblePageNumbers(6, 12)).toEqual([1, "ellipsis", 5, 6, 7, "ellipsis", 12]);
  });

  it("returns a single page when totalPages is 1", () => {
    expect(getVisiblePageNumbers(1, 1)).toEqual([1]);
  });
});

describe("paginateSlice", () => {
  const rows = Array.from({ length: 20 }, (_, i) => i);

  it("defaults to first page of 15", () => {
    const r = paginateSlice(rows, 1, 15);
    expect(r.slice).toHaveLength(15);
    expect(r.from).toBe(1);
    expect(r.to).toBe(15);
    expect(r.totalPages).toBe(2);
  });

  it("shows all rows when page size is all", () => {
    const r = paginateSlice(rows, 1, "all");
    expect(r.slice).toHaveLength(20);
    expect(r.from).toBe(1);
    expect(r.to).toBe(20);
    expect(r.totalPages).toBe(1);
  });

  it("returns empty slice for no rows", () => {
    const r = paginateSlice([], 1, 15);
    expect(r.slice).toHaveLength(0);
    expect(r.from).toBe(0);
    expect(r.to).toBe(0);
  });
});

describe("formatPagedFooterLabel", () => {
  it("includes range, page, and solo lectura", () => {
    const label = formatPagedFooterLabel({
      from: 1,
      to: 15,
      visibleTotal: 44,
      page: 1,
      totalPages: 3,
    });
    expect(label).toBe("Mostrando 1–15 de 44 · Página 1 de 3 · solo lectura");
  });
});

describe("formatWarmCasesTableFooter", () => {
  it("section footer explains global queue total", () => {
    const label = formatWarmCasesTableFooter({
      from: 1,
      to: 2,
      visibleTotal: 2,
      loadedTotal: 2,
      page: 1,
      totalPages: 1,
      sectionName: "Pagos",
      globalQueueTotal: 44,
    });
    expect(label).toContain("Mostrando 1–2 de 2 en Pagos");
    expect(label).toContain("44 casos tibios en cola global");
    expect(label).not.toContain("API reportó");
  });

  it("main bandeja includes preset when requested", () => {
    const label = formatWarmCasesTableFooter({
      from: 1,
      to: 15,
      visibleTotal: 44,
      loadedTotal: 44,
      page: 1,
      totalPages: 3,
      presetLabel: "Clientes reales",
    });
    expect(label).toContain("vista: Clientes reales");
    expect(label).toContain("Página 1 de 3");
  });
});

describe("formatProspectosTableFooter", () => {
  it("shows paged range with loaded vs API total", () => {
    const { primary, truncationNote } = formatProspectosTableFooter({
      from: 1,
      to: 15,
      loaded: 50,
      apiTotal: 71,
      page: 1,
      totalPages: 4,
    });
    expect(primary).toBe(
      "Mostrando 1–15 de 50 cargados · API total 71 · Página 1 de 4 · solo lectura",
    );
    expect(truncationNote).toMatch(/más resultados/);
  });

  it("omits truncation note when all loaded", () => {
    const { truncationNote } = formatProspectosTableFooter({
      from: 1,
      to: 10,
      loaded: 10,
      apiTotal: 10,
      page: 1,
      totalPages: 1,
    });
    expect(truncationNote).toBeUndefined();
  });
});
