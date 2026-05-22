import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PurchaseSignalsSection } from "./PurchaseSignalsSection";

describe("PurchaseSignalsSection", () => {
  it("renders empty state when no purchase rows", () => {
    render(
      <PurchaseSignalsSection
        purchases={{
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
      screen.getByText(/No hay señales de compra reciente detectadas en el espejo actual/i),
    ).toBeTruthy();
  });
});
