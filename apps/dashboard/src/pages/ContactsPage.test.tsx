import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DashboardDataContext } from "../context/DashboardDataContext";
import { ContactsPage } from "./ContactsPage";
import { leadListFixture } from "../test/fixtures/leadIntelFixtures";
import type { LeadProspectListItemUi, LeadProspectsListUi } from "../api/leadIntelTypes";

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

function contactedFixture(): LeadProspectsListUi {
  const base = leadListFixture();
  return {
    ...base,
    total: 2,
    items: base.items.filter((row) => row.source_type !== "deepsearch" || row.gmail_sent_count),
  };
}

function deepsearchFixture(): LeadProspectsListUi {
  const base = leadListFixture();
  return {
    ...base,
    total: 1,
    items: base.items.filter((row) => row.source_type === "deepsearch" && !row.is_blocked),
  };
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
    source_type: "gmail_historico",
    gmail_sent_count: 1,
  };
}

describe("ContactsPage", () => {
  beforeEach(() => {
    vi.mocked(fetchLeadProspectsMirror).mockImplementation(async (query) => {
      if (query?.contact_scope === "deepsearch") {
        return deepsearchFixture();
      }
      if (query?.q?.toLowerCase().includes("red")) {
        return {
          ...leadListFixture(),
          total: 1,
          items: [
            {
              ...leadListFixture().items[1],
              prospect_key: "redsalud",
              organization_name: "RedSalud",
              domain: "redsalud.gob.cl",
              email: "compras@redsalud.gob.cl",
              source_type: "gmail_historico",
              gmail_sent_count: 2,
            },
          ],
        };
      }
      return contactedFixture();
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("shows institution workspace title and groups for contacted scope", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "Clientes / instituciones" })).toBeTruthy();
      expect(screen.getByText("Gmail Hist Co")).toBeTruthy();
    });
    expect(screen.getByTestId("contacts-page")).toBeTruthy();
    expect(screen.getByTestId("institution-kpis")).toBeTruthy();
    expect(screen.queryByText("Acme Labs")).toBeNull();
  });

  it("defaults to contacted scope and excludes deepsearch-only rows", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(fetchLeadProspectsMirror).toHaveBeenCalled());
    expect(fetchLeadProspectsMirror).toHaveBeenCalledWith(
      expect.objectContaining({
        contact_scope: "contacted",
        include_blocked: false,
        limit: 100,
      }),
    );
    expect(screen.getByTestId("institution-scope-contacted").getAttribute("aria-selected")).toBe(
      "true",
    );
  });

  it("passes q to fetchLeadProspectsMirror when searching", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(fetchLeadProspectsMirror).toHaveBeenCalled());
    fireEvent.change(screen.getByTestId("institution-search"), {
      target: { value: "red" },
    });
    await waitFor(() => {
      expect(fetchLeadProspectsMirror).toHaveBeenCalledWith(
        expect.objectContaining({ q: "red", contact_scope: "contacted" }),
      );
    });
    await waitFor(() => expect(screen.getByText("RedSalud")).toBeTruthy());
  });

  it("refresh applies current search before debounce", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(fetchLeadProspectsMirror).toHaveBeenCalled());
    vi.mocked(fetchLeadProspectsMirror).mockClear();

    fireEvent.change(screen.getByTestId("institution-search"), {
      target: { value: "red" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Actualizar datos/i }));

    await waitFor(() => {
      expect(fetchLeadProspectsMirror).toHaveBeenCalledWith(
        expect.objectContaining({ q: "red", contact_scope: "contacted" }),
      );
    });
  });

  it("loads deepsearch scope when Investigación tab is selected", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByText("Gmail Hist Co")).toBeTruthy());
    fireEvent.click(screen.getByTestId("institution-scope-deepsearch"));
    await waitFor(() => {
      expect(fetchLeadProspectsMirror).toHaveBeenCalledWith(
        expect.objectContaining({ contact_scope: "deepsearch" }),
      );
      expect(screen.getByText("Acme Labs")).toBeTruthy();
      expect(screen.queryByText("Gmail Hist Co")).toBeNull();
    });
  });

  it("filters institution type client-side", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByText("Gmail Hist Co")).toBeTruthy());
    fireEvent.change(screen.getByTestId("institution-type-filter"), {
      target: { value: "laboratorio_servicio" },
    });
    await waitFor(() => {
      expect(screen.getByText("Gmail Hist Co")).toBeTruthy();
    });
  });

  it("shows mirror total summary line", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByTestId("institution-result-summary")).toBeTruthy());
    expect(screen.getByTestId("institution-result-summary").textContent).toMatch(
      /Mostrando \d+ de \d+ coincidencias del espejo/i,
    );
  });

  it("opens institution detail drawer with read-only note and no send actions", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByText("Gmail Hist Co")).toBeTruthy());
    fireEvent.click(screen.getByText("Gmail Hist Co"));
    await waitFor(() => {
      expect(screen.getByTestId("institution-drawer")).toBeTruthy();
      expect(screen.getByTestId("institution-readonly-note").textContent).toMatch(
        /No enviar desde este panel/i,
      );
    });
    const drawer = screen.getByTestId("institution-drawer");
    expect(within(drawer).queryByRole("button", { name: /enviar/i })).toBeNull();
  });

  it("does not render send or mutation buttons on the page", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByText("Gmail Hist Co")).toBeTruthy());
    expect(screen.queryByRole("button", { name: /enviar/i })).toBeNull();
    expect(screen.getByRole("button", { name: /Actualizar datos/i })).toBeTruthy();
  });

  it("renders updated explanatory copy and send disclaimer", async () => {
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByTestId("institution-send-disclaimer")).toBeTruthy());
    expect(screen.getByText(/historial OrigenLab publicado al espejo/i)).toBeTruthy();
    expect(screen.getByTestId("institution-send-disclaimer").textContent).toMatch(
      /contact-universe-review/i,
    );
  });

  it("shows friendly card error state when mirror load fails", async () => {
    vi.mocked(fetchLeadProspectsMirror).mockRejectedValue(
      new OperatorApiError('{"detail":"Input should be less than or equal to 100"}', 503),
    );
    render(wrap(<ContactsPage />));
    await waitFor(() => expect(screen.getByTestId("institution-load-error")).toBeTruthy());
    expect(screen.queryByRole("table")).toBeNull();
  });
});
