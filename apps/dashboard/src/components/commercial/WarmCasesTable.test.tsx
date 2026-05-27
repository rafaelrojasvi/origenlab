import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { normalizeWarmCaseItem } from "../../api/commercialParse";
import type { WarmCaseItem } from "../../api/commercialTypes";
import { WarmCasesTable } from "./WarmCasesTable";

const row: WarmCaseItem = {
  case_id: "gmail-contacto-1",
  last_email_id: 1,
  last_seen_at: "2026-05-19T10:00:00-04:00",
  account_name: "ACME Lab",
  contact_email: "buyer@acme.cl",
  subject: "Re: centrifuge quote",
  category: "client_reply",
  status: "open",
  next_action: "follow_up",
  equipment_signal: "centrifuge",
  snippet: "Short preview only",
  gmail_url: null,
};

describe("WarmCasesTable", () => {
  it("shows Clientes reales preset on initial render without mailto links", () => {
    render(
      <WarmCasesTable
        backend="sqlite"
        items={[row]}
        meta={{ data_source: "sqlite", reduced_mode: false, note: "", count: 1 }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    expect(screen.getByRole("button", { name: "Clientes reales" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    screen.getByText(/preset: Clientes reales · read-only/);
    expect(screen.queryByRole("link", { name: "mailto" })).toBeNull();
    screen.getByRole("button", { name: "Copy email" });
    screen.getByRole("button", { name: "buyer@acme.cl" });
  });

  it("renders rows without body fields", () => {
    render(
      <WarmCasesTable
        backend="sqlite"
        items={[row]}
        meta={{
          data_source: "sqlite",
          reduced_mode: false,
          note: "",
          count: 1,
        }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );

    screen.getByText("buyer@acme.cl");
    screen.getByText("ACME Lab");
    screen.getByText(/Short preview only/);
    expect(screen.queryByText(/body_preview/)).toBeNull();
  });

  it("shows loading state", () => {
    render(
      <WarmCasesTable
        backend="sqlite"
        items={[]}
        meta={null}
        loading
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    expect(document.querySelector('[role="status"]')).toBeTruthy();
  });

  it("shows error state", () => {
    render(
      <WarmCasesTable
        backend="sqlite"
        items={[]}
        meta={null}
        loading={false}
        error="Warm cases failed"
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    screen.getByText("Warm cases failed");
    screen.getByRole("button", { name: "Retry" });
  });

  it("renders sparse row without crashing", () => {
    render(
      <WarmCasesTable
        backend="sqlite"
        items={[
          normalizeWarmCaseItem(
            {
              last_seen_at: null,
              subject: null,
              category: undefined,
              status: null,
            },
            0,
          ),
        ]}
        meta={{
          data_source: "sqlite",
          reduced_mode: false,
          note: "",
          count: 1,
        }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Todo" }));
    const table = screen.getByRole("table");
    expect(table.textContent).toContain("Oportunidad");
  });

  it("shows empty state", () => {
    render(
      <WarmCasesTable
        backend="postgres"
        items={[]}
        meta={{
          data_source: "postgres_mirror",
          reduced_mode: true,
          note: "mirror lag",
          count: 0,
        }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    screen.getByText(/No warm cases returned from the API/);
    screen.getByText(/Postgres mirror/);
  });

  it("calls onContactSelect when contact email is clicked", () => {
    const onContactSelect = vi.fn();
    render(
      <WarmCasesTable
        backend="sqlite"
        items={[row]}
        meta={{
          data_source: "sqlite",
          reduced_mode: false,
          note: "",
          count: 1,
        }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={onContactSelect}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "buyer@acme.cl" }));
    expect(onContactSelect).toHaveBeenCalledWith("buyer@acme.cl");
  });

  it("filters rows by search and shows no-match state", () => {
    render(
      <WarmCasesTable
        backend="sqlite"
        items={[
          row,
          {
            ...row,
            case_id: "other",
            contact_email: "other@elsewhere.cl",
            account_name: "Elsewhere",
          },
        ]}
        meta={{ data_source: "sqlite", reduced_mode: false, note: "", count: 2 }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    fireEvent.change(screen.getByLabelText("Search warm cases"), {
      target: { value: "zzznomatch" },
    });
    screen.getByText(/No warm cases match the current search or filters/);
    expect(screen.queryByText("other@elsewhere.cl")).toBeNull();
  });

  it("opens contact drilldown after filtering to a single row", () => {
    const onContactSelect = vi.fn();
    render(
      <WarmCasesTable
        backend="sqlite"
        items={[
          row,
          {
            ...row,
            case_id: "other",
            contact_email: "hidden@hidden.cl",
            account_name: "Hidden",
          },
        ]}
        meta={{ data_source: "sqlite", reduced_mode: false, note: "", count: 2 }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={onContactSelect}
      />,
    );
    fireEvent.change(screen.getByLabelText("Search warm cases"), {
      target: { value: "acme" },
    });
    fireEvent.click(screen.getByRole("button", { name: "buyer@acme.cl" }));
    expect(onContactSelect).toHaveBeenCalledWith("buyer@acme.cl");
  });

  it("shows filtered count in footer with active preset", () => {
    render(
      <WarmCasesTable
        backend="sqlite"
        items={[row, { ...row, case_id: "b", contact_email: "x@y.cl" }]}
        meta={{ data_source: "sqlite", reduced_mode: false, note: "", count: 2 }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    screen.getByText(/preset: Clientes reales/);
    screen.getByText(/Showing 2 of 2 loaded cases/);
    fireEvent.change(screen.getByLabelText("Search warm cases"), {
      target: { value: "buyer@acme" },
    });
    screen.getByText(/Showing 1 of 2 loaded cases/);
    screen.getByText(/client filters active/);
  });

  it("hides internal contacts by default; toggle shows them", () => {
    render(
      <WarmCasesTable
        backend="sqlite"
        items={[
          row,
          {
            ...row,
            case_id: "internal",
            contact_email: "contacto@origenlab.cl",
            account_name: "OrigenLab",
          },
        ]}
        meta={{ data_source: "sqlite", reduced_mode: false, note: "", count: 2 }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
        initialFilters={{ preset: "todo" }}
      />,
    );
    expect(screen.queryByText("contacto@origenlab.cl")).toBeNull();
    screen.getByText("buyer@acme.cl");
    fireEvent.click(screen.getByLabelText("Hide internal OrigenLab contacts"));
    screen.getByText("contacto@origenlab.cl");
    screen.getByText(/Showing 2 of 2 loaded cases/);
  });

  const auditRows: WarmCaseItem[] = [
    {
      ...row,
      case_id: "dhl",
      contact_email: "monica.silva@dhl.com",
      account_name: "DHL",
      category: "vendor_logistics",
      subject: "Import",
    },
    {
      ...row,
      case_id: "banco",
      contact_email: "serviciodetransferencias@bancochile.cl",
      account_name: "Banco Chile",
      category: "payment_admin",
      subject: "FACTURA",
    },
    {
      ...row,
      case_id: "dlab",
      contact_email: "chloe.yang@dlabsci.com",
      account_name: "DLAB",
      category: "supplier_reply",
    },
    {
      ...row,
      case_id: "ollital",
      contact_email: "kelly@ollital.com",
      account_name: "Ollital",
      category: "supplier_reply",
    },
    {
      ...row,
      case_id: "ortoalresa",
      contact_email: "carmen.llorente@ortoalresa.com",
      account_name: "Ortoalresa",
      category: "supplier_reply",
    },
    {
      ...row,
      case_id: "udec",
      contact_email: "tatiana.beldarrain@udec.cl",
      account_name: "UdeC",
      category: "client_reply",
      subject: "Consulta",
    },
    {
      ...row,
      case_id: "internal",
      contact_email: "contacto@origenlab.cl",
      account_name: "OrigenLab",
      category: "client_reply",
    },
  ];

  function renderAudit() {
    return render(
      <WarmCasesTable
        backend="sqlite"
        items={auditRows}
        meta={{ data_source: "sqlite", reduced_mode: false, note: "", count: auditRows.length }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
  }

  it("defaults to Clientes reales preset and shows UdeC only from audit set", () => {
    renderAudit();
    screen.getByText("tatiana.beldarrain@udec.cl");
    expect(screen.queryByText("monica.silva@dhl.com")).toBeNull();
    expect(screen.queryByText("serviciodetransferencias@bancochile.cl")).toBeNull();
    expect(screen.queryByText("chloe.yang@dlabsci.com")).toBeNull();
    screen.getByText(/preset: Clientes reales/);
  });

  it("Logística preset shows DHL not client rows", () => {
    renderAudit();
    fireEvent.click(screen.getByRole("button", { name: "Logística" }));
    screen.getByText("monica.silva@dhl.com");
    expect(screen.queryByText("tatiana.beldarrain@udec.cl")).toBeNull();
    screen.getByText(/preset: Logística/);
  });

  it("Pagos/admin preset shows Banco not client rows", () => {
    renderAudit();
    fireEvent.click(screen.getByRole("button", { name: "Pagos/admin" }));
    screen.getByText("serviciodetransferencias@bancochile.cl");
    expect(screen.queryByText("tatiana.beldarrain@udec.cl")).toBeNull();
    screen.getByText(/preset: Pagos\/admin/);
  });

  it("Pagos/admin preset shows payment_received and transferencia snippet rows", () => {
    render(
      <WarmCasesTable
        backend="sqlite"
        items={[
          {
            ...row,
            case_id: "pago-recibido",
            contact_email: "tesoreria@hospital.cl",
            category: "payment_received",
            subject: "Comprobante pago",
          },
          {
            ...row,
            case_id: "transferencia",
            contact_email: "notify@example.com",
            category: "opportunity",
            subject: "Aviso",
            snippet: "Confirmación de transferencia",
          },
          row,
        ]}
        meta={{ data_source: "sqlite", reduced_mode: false, note: "", count: 3 }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Pagos/admin" }));
    screen.getByText("tesoreria@hospital.cl");
    screen.getByText("notify@example.com");
    expect(screen.queryByText("buyer@acme.cl")).toBeNull();
  });

  it("Clear filters resets search and preset to Clientes reales", () => {
    render(
      <WarmCasesTable
        backend="sqlite"
        items={[row, { ...row, case_id: "b", contact_email: "x@y.cl" }]}
        meta={{ data_source: "sqlite", reduced_mode: false, note: "", count: 2 }}
        loading={false}
        error={null}
        onRetry={() => {}}
        onContactSelect={() => {}}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Todo" }));
    expect(screen.getByRole("button", { name: "Todo" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.change(screen.getByLabelText("Search warm cases"), {
      target: { value: "buyer@acme" },
    });
    fireEvent.click(
      screen.getByRole("button", {
        name: "Clear search and dropdown filters; reset view to Clientes reales",
      }),
    );
    expect(screen.getByRole("button", { name: "Clientes reales" }).getAttribute("aria-pressed")).toBe(
      "true",
    );
    screen.getByText(/preset: Clientes reales · read-only/);
    expect((screen.getByLabelText("Search warm cases") as HTMLInputElement).value).toBe("");
  });

  it("Proveedores preset shows DLAB, Ollital, Ortoalresa", () => {
    renderAudit();
    fireEvent.click(screen.getByRole("button", { name: "Proveedores" }));
    screen.getByText("chloe.yang@dlabsci.com");
    screen.getByText("kelly@ollital.com");
    screen.getByText("carmen.llorente@ortoalresa.com");
    expect(screen.queryByText("monica.silva@dhl.com")).toBeNull();
    expect(screen.queryByText("tatiana.beldarrain@udec.cl")).toBeNull();
  });

  it("Todo preset shows all non-internal rows when hide-internal is on", () => {
    renderAudit();
    fireEvent.click(screen.getByRole("button", { name: "Todo" }));
    screen.getByText("monica.silva@dhl.com");
    screen.getByText("tatiana.beldarrain@udec.cl");
    expect(screen.queryByText("contacto@origenlab.cl")).toBeNull();
  });
});
