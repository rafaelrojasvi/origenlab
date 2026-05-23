import { describe, expect, it } from "vitest";
import type { WarmCaseItem } from "../api/commercialTypes";
import {
  DEFAULT_WARM_VIEW_PRESET,
  filterWarmCasesByViewPreset,
  matchesWarmCaseViewPreset,
} from "./warmCaseViewPreset";

function warmRow(
  partial: Partial<WarmCaseItem> & Pick<WarmCaseItem, "contact_email" | "category">,
): WarmCaseItem {
  return {
    case_id: partial.case_id ?? partial.contact_email,
    last_email_id: 1,
    last_seen_at: "2026-05-19T10:00:00Z",
    account_name: partial.account_name ?? "",
    subject: partial.subject ?? "",
    status: partial.status ?? "open",
    next_action: partial.next_action ?? "",
    equipment_signal: partial.equipment_signal ?? "",
    snippet: partial.snippet ?? "",
    gmail_url: null,
    ...partial,
  };
}

const AUDIT_ROWS: WarmCaseItem[] = [
  warmRow({
    case_id: "dhl",
    contact_email: "monica.silva@dhl.com",
    category: "vendor_logistics",
    account_name: "DHL",
  }),
  warmRow({
    case_id: "banco",
    contact_email: "serviciodetransferencias@bancochile.cl",
    category: "payment_admin",
    account_name: "Banco Chile",
  }),
  warmRow({
    case_id: "dlab",
    contact_email: "chloe.yang@dlabsci.com",
    category: "supplier_reply",
    account_name: "DLAB",
  }),
  warmRow({
    case_id: "ollital",
    contact_email: "kelly@ollital.com",
    category: "supplier_reply",
    account_name: "Ollital",
  }),
  warmRow({
    case_id: "ortoalresa",
    contact_email: "carmen.llorente@ortoalresa.com",
    category: "supplier_reply",
    account_name: "Ortoalresa",
  }),
  warmRow({
    case_id: "udec",
    contact_email: "tatiana.beldarrain@udec.cl",
    category: "client_reply",
    account_name: "UdeC",
  }),
  warmRow({
    case_id: "internal",
    contact_email: "contacto@origenlab.cl",
    category: "client_reply",
    account_name: "OrigenLab",
  }),
  warmRow({
    case_id: "equip",
    contact_email: "lab@hospital.cl",
    category: "client_reply",
    equipment_signal: "centrifuge",
    account_name: "Hospital",
  }),
];

describe("warmCaseViewPreset", () => {
  it("defaults to Clientes reales", () => {
    expect(DEFAULT_WARM_VIEW_PRESET).toBe("clientes_reales");
  });

  it("Clientes reales includes UdeC client_reply and excludes logistics, payments, suppliers", () => {
    const preset = "clientes_reales" as const;
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[5], preset)).toBe(true);
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[0], preset)).toBe(false);
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[1], preset)).toBe(false);
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[2], preset)).toBe(false);
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[3], preset)).toBe(false);
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[4], preset)).toBe(false);
  });

  it("Proveedores includes DLAB, Ollital, Ortoalresa and excludes DHL logistics", () => {
    const preset = "proveedores" as const;
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[2], preset)).toBe(true);
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[3], preset)).toBe(true);
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[4], preset)).toBe(true);
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[0], preset)).toBe(false);
  });

  it("Pagos/admin includes Banco Chile payment_admin", () => {
    const preset = "pagos_admin" as const;
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[1], preset)).toBe(true);
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[5], preset)).toBe(false);
  });

  it("Pagos/admin includes payment_received category", () => {
    const preset = "pagos_admin" as const;
    const row = warmRow({
      contact_email: "tesoreria@cliente.cl",
      category: "payment_received",
      subject: "Comprobante",
    });
    expect(matchesWarmCaseViewPreset(row, preset)).toBe(true);
  });

  it("Pagos/admin includes bancochile.cl and FACTURA/transferencia text signals", () => {
    const preset = "pagos_admin" as const;
    expect(
      matchesWarmCaseViewPreset(
        warmRow({
          contact_email: "alertas@bancochile.cl",
          category: "opportunity",
          subject: "Movimiento",
        }),
        preset,
      ),
    ).toBe(true);
    expect(
      matchesWarmCaseViewPreset(
        warmRow({
          contact_email: "notify@example.com",
          category: "opportunity",
          subject: "FACTURA 6",
        }),
        preset,
      ),
    ).toBe(true);
    expect(
      matchesWarmCaseViewPreset(
        warmRow({
          contact_email: "notify@example.com",
          category: "opportunity",
          subject: "Hola",
          snippet: "Confirmación de transferencia bancaria",
        }),
        preset,
      ),
    ).toBe(true);
    expect(
      matchesWarmCaseViewPreset(
        warmRow({
          contact_email: "notify@example.com",
          category: "client_reply",
          subject: "Consulta equipo",
        }),
        preset,
      ),
    ).toBe(false);
  });

  it("Logística includes DHL vendor_logistics", () => {
    const preset = "logistica" as const;
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[0], preset)).toBe(true);
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[1], preset)).toBe(false);
  });

  it("Con señal de equipo matches non-empty equipment_signal", () => {
    const preset = "con_senal_equipo" as const;
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[7], preset)).toBe(true);
    expect(matchesWarmCaseViewPreset(AUDIT_ROWS[5], preset)).toBe(false);
  });

  it("Todo includes all loaded rows", () => {
    expect(filterWarmCasesByViewPreset(AUDIT_ROWS, "todo")).toHaveLength(AUDIT_ROWS.length);
  });
});
