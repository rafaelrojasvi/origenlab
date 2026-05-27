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
    return { table_available: true, product: null, data_source: "postgres_mirror", read_only: true, disclaimer: "" };
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

  it("loads nine catalog products", async () => {
    render(<CatalogPage />);
    await waitFor(() => {
      expect(screen.getByText("9 productos catalogados")).toBeTruthy();
    });
    expect(screen.getByText("Tubo de vapor IKA RV10.70")).toBeTruthy();
    expect(screen.getByText("CRTOP Lab Reactor OLT-HP-5L")).toBeTruthy();
  });

  it("search filter calls list API with q param", async () => {
    render(<CatalogPage />);
    await waitFor(() => screen.getByText("9 productos catalogados"));

    fireEvent.change(screen.getByPlaceholderText("Buscar producto, marca o modelo"), {
      target: { value: "CRTOP" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Aplicar filtros" }));

    await waitFor(() => {
      expect(fetchCatalogProductsMirror).toHaveBeenCalledWith(
        expect.objectContaining({ q: "CRTOP", limit: 100 }),
      );
    });
  });

  it("opens CRTOP drawer with specs USD EXW and internal price label", async () => {
    render(<CatalogPage />);
    await waitFor(() => screen.getByText("CRTOP Lab Reactor OLT-HP-5L"));

    fireEvent.click(screen.getByRole("button", { name: "CRTOP Lab Reactor OLT-HP-5L" }));

    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Resumen")).toBeTruthy();
    expect(within(dialog).getByText("Alias / códigos")).toBeTruthy();
    expect(within(dialog).getByText("Especificaciones")).toBeTruthy();
    expect(within(dialog).getByText("Ofertas de proveedor")).toBeTruthy();
    expect(within(dialog).getByText("Historial de precios")).toBeTruthy();
    expect(within(dialog).getByText("Negocios y casos vinculados")).toBeTruthy();

    expect(within(dialog).getByText("USD 10600.00")).toBeTruthy();
    expect(within(dialog).getAllByText(/EXW/).length).toBeGreaterThan(0);
    expect(within(dialog).getByText("5 L")).toBeTruthy();
    expect(within(dialog).getByText("170–190 °C")).toBeTruthy();
    expect(within(dialog).getByText("Precio interno / no público")).toBeTruthy();
  });

  it("opens IKA drawer with pending currency and review labels", async () => {
    render(<CatalogPage />);
    await waitFor(() => screen.getByText("Tubo de vapor IKA RV10.70"));

    fireEvent.click(screen.getByRole("button", { name: "Tubo de vapor IKA RV10.70" }));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getByText(/Moneda pendiente/)).toBeTruthy();
    expect(within(dialog).getByText(/candidato a precio unitario/i)).toBeTruthy();
    expect(within(dialog).getByText(/antes de cotizar/i)).toBeTruthy();
    expect(within(dialog).getAllByText(/Requiere revisión/i).length).toBeGreaterThan(0);
  });

  it("shows SERVA deal refs without private evidence fields", async () => {
    render(<CatalogPage />);
    await waitFor(() => screen.getByText("BlueSlick™ 250 ml"));
    fireEvent.click(screen.getByRole("button", { name: "BlueSlick™ 250 ml" }));
    const dialog = await screen.findByRole("dialog");

    expect(within(dialog).getByText(/serva-ceaf-oc-26172/i)).toBeTruthy();
    const blob = within(dialog).getByText("Negocios y casos vinculados").closest("section")!.textContent ?? "";
    expect(blob).not.toMatch(/gmail|evidence|transfer_id|operation_id/i);
  });

  it("rendered catalog UI has no joined prose artifacts or forbidden privacy tokens", async () => {
    render(<CatalogPage />);
    await waitFor(() => screen.getByText("9 productos catalogados"));
    fireEvent.click(screen.getByRole("button", { name: "CRTOP Lab Reactor OLT-HP-5L" }));
    await screen.findByRole("dialog");

    const blob = document.body.textContent?.toLowerCase() ?? "";
    for (const artifact of CATALOG_FORBIDDEN_PROSE_ARTIFACTS) {
      expect(blob).not.toContain(artifact.toLowerCase());
    }
    expect(blob).not.toContain("swift");
    expect(blob).not.toContain("iban");
    expect(blob).not.toContain("gmail");
  });
});
