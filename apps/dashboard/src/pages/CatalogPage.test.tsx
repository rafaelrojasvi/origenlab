import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CATALOG_FORBIDDEN_PROSE_ARTIFACTS } from "../api/catalogParse";
import { CatalogPage } from "./CatalogPage";
import {
  catalogListFixture,
  crtopDetailFixture,
  ikaDetailFixture,
  servaBlueslickDetailFixture,
} from "../test/fixtures/catalogMirrorFixtures";

vi.mock("../api/mirrorCatalogClient", () => ({
  fetchCatalogProductsMirror: vi.fn(),
  fetchCatalogProductDetailMirror: vi.fn(),
}));

import {
  fetchCatalogProductDetailMirror,
  fetchCatalogProductsMirror,
} from "../api/mirrorCatalogClient";

function mockCatalogList() {
  vi.mocked(fetchCatalogProductsMirror).mockResolvedValue(catalogListFixture());
}

function mockDetailByKey() {
  vi.mocked(fetchCatalogProductDetailMirror).mockImplementation(async (key: string) => {
    if (key === "crtop-olt-hp-5l") {
      return crtopDetailFixture();
    }
    if (key === "ika-rv10-70-vapor-tube") {
      return ikaDetailFixture();
    }
    if (key === "serva-blueslick-250ml") {
      return servaBlueslickDetailFixture();
    }
    return {
      table_available: true,
      product: null,
      data_source: "postgres_mirror",
      read_only: true,
      disclaimer: "",
    };
  });
}

describe("CatalogPage", () => {
  beforeEach(() => {
    mockCatalogList();
    mockDetailByKey();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("loads nine catalog products with real category names", async () => {
    render(<CatalogPage />);
    await waitFor(() => {
      expect(screen.getByText("9 productos catalogados")).toBeTruthy();
      expect(screen.getAllByText("Reactor de laboratorio").length).toBeGreaterThan(0);
    });
    const table = screen.getByRole("table");
    expect(within(table).queryByText("Ver detalle")).toBeNull();
  });

  it("brand filter chip toggles off and Limpiar filtros resets", async () => {
    render(<CatalogPage />);
    await waitFor(() => screen.getByText("9 productos catalogados"));

    fireEvent.click(screen.getByRole("button", { name: "IKA", pressed: false }));
    await waitFor(() => {
      expect(fetchCatalogProductsMirror).toHaveBeenCalledWith(
        expect.objectContaining({ brand: "IKA" }),
      );
    });

    fireEvent.click(screen.getByRole("button", { name: "IKA", pressed: true }));
    await waitFor(() => {
      const last = vi.mocked(fetchCatalogProductsMirror).mock.calls.at(-1)?.[0];
      expect(last?.brand).toBeUndefined();
    });

    fireEvent.click(screen.getByRole("button", { name: "Limpiar filtros" }));
    await waitFor(() => {
      expect(fetchCatalogProductsMirror).toHaveBeenCalledWith({ limit: 100 });
    });
  });

  it("clicking table row opens drawer", async () => {
    render(<CatalogPage />);
    await waitFor(() => screen.getByText("CRTOP Lab Reactor OLT-HP-5L"));

    const row = screen.getByRole("button", { name: /Abrir ficha de CRTOP Lab Reactor/i });
    fireEvent.click(row);

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Ficha técnica")).toBeTruthy();
  });

  it("CRTOP row shows formatted offer summary", async () => {
    render(<CatalogPage />);
    await waitFor(() => {
      expect(screen.getByText(/USD 10\.600,00/)).toBeTruthy();
      expect(screen.getByText(/EXW/)).toBeTruthy();
      expect(screen.getByText(/1 unidad/)).toBeTruthy();
    });
  });

  it("opens CRTOP drawer with ficha técnica specs and internal price", async () => {
    render(<CatalogPage />);
    await waitFor(() => {
      expect(screen.getByText("CRTOP Lab Reactor OLT-HP-5L")).toBeTruthy();
      expect(screen.getByText(/10\.600,00/)).toBeTruthy();
    });

    fireEvent.click(screen.getByRole("button", { name: /Abrir ficha de CRTOP Lab Reactor/i }));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getByText(/Ficha del producto/)).toBeTruthy();
    expect(within(dialog).getByText("Resumen")).toBeTruthy();
    expect(within(dialog).getByText("Ficha técnica")).toBeTruthy();
    expect(within(dialog).getByText("Ofertas de proveedor")).toBeTruthy();
    expect(within(dialog).getByText("Historial de precios")).toBeTruthy();
    expect(within(dialog).getByText("Negocios y casos vinculados")).toBeTruthy();

    expect(
      within(dialog).getAllByText((_, el) => (el?.textContent ?? "").includes("10.600,00")).length,
    ).toBeGreaterThan(0);
    expect(within(dialog).getAllByText(/EXW/).length).toBeGreaterThan(0);
    expect(within(dialog).getByText("5 L")).toBeTruthy();
    expect(within(dialog).getByText("Precio interno / no público")).toBeTruthy();
    expect(within(dialog).queryByText(/2026-05-27T00:00:00Z/)).toBeNull();
    expect(within(dialog).getByText(/27 may 2026/)).toBeTruthy();
  });

  it("opens IKA drawer with Moneda pendiente and quantity phrasing", async () => {
    render(<CatalogPage />);
    await waitFor(() => screen.getByText("Tubo de vapor IKA RV10.70"));

    fireEvent.click(screen.getByRole("button", { name: /Abrir ficha de Tubo de vapor IKA/i }));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getByText(/Moneda pendiente/)).toBeTruthy();
    expect(within(dialog).getByText(/Solicitud cliente: 3 unidades/)).toBeTruthy();
    expect(within(dialog).getByText(/posible precio unitario/i)).toBeTruthy();
    expect(within(dialog).getByText(/antes de cotizar/i)).toBeTruthy();
  });

  it("rendered UI preserves common Spanish words and blocks artifacts", async () => {
    render(<CatalogPage />);
    await waitFor(() => screen.getByText("9 productos catalogados"));
    fireEvent.click(screen.getByRole("button", { name: /Abrir ficha de CRTOP Lab Reactor/i }));
    await screen.findByRole("dialog");

    const blob = document.body.textContent?.toLowerCase() ?? "";
    expect(blob).toContain("modelo");
    expect(blob).toContain("proveedor");
    expect(blob).not.toContain("oportunida de s");
    for (const artifact of CATALOG_FORBIDDEN_PROSE_ARTIFACTS) {
      expect(blob).not.toContain(artifact.toLowerCase());
    }
    expect(blob).not.toContain("oportunida de s");
    expect(blob).not.toContain("swift");
    expect(blob).not.toContain("gmail");
  });
});
