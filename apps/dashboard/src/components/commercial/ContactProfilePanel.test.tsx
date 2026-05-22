import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { OperatorApiError } from "../../api/operatorClient";
import { ContactProfilePanel } from "./ContactProfilePanel";

vi.mock("../../api/operatorClient", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../api/operatorClient")>();
  return {
    ...actual,
    fetchContactProfile: vi.fn(),
  };
});

import { fetchContactProfile } from "../../api/operatorClient";

describe("ContactProfilePanel", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("shows loading then profile content", async () => {
    vi.mocked(fetchContactProfile).mockResolvedValue({
      meta: { data_source: "sqlite", read_only: true, reduced_mode: false, note: "" },
      contact: {
        email: "buyer@acme.cl",
        normalized_email: "buyer@acme.cl",
        name: "Buyer",
        domain: "acme.cl",
        organization_name: "ACME",
        organization_domain: "acme.cl",
        last_seen_at: null,
        first_seen_at: null,
        message_count: 3,
      },
      outreach: {
        state: "open",
        last_contacted_at: null,
        source: null,
        notes: null,
        do_not_repeat: false,
        suppressed_email: false,
        suppressed_domain: false,
      },
      sent_history: { sent_count: 0, latest_sent_at: null, latest_subject: null },
      warnings: [],
    });

    render(
      <ContactProfilePanel
        email="buyer@acme.cl"
        open
        onClose={() => {}}
        backend="sqlite"
        mirrorBackend={false}
      />,
    );

    expect(screen.getByText("Read-only contact profile")).toBeTruthy();
    await waitFor(() => {
      expect(screen.getByText("Buyer")).toBeTruthy();
    });
    expect(screen.queryByText(/sqlite_path|source_path|body_preview/i)).toBeNull();
  });

  it("shows error and retry", async () => {
    vi.mocked(fetchContactProfile).mockRejectedValue(
      new OperatorApiError("not found", 404),
    );

    render(
      <ContactProfilePanel
        email="missing@acme.cl"
        open
        onClose={() => {}}
        backend="sqlite"
        mirrorBackend={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Contact not found.")).toBeTruthy();
    });

    vi.mocked(fetchContactProfile).mockResolvedValue({
      meta: { data_source: "sqlite", read_only: true, reduced_mode: false, note: "" },
      contact: {
        email: "missing@acme.cl",
        normalized_email: "missing@acme.cl",
        name: "",
        domain: "",
        organization_name: "",
        organization_domain: "",
        last_seen_at: null,
        first_seen_at: null,
        message_count: 0,
      },
      outreach: {
        state: null,
        last_contacted_at: null,
        source: null,
        notes: null,
        do_not_repeat: false,
        suppressed_email: false,
        suppressed_domain: false,
      },
      sent_history: { sent_count: 0, latest_sent_at: null, latest_subject: null },
      warnings: [],
    });

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => {
      expect(fetchContactProfile).toHaveBeenCalledTimes(2);
    });
  });

  it("shows postgres mirror truth note when mirror backend", async () => {
    vi.mocked(fetchContactProfile).mockResolvedValue({
      meta: { data_source: "postgres_mirror", read_only: true, reduced_mode: false, note: "" },
      contact: {
        email: "x@y.cl",
        normalized_email: "x@y.cl",
        name: "",
        domain: "",
        organization_name: "",
        organization_domain: "",
        last_seen_at: null,
        first_seen_at: null,
        message_count: 0,
      },
      outreach: {
        state: null,
        last_contacted_at: null,
        source: null,
        notes: null,
        do_not_repeat: false,
        suppressed_email: false,
        suppressed_domain: false,
      },
      sent_history: { sent_count: 0, latest_sent_at: null, latest_subject: null },
      warnings: [],
    });

    render(
      <ContactProfilePanel
        email="x@y.cl"
        open
        onClose={() => {}}
        backend="postgres"
        mirrorBackend
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Postgres mirror is not send\/outreach truth/)).toBeTruthy();
    });
  });

  it("shows suppression warning without write actions", async () => {
    vi.mocked(fetchContactProfile).mockResolvedValue({
      meta: { data_source: "sqlite", read_only: true, reduced_mode: false, note: "" },
      contact: {
        email: "dnr@x.cl",
        normalized_email: "dnr@x.cl",
        name: "",
        domain: "",
        organization_name: "",
        organization_domain: "",
        last_seen_at: null,
        first_seen_at: null,
        message_count: 0,
      },
      outreach: {
        state: "contacted",
        last_contacted_at: null,
        source: null,
        notes: null,
        do_not_repeat: true,
        suppressed_email: true,
        suppressed_domain: false,
      },
      sent_history: { sent_count: 0, latest_sent_at: null, latest_subject: null },
      warnings: [],
    });

    render(
      <ContactProfilePanel
        email="dnr@x.cl"
        open
        onClose={() => {}}
        backend="sqlite"
        mirrorBackend={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Do not repeat")).toBeTruthy();
    });
    expect(screen.queryByRole("button", { name: /send|draft|archive|mark contacted/i })).toBeNull();
  });

  it("explains DNR vs empty outreach state and sent history", async () => {
    vi.mocked(fetchContactProfile).mockResolvedValue({
      meta: { data_source: "sqlite", read_only: true, reduced_mode: false, note: "" },
      contact: {
        email: "kelly@ollital.com",
        normalized_email: "kelly@ollital.com",
        name: "",
        domain: "ollital.com",
        organization_name: "Ollital",
        organization_domain: "ollital.com",
        last_seen_at: null,
        first_seen_at: null,
        message_count: 5,
      },
      outreach: {
        state: null,
        last_contacted_at: null,
        source: null,
        notes: null,
        do_not_repeat: true,
        suppressed_email: false,
        suppressed_domain: false,
      },
      sent_history: {
        sent_count: 4,
        latest_sent_at: "2026-05-12T10:40:31-04:00",
        latest_subject: "Re: reactor",
      },
      warnings: [],
    });

    render(
      <ContactProfilePanel
        email="kelly@ollital.com"
        open
        onClose={() => {}}
        backend="sqlite"
        mirrorBackend={false}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/How to read outreach fields/i)).toBeTruthy();
    });
    expect(screen.getByText(/safety memory flag/i)).toBeTruthy();
    expect(screen.getByText(/Gmail Sent backfill/i)).toBeTruthy();
    expect(screen.getByText(/manual sidecar/i)).toBeTruthy();
    expect(screen.getByText(/— \(no sidecar row\)/)).toBeTruthy();
    expect(screen.getByText(/Sent history shows prior outbound/i)).toBeTruthy();
  });
});
