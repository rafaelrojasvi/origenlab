import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { WarmCaseItem } from "../../api/commercialTypes";
import { CaseDetailDrawer } from "./CaseDetailDrawer";
import { WarmCasesTable } from "./WarmCasesTable";

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
  gmail_url: "https://mail.google.com/mail/u/0/#inbox/abc123",
};

const paymentRow: WarmCaseItem = {
  ...supplierRow,
  case_id: "pay-1",
  contact_email: "serviciodetransferencias@bancochile.cl",
  account_name: "Banco Chile",
  subject: "FACTURA 6",
  category: "payment_admin",
  next_action: "payment_admin",
  snippet: "Transferencia 12345678901234 cuenta corriente 001",
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

describe("CaseDetailDrawer", () => {
  it("shows supplier strategy when opened for supplier_quote_received", () => {
    render(
      <CaseDetailDrawer
        item={supplierRow}
        open
        onClose={() => {}}
        onContactSelect={() => {}}
      />,
    );
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/Recommended strategy/i)).toBeTruthy();
    expect(within(dialog).getByText(/Link this supplier price to the matching client opportunity/i)).toBeTruthy();
    expect(within(dialog).getByText(/Open Suppliers/i)).toBeTruthy();
  });

  it("shows payment strategy for payment_admin", () => {
    render(
      <CaseDetailDrawer item={paymentRow} open onClose={() => {}} onContactSelect={() => {}} />,
    );
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/do not treat this as a quoting thread/i)).toBeTruthy();
    expect(within(dialog).getByText(/Open Payments & logistics/i)).toBeTruthy();
  });

  it("shows deal strategy for deal_evidence_candidate", () => {
    render(
      <CaseDetailDrawer item={dealRow} open onClose={() => {}} onContactSelect={() => {}} />,
    );
    const dialog = screen.getByRole("dialog");
    expect(within(dialog).getByText(/commercial deals mirror/i)).toBeTruthy();
    expect(within(dialog).getByText(/Open Deals/i)).toBeTruthy();
  });

  it("does not render forbidden fields", () => {
    render(
      <CaseDetailDrawer item={paymentRow} open onClose={() => {}} onContactSelect={() => {}} />,
    );
    const dialog = screen.getByRole("dialog");
    const text = dialog.textContent ?? "";
    expect(text).not.toMatch(/gmail\.com/i);
    expect(text).not.toMatch(/mail\.google/i);
    expect(text).not.toMatch(/12345678901234/);
    expect(text).not.toMatch(/body_preview/i);
    expect(text).not.toMatch(/sqlite/i);
  });

  it("closes when Close is clicked", () => {
    const onClose = vi.fn();
    render(
      <CaseDetailDrawer item={supplierRow} open onClose={onClose} onContactSelect={() => {}} />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });
});

describe("WarmCasesTable case drawer", () => {
  it("opens drawer when a row is clicked", () => {
    render(
      <WarmCasesTable
        backend="sqlite"
        items={[supplierRow]}
        meta={{ data_source: "sqlite", reduced_mode: false, note: "", count: 1 }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
        initialFilters={{ preset: "todo" }}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Open case summary/i }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText(/Recommended strategy/i)).toBeTruthy();
  });
});
