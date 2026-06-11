import { fireEvent, render, screen, within } from "@testing-library/react";
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

  it("renders KPI cards and split workspace", () => {
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
    const kpis = screen.getByTestId("supplier-kpis");
    expect(within(kpis).getByText("Proveedores")).toBeTruthy();
    expect(within(kpis).getByText("Cotizaciones recibidas")).toBeTruthy();
    expect(within(kpis).getByText("Seguimientos")).toBeTruthy();
    expect(within(kpis).getByText("Hilos activos")).toBeTruthy();
    expect(screen.getByTestId("suppliers-workspace")).toBeTruthy();
    expect(screen.getByTestId("supplier-detail-panel")).toBeTruthy();
  });

  it("renders compact provider cards without list bullet markers", () => {
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
    expect(container.querySelector("ul")).toBeNull();
    expect(container.querySelector(".list-disc")).toBeNull();
    expect(container.querySelector("li")).toBeNull();
    expect(grid.querySelectorAll('[data-testid="supplier-entity-card"]').length).toBe(2);
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
    const cards = screen.getByTestId("supplier-entity-cards");
    expect(within(cards).getByText("SERVA thread subject")).toBeTruthy();
    expect(within(cards).getByText("IKA price response")).toBeTruthy();
    expect(within(cards).getByText("Cotización recibida")).toBeTruthy();
    expect(within(cards).getByText("Seguimiento")).toBeTruthy();
  });

  it("auto-selects first provider and shows detail panel", () => {
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
    const servaCard = screen.getByRole("button", { name: /SERVA, 1 caso en espejo/i });
    expect(servaCard.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("supplier-detail-title").textContent).toBe("SERVA");
    screen.getByText("sales@serva.de");
    expect(screen.queryByText("beatriz.bonon@ika.net.br")).toBeNull();
    screen.getByTestId("supplier-readonly-note");
  });

  it("selecting another provider updates detail panel", () => {
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
    const ikaCard = screen.getByRole("button", { name: /IKA, 1 caso en espejo/i });
    fireEvent.click(ikaCard);
    expect(ikaCard.getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByTestId("supplier-detail-title").textContent).toBe("IKA");
    screen.getByText("beatriz.bonon@ika.net.br");
    expect(screen.queryByText("sales@serva.de")).toBeNull();
  });

  it("search narrows visible provider cards", () => {
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
    fireEvent.change(screen.getByTestId("supplier-search"), { target: { value: "IKA" } });
    const cards = screen.getByTestId("supplier-entity-cards");
    expect(within(cards).queryByRole("button", { name: /SERVA/i })).toBeNull();
    expect(within(cards).getByRole("button", { name: /IKA/i })).toBeTruthy();
    expect(screen.getByTestId("supplier-detail-title").textContent).toBe("IKA");
  });

  it("shows mirror scope and missing audit fallback in detail panel", () => {
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
    expect(screen.getByTestId("supplier-mirror-scope-note").textContent).toMatch(
      /casos tibios del espejo/i,
    );
    expect(screen.getByTestId("supplier-gmail-hint").textContent).toMatch(
      /Sin snapshot Gmail publicado/i,
    );
  });

  it("shows SQLite audit counts when snapshot present", () => {
    render(
      <SupplierEntityGroups
        backend="sqlite"
        allItems={items}
        auditSnapshot={{
          schema_version: 1,
          generated_at_utc: "2026-06-11T12:00:00+00:00",
          source: "sqlite:gmail:contacto",
          lookback_days: 180,
          domains: [
            {
              domain: "serva.de",
              message_count: 9,
              sent_count: 5,
              received_count: 4,
              thread_count: 1,
              latest_email_at: "2026-06-10T10:00:00+00:00",
              latest_subject_safe: "SERVA quote",
              has_attachments: false,
              matched_aliases: ["serva.de"],
            },
          ],
        }}
        meta={meta}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    expect(screen.getByTestId("supplier-gmail-hint").textContent).toMatch(
      /9 mensajes · 5 enviados · 4 recibidos · 1 hilo/i,
    );
    expect(
      screen.getByRole("button", { name: /SERVA, 1 caso en espejo · 9 mensajes SQLite\/Gmail/i }),
    ).toBeTruthy();
  });

  it("does not introduce send, export, or write buttons", () => {
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
    expect(screen.queryByRole("button", { name: /enviar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /exportar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /mandar/i })).toBeNull();
  });
});
