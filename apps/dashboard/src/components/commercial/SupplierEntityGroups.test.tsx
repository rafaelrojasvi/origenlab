import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { WarmCaseItem } from "../../api/commercialTypes";
import { SupplierEntityGroups } from "./SupplierEntityGroups";

const meta = {
  data_source: "sqlite" as const,
  reduced_mode: false,
  note: "",
  count: 3,
};

function supplierRow(
  email: string,
  category: WarmCaseItem["category"],
  subject: string,
  account: string,
  lastSeen: string,
): WarmCaseItem {
  return {
    case_id: email,
    last_email_id: 1,
    last_seen_at: lastSeen,
    account_name: account,
    contact_email: email,
    subject,
    category,
    status: "open",
    next_action: "",
    equipment_signal: "",
    snippet: "",
    gmail_url: null,
  };
}

describe("SupplierEntityGroups", () => {
  const items = [
    supplierRow(
      "sales@serva.de",
      "supplier_followup",
      "SERVA thread subject",
      "SERVA",
      "2026-05-20T10:00:00-04:00",
    ),
    supplierRow(
      "beatriz.bonon@ika.net.br",
      "supplier_quote_received",
      "IKA price response",
      "IKA",
      "2026-05-19T10:00:00-04:00",
    ),
  ];

  it("renders compact cards without list bullet markers", () => {
    const { container } = render(
      <SupplierEntityGroups
        backend="sqlite"
        allItems={items}
        meta={meta}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    const grid = screen.getByTestId("supplier-entity-cards");
    expect(grid.className).toMatch(/list-none/);
    expect(container.querySelector("ul")).toBeNull();
    expect(container.querySelector(".list-disc")).toBeNull();
    expect(container.querySelector("li")).toBeNull();
  });

  it("shows latest subject on supplier cards", () => {
    render(
      <SupplierEntityGroups
        backend="sqlite"
        allItems={items}
        meta={meta}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    screen.getByText("SERVA thread subject");
    screen.getByText("IKA price response");
    screen.getByText("Cotización recibida");
    screen.getByText("Seguimiento");
  });

  it("marks selected supplier and filters warm-case table", () => {
    render(
      <SupplierEntityGroups
        backend="sqlite"
        allItems={items}
        meta={meta}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    const ikaCard = screen.getByRole("button", { name: /IKA, 1 cotización/i });
    fireEvent.click(ikaCard);
    expect(screen.getByText("Seleccionado")).toBeTruthy();
    expect(ikaCard.getAttribute("aria-pressed")).toBe("true");
    screen.getByRole("heading", { name: /Hilos de IKA/i });
    screen.getByText("beatriz.bonon@ika.net.br");
    expect(screen.queryByText("sales@serva.de")).toBeNull();
  });

  it("clicking SERVA shows SERVA threads only", () => {
    render(
      <SupplierEntityGroups
        backend="sqlite"
        allItems={items}
        meta={meta}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /SERVA, 1 seguimiento/i }));
    screen.getByRole("heading", { name: /Hilos de SERVA/i });
    screen.getByText("sales@serva.de");
    expect(screen.queryByText("beatriz.bonon@ika.net.br")).toBeNull();
  });
});
