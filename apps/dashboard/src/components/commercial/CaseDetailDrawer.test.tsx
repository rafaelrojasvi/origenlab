import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { WarmCaseItem } from "../../api/commercialTypes";
import { CaseDetailDrawer } from "./CaseDetailDrawer";

const supplierRow: WarmCaseItem = {
  case_id: "sup-1",
  last_email_id: 1,
  last_seen_at: "2026-05-19T10:00:00-04:00",
  account_name: "IKA",
  contact_email: "beatriz.bonon@ika.net.br",
  subject: "RE: RV10.70 price response",
  category: "supplier_quote_received",
  status: "waiting",
  next_action: "supplier_reply",
  equipment_signal: "RV10.70",
  snippet: "Please find attached pricing",
  gmail_url: null,
};

const paymentRow: WarmCaseItem = {
  ...supplierRow,
  case_id: "pay-1",
  contact_email: "serviciodetransferencias@bancochile.cl",
  account_name: "Banco Chile",
  subject: "FACTURA 6",
  category: "payment_admin",
  next_action: "payment_admin",
  snippet: "Transferencia 12345678901234 cuenta corriente",
};

const dealRow: WarmCaseItem = {
  ...supplierRow,
  case_id: "deal-1",
  contact_email: "cgaray@ceaf.cl",
  account_name: "CEAF",
  subject: "Remite OC N 26172",
  category: "deal_evidence_candidate",
  next_action: "waiting_client",
  snippet: "Orden de compra adjunta",
};

describe("CaseDetailDrawer (español)", () => {
  it("muestra estrategia de proveedor y secciones en español", () => {
    render(
      <CaseDetailDrawer
        item={supplierRow}
        open
        onClose={() => {}}
        onContactSelect={() => {}}
      />,
    );
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText("Qué pasó")).toBeTruthy();
    expect(within(dialog).getByText("Estrategia recomendada")).toBeTruthy();
    expect(within(dialog).getByText("Próxima acción")).toBeTruthy();
    expect(within(dialog).getAllByText(/oportunidad de cliente/i).length).toBeGreaterThan(0);
    expect(within(dialog).getByRole("button", { name: /Ir a Proveedores/i })).toBeTruthy();
    expect(dialog.textContent).not.toMatch(/supplier_quote_received/);
  });

  it("muestra estrategia de pago", () => {
    render(
      <CaseDetailDrawer item={paymentRow} open onClose={() => {}} onContactSelect={() => {}} />,
    );
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/flujo operativo/i)).toBeTruthy();
    expect(within(dialog).getByRole("button", { name: /Ir a Pagos y logística/i })).toBeTruthy();
  });

  it("muestra estrategia de negocio", () => {
    render(
      <CaseDetailDrawer item={dealRow} open onClose={() => {}} onContactSelect={() => {}} />,
    );
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByRole("button", { name: /Ir a Negocios/i })).toBeTruthy();
    expect(within(dialog).getByText(/cotización duplicada/i)).toBeTruthy();
  });

  it("no muestra campos prohibidos", () => {
    render(
      <CaseDetailDrawer item={paymentRow} open onClose={() => {}} onContactSelect={() => {}} />,
    );
    const dialog = screen.getByRole("dialog");
    const text = dialog.textContent ?? "";
    expect(text).not.toMatch(/gmail\.com/i);
    expect(text).not.toMatch(/12345678901234/);
  });

  it("formats last_seen_at without raw ISO timestamp", () => {
    render(
      <CaseDetailDrawer item={supplierRow} open onClose={() => {}} onContactSelect={() => {}} />,
    );
    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).not.toContain("2026-05-19T10:00:00-04:00");
    expect(dialog.textContent).toMatch(/Última actividad:/);
    expect(dialog.textContent).toMatch(/2026/);
  });

  it("shows human-readable next action sentence in drawer", () => {
    const row: WarmCaseItem = {
      ...supplierRow,
      next_action: "Cotización enviada; monitorear respuesta del cliente.",
    };
    render(<CaseDetailDrawer item={row} open onClose={() => {}} onContactSelect={() => {}} />);
    const dialog = screen.getByRole("dialog");
    expect(
      within(dialog).getByText("Cotización enviada; monitorear respuesta del cliente."),
    ).toBeTruthy();
    expect(dialog.textContent).not.toMatch(/Sin clasificar/);
  });

  it("cierra al pulsar Cerrar", () => {
    const onClose = vi.fn();
    render(
      <CaseDetailDrawer item={supplierRow} open onClose={onClose} onContactSelect={() => {}} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(onClose).toHaveBeenCalled();
  });
});
