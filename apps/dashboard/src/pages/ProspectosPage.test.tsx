import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ProspectosPage } from "./ProspectosPage";
import {
  leadBlockedDetailFixture,
  leadListFixture,
  leadSameDomainDetailFixture,
  leadSummaryFixture,
  leadTenderDetailFixture,
} from "../test/fixtures/leadIntelFixtures";

vi.mock("../api/mirrorLeadIntelClient", () => ({
  fetchLeadProspectsMirror: vi.fn(),
  fetchLeadProspectDetailMirror: vi.fn(),
  fetchLeadResearchSummaryMirror: vi.fn(),
}));

import {
  fetchLeadProspectDetailMirror,
  fetchLeadProspectsMirror,
  fetchLeadResearchSummaryMirror,
} from "../api/mirrorLeadIntelClient";

describe("ProspectosPage", () => {
  beforeEach(() => {
    vi.mocked(fetchLeadResearchSummaryMirror).mockResolvedValue(leadSummaryFixture());
    vi.mocked(fetchLeadProspectsMirror).mockResolvedValue(leadListFixture());
    vi.mocked(fetchLeadProspectDetailMirror).mockImplementation(async (key: string) => {
      if (key === "blocked") return leadBlockedDetailFixture();
      if (key === "same") return leadSameDomainDetailFixture();
      if (key === "tender") return leadTenderDetailFixture();
      return leadBlockedDetailFixture();
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders KPIs and Spanish table labels", async () => {
    render(<ProspectosPage />);
    await waitFor(() => {
      expect(screen.getByText("Net-new seguros")).toBeTruthy();
      expect(screen.getByText("Acme Labs")).toBeTruthy();
    });
    expect(screen.getByText("Organización")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /enviar/i })).toBeNull();
  });

  it("shows disclaimer with space after OrigenLab before Revisión", async () => {
    render(<ProspectosPage />);
    await waitFor(() => {
      expect(screen.getByText(/historial OrigenLab\. Revisión humana/i)).toBeTruthy();
    });
    expect(screen.queryByText(/OrigenLab\.Revisión/i)).toBeNull();
  });

  it("opens drawer with No contactar for blocked prospect", async () => {
    render(<ProspectosPage />);
    await waitFor(() => expect(screen.getByText("Blocked Co")).toBeTruthy());
    fireEvent.click(screen.getByText("Blocked Co"));
    await waitFor(() => {
      expect(screen.getByText("Ficha del prospecto")).toBeTruthy();
      expect(screen.getByTestId("prospect-safety-banner").textContent).toMatch(/No contactar/i);
    });
  });

  it("shows same-domain warning in drawer", async () => {
    vi.mocked(fetchLeadProspectsMirror).mockResolvedValue({
      ...leadListFixture(),
      items: [
        {
          ...leadListFixture().items[0],
          prospect_key: "same",
          organization_name: "Old Domain",
          classification: "same_domain_contacted_review",
          status: "same_domain_review",
        },
      ],
    });
    render(<ProspectosPage />);
    await waitFor(() => expect(screen.getByText("Old Domain")).toBeTruthy());
    fireEvent.click(screen.getByText("Old Domain"));
    await waitFor(() => {
      expect(screen.getByTestId("prospect-safety-banner").textContent).toMatch(/historial con este dominio/i);
    });
  });

  it("shows public tender route copy", async () => {
    vi.mocked(fetchLeadProspectsMirror).mockResolvedValue({
      ...leadListFixture(),
      items: [
        {
          ...leadListFixture().items[0],
          prospect_key: "tender",
          organization_name: "Hospital Demo",
          classification: "public_tender_review",
          status: "public_tender_review",
        },
      ],
    });
    render(<ProspectosPage />);
    await waitFor(() => expect(screen.getByText("Hospital Demo")).toBeTruthy());
    fireEvent.click(screen.getByText("Hospital Demo"));
    await waitFor(() => {
      expect(screen.getByTestId("prospect-safety-banner").textContent).toMatch(/equivalencia técnica/i);
    });
  });
});
