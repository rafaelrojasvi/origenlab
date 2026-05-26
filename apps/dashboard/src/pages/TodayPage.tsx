import { useCallback, useEffect, useMemo, useState } from "react";
import type {
  EquipmentOpportunitiesUiResponse,
  WarmCasesResponse,
} from "../api/commercialTypes";
import {
  OperatorApiError,
  fetchEquipmentOpportunities,
  fetchTodayPanel,
  DASHBOARD_WARM_CASES_QUERY,
  fetchWarmCases,
  getOperatorApiBaseUrl,
} from "../api/operatorClient";
import type { TodayPanelData } from "../api/operatorTypes";
import type { CommercialDealsListUi } from "../api/commercialDealsTypes";
import { fetchCommercialDealsMirror } from "../api/mirrorCommercialClient";
import { CommercialDealsTable } from "../components/commercial/CommercialDealsTable";
import { ContactProfilePanel } from "../components/commercial/ContactProfilePanel";
import { EquipmentOpportunitiesTable } from "../components/commercial/EquipmentOpportunitiesTable";
import { WarmCasesTable } from "../components/commercial/WarmCasesTable";
import { DevLegacyPortWarning } from "../components/operator/DevLegacyPortWarning";
import { OperatorWarningsList } from "../components/operator/OperatorWarningsList";
import { ReadOnlyBanner } from "../components/operator/ReadOnlyBanner";
import {
  getLegacyDevPortWarning,
  logLegacyDevPortWarningIfNeeded,
} from "../lib/devApiConfig";
import {
  backendChipClass,
  backendLabel,
  verdictTone,
} from "../lib/verdictStyles";

const WARNINGS_PREVIEW = 5;

function formatLoadError(label: string, e: unknown): string {
  if (e instanceof OperatorApiError) {
    return `${label} (API ${e.status}): ${e.message}`;
  }
  if (e instanceof Error) {
    return `${label}: ${e.message}`;
  }
  return `${label}: unknown error`;
}

function MirrorReadinessNote({ readiness, mirrorBackend }: { readiness: string; mirrorBackend: boolean }) {
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
      <span className="block text-xs mt-1 text-sky-800">
        Label reflects Postgres mirror sync, not SQLite send approval.
      </span>
    </p>
  );
}

export function TodayPage() {
  const [data, setData] = useState<TodayPanelData | null>(null);
  const [panelLoading, setPanelLoading] = useState(true);
  const [panelError, setPanelError] = useState<string | null>(null);

  const [warm, setWarm] = useState<WarmCasesResponse | null>(null);
  const [warmLoading, setWarmLoading] = useState(true);
  const [warmError, setWarmError] = useState<string | null>(null);

  const [equipment, setEquipment] = useState<EquipmentOpportunitiesUiResponse | null>(null);
  const [equipmentLoading, setEquipmentLoading] = useState(true);
  const [equipmentError, setEquipmentError] = useState<string | null>(null);

  const [commercialDeals, setCommercialDeals] = useState<CommercialDealsListUi | null>(null);
  const [commercialDealsLoading, setCommercialDealsLoading] = useState(true);
  const [commercialDealsError, setCommercialDealsError] = useState<string | null>(null);

  const [contactEmail, setContactEmail] = useState<string | null>(null);

  const loadPanel = useCallback(async () => {
    setPanelLoading(true);
    setPanelError(null);
    try {
      setData(await fetchTodayPanel());
    } catch (e) {
      setPanelError(formatLoadError("Operator status", e));
      setData(null);
    } finally {
      setPanelLoading(false);
    }
  }, []);

  const loadWarm = useCallback(async () => {
    setWarmLoading(true);
    setWarmError(null);
    try {
      setWarm(await fetchWarmCases(DASHBOARD_WARM_CASES_QUERY));
    } catch (e) {
      setWarmError(formatLoadError("Warm cases", e));
      setWarm(null);
    } finally {
      setWarmLoading(false);
    }
  }, []);

  const loadEquipment = useCallback(async () => {
    setEquipmentLoading(true);
    setEquipmentError(null);
    try {
      setEquipment(await fetchEquipmentOpportunities());
    } catch (e) {
      setEquipmentError(formatLoadError("Equipment opportunities", e));
      setEquipment(null);
    } finally {
      setEquipmentLoading(false);
    }
  }, []);

  const loadCommercialDeals = useCallback(async () => {
    setCommercialDealsLoading(true);
    setCommercialDealsError(null);
    try {
      setCommercialDeals(await fetchCommercialDealsMirror());
    } catch (e) {
      setCommercialDealsError(formatLoadError("Commercial deals mirror", e));
      setCommercialDeals(null);
    } finally {
      setCommercialDealsLoading(false);
    }
  }, []);

  const loadAll = useCallback(() => {
    void Promise.all([loadPanel(), loadWarm(), loadEquipment(), loadCommercialDeals()]);
  }, [loadPanel, loadWarm, loadEquipment, loadCommercialDeals]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const devConfigWarning = useMemo(() => getLegacyDevPortWarning(), []);

  useEffect(() => {
    logLegacyDevPortWarningIfNeeded();
  }, [devConfigWarning]);

  const mirrorBackend = data?.health.backend === "postgres";
  const backend = data?.health.backend ?? "sqlite";
  const tone = data ? verdictTone(data.operator.verdict) : null;
  const warnings = data?.operator.warnings ?? [];
  const warningsMore = Math.max(0, warnings.length - WARNINGS_PREVIEW);
  const refreshing =
    panelLoading || warmLoading || equipmentLoading || commercialDealsLoading;

  return (
    <div className="min-h-screen">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-card)]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-start justify-between gap-4 px-4 py-6 sm:px-6">
          <div>
            <p className="text-sm font-medium uppercase tracking-wide text-brand-600">
              OrigenLab
            </p>
            <h1 className="mt-1 text-2xl font-semibold text-brand-900 sm:text-3xl">Today</h1>
            <p className="mt-2 text-sm text-[var(--color-muted)]">
              Operator status · warm cases · equipment · commercial deals mirror · read-only ·
              apps/api
            </p>
          </div>
          {data ? (
            <span
              className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset ${backendChipClass(data.health.backend)}`}
            >
              {backendLabel(data.health.backend)}
            </span>
          ) : null}
        </div>
      </header>

      <main className="mx-auto max-w-6xl space-y-8 px-4 py-8 sm:px-6">
        <ReadOnlyBanner mirrorBackend={Boolean(mirrorBackend)} />

        {devConfigWarning ? <DevLegacyPortWarning message={devConfigWarning} /> : null}

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={loadAll}
            disabled={refreshing}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
          <p className="text-xs text-[var(--color-muted)]">
            API: <code className="text-slate-700">{getOperatorApiBaseUrl() || "(Vite proxy)"}</code>
          </p>
        </div>

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

        <WarmCasesTable
          backend={backend}
          items={warm?.items ?? []}
          meta={warm?.meta ?? null}
          loading={warmLoading}
          error={warmError}
          onRetry={() => void loadWarm()}
          onContactSelect={setContactEmail}
        />

        <EquipmentOpportunitiesTable
          backend={backend}
          items={equipment?.items ?? []}
          meta={equipment?.meta ?? null}
          loading={equipmentLoading}
          error={equipmentError}
          onRetry={() => void loadEquipment()}
          onContactSelect={setContactEmail}
        />

        <CommercialDealsTable
          data={commercialDeals}
          loading={commercialDealsLoading}
          error={commercialDealsError}
          onRetry={() => void loadCommercialDeals()}
        />

        <footer className="border-t border-[var(--color-border)] pt-6 text-xs text-[var(--color-muted)]">
          Dashboard v1 · Today · GET /health · /operator/status · /cases/warm ·
          /opportunities/equipment · /mirror/commercial/deals · /contacts/{"{email}"}
        </footer>
      </main>

      <ContactProfilePanel
        email={contactEmail}
        open={contactEmail !== null}
        onClose={() => setContactEmail(null)}
        backend={backend}
        mirrorBackend={Boolean(mirrorBackend)}
      />
    </div>
  );
}
