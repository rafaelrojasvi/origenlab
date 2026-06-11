import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DashboardDataContext } from "../context/DashboardDataContext";
import { ContactsPage } from "./ContactsPage";
import { leadListFixture } from "../test/fixtures/leadIntelFixtures";
import type { LeadProspectListItemUi } from "../api/leadIntelTypes";

vi.mock("../api/mirrorLeadIntelClient", () => ({
  fetchLeadProspectsMirror: vi.fn(),
}));

import { fetchLeadProspectsMirror } from "../api/mirrorLeadIntelClient";
import { OperatorApiError } from "../api/operatorClient";

function wrap(ui: ReactNode) {
  return (
    <DashboardDataContext.Provider
      value={
        {
          setContactEmail: vi.fn(),
        } as never
      }
    >
      {ui}
    </DashboardDataContext.Provider>
  );
}

function rowWithMissingEmail(): LeadProspectListItemUi {
  return {
    ...leadListFixture().items[0],
    prospect_key: "no-email",
    organization_name: "Sin Email SA",
    domain: "sinemail.cl",
    email: null,
    classification: "research_only_contact_needed",
    final_score: 60,
  };
}

describe("ContactsPage", () => {
  beforeEach(() => {
    vi.mocked(fetchLeadProspectsMirror).mockResolvedValue(leadListFixture());
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows institution workspace title and groups", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Clientes / instituciones" })).toBeTruthy();
      expect(screen.getByText("Acme Labs")).toBeTruthy();
      expect(screen.getByText("Gmail Hist Co")).toBeTruthy();
    });
    expect(screen.getByTestId("contacts-page")).toBeTruthy();
    expect(screen.getByTestId("institution-kpis")).toBeTruthy();
    expect(screen.getAllByTestId("institution-row").length).toBeGreaterThanOrEqual(2);
  });

  it("filters by Gmail history preset", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByText("Gmail Hist Co")).toBeTruthy());
    fireEvent.change(screen.getByTestId("institution-preset-filter"), {
      target: { value: "gmail_history" },
    });
    await waitFor(() => {
      expect(screen.getByText("Gmail Hist Co")).toBeTruthy();
      expect(screen.queryByText("Acme Labs")).toBeNull();
    });
  });

  it("filters missing email preset", async () => {
    vi.mocked(fetchLeadProspectsMirror).mockResolvedValue({
      ...leadListFixture(),
      items: [...leadListFixture().items, rowWithMissingEmail()],
    });
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByText("Sin Email SA")).toBeTruthy());
    fireEvent.change(screen.getByTestId("institution-preset-filter"), {
      target: { value: "missing_email" },
    });
    await waitFor(() => {
      expect(screen.getByText("Sin Email SA")).toBeTruthy();
      expect(screen.queryByText("Acme Labs")).toBeNull();
    });
  });

  it("filters blocked and risk preset", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByText("Blocked Co")).toBeTruthy());
    fireEvent.change(screen.getByTestId("institution-preset-filter"), {
      target: { value: "blocked_risk" },
    });
    await waitFor(() => {
      expect(screen.getByText("Blocked Co")).toBeTruthy();
      expect(screen.queryByText("Acme Labs")).toBeNull();
    });
  });

  it("opens institution detail drawer with read-only note and no send actions", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByText("Acme Labs")).toBeTruthy());
    fireEvent.click(screen.getByText("Acme Labs"));
    await waitFor(() => {
      expect(screen.getByTestId("institution-drawer")).toBeTruthy();
      expect(screen.getByTestId("institution-readonly-note").textContent).toMatch(
        /No enviar desde este panel/i,
      );
    });
    const drawer = screen.getByTestId("institution-drawer");
    expect(within(drawer).queryByRole("button", { name: /enviar/i })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: /mandar/i })).toBeNull();
    expect(within(drawer).queryByRole("button", { name: /send/i })).toBeNull();
  });

  it("does not render send or mutation buttons on the page", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByText("Acme Labs")).toBeTruthy());
    expect(screen.queryByRole("button", { name: /enviar/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /exportar/i })).toBeNull();
    expect(screen.getByRole("button", { name: /Actualizar datos/i })).toBeTruthy();
  });

  it("requests prospects with include_blocked false and limit 100", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(fetchLeadProspectsMirror).toHaveBeenCalled());
    expect(fetchLeadProspectsMirror).toHaveBeenCalledWith({
      limit: 100,
      include_blocked: false,
    });
  });

  it("renders mirror limit note for operators", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByTestId("institution-mirror-limit-note")).toBeTruthy());
    expect(screen.getByTestId("institution-mirror-limit-note").textContent).toMatch(
      /hasta 100 prospectos/i,
    );
  });

  it("shows friendly card error state when mirror load fails", async () => {
    vi.mocked(fetchLeadProspectsMirror).mockRejectedValue(
      new OperatorApiError('{"detail":"Input should be less than or equal to 100"}', 503),
    );
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByTestId("institution-load-error")).toBeTruthy());
    expect(screen.getByTestId("institution-load-error").textContent).toMatch(
      /No se pudieron cargar las instituciones desde el espejo/i,
    );
    expect(screen.getByText("Ver detalle técnico")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
