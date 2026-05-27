import type { ReactNode } from "react";
import { getOperatorApiBaseUrl } from "../../api/operatorClient";
import { useDashboardData } from "../../context/DashboardDataContext";
import { dashboardSectionLabel, type DashboardSection } from "../../lib/dashboardNav";
import { backendChipClass, backendLabel } from "../../lib/verdictStyles";
import { DevLegacyPortWarning } from "../operator/DevLegacyPortWarning";
import { ReadOnlyBanner } from "../operator/ReadOnlyBanner";
import { ContactProfilePanel } from "../commercial/ContactProfilePanel";
import { DashboardSidebar } from "./DashboardSidebar";

export function DashboardShell({
  section,
  onNavigate,
  children,
}: {
  section: DashboardSection;
  onNavigate: (section: DashboardSection) => void;
  children: ReactNode;
}) {
  const {
    data,
    mirrorBackend,
    backend,
    devConfigWarning,
    refreshing,
    loadAll,
    contactEmail,
    setContactEmail,
  } = useDashboardData();

  const pageTitle = dashboardSectionLabel(section);

  return (
    <div className="flex min-h-screen">
      <DashboardSidebar active={section} onNavigate={onNavigate} />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-[var(--color-border)] bg-[var(--color-card)]">
          <div className="flex flex-wrap items-start justify-between gap-4 px-4 py-5 sm:px-6">
            <div>
              <h1 className="text-2xl font-semibold text-brand-900 sm:text-3xl">{pageTitle}</h1>
              <p className="mt-1 text-sm text-[var(--color-muted)]">
                Operator dashboard · apps/api · read-only
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

        <main className="flex-1 space-y-6 px-4 py-6 sm:px-6">
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
              API:{" "}
              <code className="text-slate-700">{getOperatorApiBaseUrl() || "(Vite proxy)"}</code>
            </p>
          </div>

          {children}
        </main>
      </div>

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
