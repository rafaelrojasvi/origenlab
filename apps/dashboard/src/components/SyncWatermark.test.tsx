import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SyncWatermark } from "./SyncWatermark";
import type { DashboardSyncMeta } from "../api/types";

const baseMeta: DashboardSyncMeta = {
  table_available: true,
  status: "success",
  latest_sync_id: 9,
  started_at: new Date().toISOString(),
  finished_at: new Date().toISOString(),
  elapsed_seconds: 2,
  postgres_mirror_note: "nota",
  canonical_contact_count: 1,
  canonical_organization_count: 1,
  canonical_opportunity_signal_count: 1,
  archive_contact_count: 1,
  archive_organization_count: 1,
  archive_opportunity_signal_count: 1,
  email_suppression_count: 0,
  domain_suppression_count: 0,
  outreach_state_count: 0,
  error_message: null,
};

describe("SyncWatermark", () => {
  it("renders sync timestamp and refresh note", () => {
    render(<SyncWatermark syncMeta={baseMeta} />);
    expect(screen.getByText(/Última sincronización del espejo Postgres/i)).toBeTruthy();
    expect(
      screen.getByText(/Los nuevos correos no aparecen aquí hasta ejecutar ingest Gmail/i),
    ).toBeTruthy();
  });
});
