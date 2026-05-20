import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
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
      />,
    );
    screen.getByText("Warm cases failed");
    screen.getByRole("button", { name: "Retry" });
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
      />,
    );
    screen.getByText(/No warm cases returned/);
    screen.getByText(/Postgres mirror/);
  });
});
