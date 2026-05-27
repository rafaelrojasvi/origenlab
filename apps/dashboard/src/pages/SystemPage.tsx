import { useDashboardData } from "../context/DashboardDataContext";

export function SystemPage() {
  const { data, warm, equipment, commercialDeals } = useDashboardData();

  return (
    <section className="space-y-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] px-5 py-5 shadow-sm">
      <h2 className="text-lg font-semibold text-brand-900">System</h2>
      <p className="text-sm text-[var(--color-muted)]">
        Read-only operator dashboard. No Gmail sends, outreach writes, or SQLite mutations from this
        UI.
      </p>
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-[var(--color-muted)]">API service</dt>
          <dd className="font-medium">{data?.health.service ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-[var(--color-muted)]">Backend</dt>
          <dd className="font-medium">{data?.health.backend ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-[var(--color-muted)]">Warm cases loaded</dt>
          <dd className="font-medium">{warm?.items.length ?? 0}</dd>
        </div>
        <div>
          <dt className="text-[var(--color-muted)]">Equipment rows loaded</dt>
          <dd className="font-medium">{equipment?.items.length ?? 0}</dd>
        </div>
        <div>
          <dt className="text-[var(--color-muted)]">Commercial deals mirror</dt>
          <dd className="font-medium">
            {commercialDeals?.table_available ? `${commercialDeals.total} rows` : "not synced"}
          </dd>
        </div>
      </dl>
      <footer className="border-t border-[var(--color-border)] pt-4 text-xs text-[var(--color-muted)]">
        GET /health · /operator/status · /cases/warm · /opportunities/equipment ·
        /mirror/commercial/deals · /contacts/{"{email}"}
      </footer>
    </section>
  );
}
