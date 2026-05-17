import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { CommercialPurchaseEventsList } from "../api/types";
import { ComprasTab } from "./ComprasTab";

const ceafPayload: CommercialPurchaseEventsList = {
  table_available: true,
  total: 1,
  limit: 20,
  disclaimer: "test",
  items: [
    {
      id: 1,
      buyer_org_name: "Centro de Estudios Avanzados en Fruticultura CEAF",
      buyer_contact_name: "Carlos Garay Sotelo",
      buyer_contact_email: "cgaray@ceaf.cl",
      purchase_status: "purchase_order_received",
      purchase_status_label_es: "OC recibida",
      oc_number: "26172",
      quote_number: "011728A-26",
      project_name: "ANID",
      project_code: "R23F0002",
      net_amount_clp: 1_260_000,
      iva_amount_clp: 239_400,
      gross_amount_clp: 1_499_400,
      currency: "CLP",
      line_items: [
        {
          line_number: 1,
          product_name: "BlueSlick™ 250 ml",
          brand: "SERVA",
          net_amount_clp: 695_000,
        },
      ],
      product_summary: "BlueSlick™ 250 ml",
      suggested_action_es: "Confirmar despacho, enviar factura y datos bancarios",
    },
  ],
};

vi.mock("../api/client", async (importOriginal) => {
  const mod = await importOriginal<typeof import("../api/client")>();
  return {
    ...mod,
    fetchCommercialPurchaseEvents: vi.fn(),
  };
});

import { fetchCommercialPurchaseEvents } from "../api/client";

describe("ComprasTab", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders confirmed purchase events from API above heuristic section", async () => {
    vi.mocked(fetchCommercialPurchaseEvents).mockResolvedValue(ceafPayload);

    render(
      <ComprasTab
        purchaseSignals={{
          scope: "canonical",
          table_available: true,
          items: [],
          total: 0,
          limit: 20,
          label_filter: "purchase_or_order_signal",
        }}
      />,
    );

    expect(
      screen.getByRole("heading", { level: 3, name: /Órdenes de compra confirmadas/i }),
    ).toBeTruthy();

    await waitFor(() => {
      expect(screen.getByText(/OC 26172/)).toBeTruthy();
      expect(screen.getByText(/Fruticultura CEAF/)).toBeTruthy();
    });

    expect(screen.getByText(/OC recibida/i)).toBeTruthy();
    expect(screen.getByText(/\$1\.499\.400 CLP/)).toBeTruthy();
    expect(screen.getByText(/011728A-26/)).toBeTruthy();
    expect(screen.getByText(/ANID R23F0002/)).toBeTruthy();
    expect(screen.getByText(/Señales detectadas/i)).toBeTruthy();
    expect(fetchCommercialPurchaseEvents).toHaveBeenCalledWith(20);
  });

  it("shows error when commercial API fails", async () => {
    vi.mocked(fetchCommercialPurchaseEvents).mockRejectedValue(
      new Error("proxy missing"),
    );

    render(<ComprasTab purchaseSignals={null} />);

    await waitFor(() => {
      expect(screen.getByText(/No se pudieron cargar las OC confirmadas/i)).toBeTruthy();
    });
  });
});
