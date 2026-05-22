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

  it("shows filtered count in footer", () => {
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
    screen.getByText(/Showing 2 of 2 loaded cases/);
    fireEvent.change(screen.getByLabelText("Search warm cases"), {
      target: { value: "buyer@acme" },
    });
    screen.getByText(/Showing 1 of 2 loaded cases/);
    screen.getByText(/client filters active/);
  });

  it("hides internal contacts when toggle is enabled", () => {
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
      />,
    );
    screen.getByText("contacto@origenlab.cl");
    fireEvent.click(screen.getByLabelText("Hide internal OrigenLab contacts"));
    expect(screen.queryByText("contacto@origenlab.cl")).toBeNull();
    screen.getByText("buyer@acme.cl");
    screen.getByText(/client filters active/);
  });
});
