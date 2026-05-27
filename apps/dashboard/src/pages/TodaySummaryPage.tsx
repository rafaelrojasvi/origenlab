import { useMemo } from "react";
import { useDashboardData } from "../context/DashboardDataContext";
import { computeTodaySummaryCounts } from "../lib/todaySummaryCounts";
import { verdictTone } from "../lib/verdictStyles";
import { OperatorWarningsList } from "../components/operator/OperatorWarningsList";

const WARNINGS_PREVIEW = 5;

function MirrorReadinessNote({
  readiness,
  mirrorBackend,
}: {
  readiness: string;
  mirrorBackend: boolean;
}) {
  if (!mirrorBackend) {
    return (
      <p className="text-sm text-[var(--color-muted)]">
        Outbound readiness: <span className="font-medium text-slate-800">{readiness}</span>
      </p>
    );
  }
  return (
    <p className="text-sm text-[var(--color-muted)]">
      Mirror freshness: <span className="font-medium text-slate-800">{readiness}</span>
      <span className="mt-1 block text-xs text-sky-800">
        Label reflects Postgres mirror sync, not SQLite send approval.
      </span>
    </p>
  );
}

function SummaryCard({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] px-4 py-4 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
        {label}
      </p>
      <p className="mt-2 text-3xl font-semibold text-brand-900">{value}</p>
      {hint ? <p className="mt-1 text-xs text-[var(--color-muted)]">{hint}</p> : null}
    </div>
  );
}

export function TodaySummaryPage() {
  const {
    data,
    panelLoading,
    panelError,
    warm,
    equipment,
    commercialDeals,
    mirrorBackend,
    loadPanel,
    setContactEmail,
  } = useDashboardData();

  const tone = data ? verdictTone(data.operator.verdict) : null;
  const warnings = data?.operator.warnings ?? [];
  const warningsMore = Math.max(0, warnings.length - WARNINGS_PREVIEW);

  const counts = useMemo(
    () =>
      computeTodaySummaryCounts(
        warm?.items ?? [],
        equipment?.items.length ?? 0,
        commercialDeals?.items ?? [],
      ),
    [warm?.items, equipment?.items.length, commercialDeals?.items],
  );

  return (
    <div className="space-y-6">
      {panelLoading && !data ? (
        <div className="space-y-3" role="status" aria-live="polite">
          <div className="h-24 animate-pulse rounded-lg bg-slate-200/80" />
          <div className="h-16 animate-pulse rounded-lg bg-slate-100" />
        </div>
      ) : null}

      {panelError ? (
        <div
          className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900"
          role="alert"
        >
          <p className="font-medium">Could not load operator status</p>
          <p className="mt-1 break-words">{panelError}</p>
          <button
            type="button"
            onClick={() => void loadPanel()}
            className="mt-3 rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-50"
          >
            Retry
          </button>
        </div>
      ) : null}

      {data && tone ? (
        <>
          <section
            className={`rounded-xl border px-5 py-5 shadow-sm ${tone.banner}`}
            aria-labelledby="verdict-heading"
          >
            <div className="flex flex-wrap items-center gap-3">
              <span
                id="verdict-heading"
                className={`rounded-md px-3 py-1 text-sm font-bold uppercase tracking-wide ${tone.badge}`}
              >
                {tone.label}
              </span>
              <span className="text-sm font-medium">Operator verdict</span>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <p className="text-sm">
                <span className="text-[var(--color-muted)]">Service mode:</span>{" "}
                <code className="text-xs">{data.health.mode}</code>
              </p>
              <p className="text-sm">
                <span className="text-[var(--color-muted)]">Health:</span>{" "}
                {data.health.ok ? "ok" : "degraded"}
              </p>
              {data.operator.campaign_mode ? (
                <p className="text-sm">
                  <span className="text-[var(--color-muted)]">Campaign:</span>{" "}
                  <span className="font-medium">{data.operator.campaign_mode}</span>
                </p>
              ) : null}
              {data.operator.operator_focus ? (
                <p className="text-sm">
                  <span className="text-[var(--color-muted)]">Focus:</span>{" "}
                  <span className="font-medium">{data.operator.operator_focus}</span>
                </p>
              ) : null}
            </div>
            <div className="mt-3">
              <MirrorReadinessNote
                readiness={data.operator.outbound_readiness}
                mirrorBackend={mirrorBackend}
              />
            </div>
          </section>

          {warnings.length > 0 ? (
            <OperatorWarningsList
              warnings={warnings.slice(0, WARNINGS_PREVIEW)}
              moreCount={warningsMore}
              onContactSelect={setContactEmail}
            />
          ) : (
            <p className="text-sm text-[var(--color-muted)]" role="status">
              No warnings from operator status.
            </p>
          )}

          {data.health.backend === "sqlite" ? (
            <p className="text-sm text-[var(--color-muted)]" role="status">
              SQLite runtime configured on API server (path not shown in dashboard).
            </p>
          ) : null}
        </>
      ) : null}

      <section aria-labelledby="today-summary-heading">
        <h2 id="today-summary-heading" className="text-lg font-semibold text-brand-900">
          Queue summary
        </h2>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          Counts from loaded warm cases, equipment opportunities, and commercial deals mirror.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <SummaryCard
            label="Client opportunities"
            value={counts.clientOpportunities}
            hint="client_opportunity · client_response"
          />
          <SummaryCard
            label="Supplier quotes / follow-ups"
            value={counts.supplierQuotesFollowups}
            hint="supplier_quote_received · supplier_followup"
          />
          <SummaryCard
            label="Payments & logistics"
            value={counts.paymentsLogistics}
            hint="payment_admin · logistics_admin"
          />
          <SummaryCard
            label="Deal evidence (warm)"
            value={counts.dealEvidence}
            hint="deal_evidence_candidate"
          />
          <SummaryCard
            label="Deal margin blockers"
            value={counts.dealBlockers}
            hint="Commercial deals mirror"
          />
          <SummaryCard
            label="Tenders / equipment"
            value={counts.tendersEquipment}
            hint="Equipment opportunities queue"
          />
        </div>
      </section>
    </div>
  );
}
