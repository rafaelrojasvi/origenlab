import { describe, expect, it } from "vitest";
import {
  formatProspectosTableFooter,
  formatWarmCasesTableFooter,
  paginateSlice,
} from "./clientTablePagination";

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
  it("shows loaded vs total", () => {
    const { primary, truncationNote } = formatProspectosTableFooter({
      loaded: 50,
      total: 71,
    });
    expect(primary).toBe("Mostrando 1–50 de 71 prospectos · solo lectura");
    expect(truncationNote).toMatch(/más resultados/);
  });

  it("omits truncation note when all loaded", () => {
    const { truncationNote } = formatProspectosTableFooter({ loaded: 10, total: 10 });
    expect(truncationNote).toBeUndefined();
  });
});
