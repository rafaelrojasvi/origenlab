import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ConfirmedPurchaseEventsSection } from "./ConfirmedPurchaseEventsSection";

describe("ConfirmedPurchaseEventsSection", () => {
  it("renders CEAF purchase event with CLP amounts and OC number", () => {
    render(
      <ConfirmedPurchaseEventsSection
        confirmed={{
          status: "ready",
          data: {
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
                suggested_action_es:
                  "Confirmar despacho, enviar factura y datos bancarios",
              },
            ],
          },
        }}
      />,
    );
    expect(screen.getByText(/OC 26172/)).toBeTruthy();
    expect(screen.getByText(/Centro de Estudios Avanzados en Fruticultura CEAF/)).toBeTruthy();
    expect(screen.getByText(/OC recibida/i)).toBeTruthy();
    expect(screen.getByText(/\$1\.260\.000 CLP/)).toBeTruthy();
    expect(screen.getByText(/\$1\.499\.400 CLP/)).toBeTruthy();
    expect(screen.getAllByText(/BlueSlick/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/ANID R23F0002/)).toBeTruthy();
  });

  it("shows loading state", () => {
    render(<ConfirmedPurchaseEventsSection confirmed={{ status: "loading" }} />);
    expect(screen.getByText(/Cargando órdenes de compra confirmadas/i)).toBeTruthy();
  });
});
