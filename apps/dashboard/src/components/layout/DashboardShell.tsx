import { useState, type ReactNode } from "react";
import { getOperatorApiBaseUrl } from "../../api/operatorClient";
import { useDashboardData } from "../../context/DashboardDataContext";
import {
  dashboardSectionGroupLabel,
  dashboardSectionLabel,
  type DashboardSection,
} from "../../lib/dashboardNav";
import { backendChipClass, backendLabel, verdictTone } from "../../lib/verdictStyles";
import { DevLegacyPortWarning } from "../operator/DevLegacyPortWarning";
import { ReadOnlyBanner } from "../operator/ReadOnlyBanner";
import { ContactProfilePanel } from "../commercial/ContactProfilePanel";
import { OrigenLabAnimatedLogo } from "../brand/OrigenLabAnimatedLogo";
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
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
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
  const groupLabel = dashboardSectionGroupLabel(section);
  const verdict = data?.operator.verdict;
  const apiBase = getOperatorApiBaseUrl() || "(proxy Vite)";

  return (
    <div className="flex min-h-screen bg-[var(--color-surface)]">
      <DashboardSidebar
        active={section}
        collapsed={sidebarCollapsed}
        onNavigate={onNavigate}
        onToggleCollapsed={() => setSidebarCollapsed((value) => !value)}
      />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-[var(--color-border)] bg-[var(--color-card)]/95 shadow-sm backdrop-blur-sm">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
            <div className="flex min-w-0 flex-1 items-center gap-3">
              <OrigenLabAnimatedLogo />
              <div className="hidden h-7 w-px bg-[var(--color-border)] sm:block" aria-hidden />
              <div className="min-w-0">
                {groupLabel ? (
                  <p className="text-[11px] font-medium uppercase tracking-wide text-[var(--color-muted)]">
                    {groupLabel}
                  </p>
                ) : null}
                <h1 className="truncate text-lg font-semibold text-brand-950 sm:text-xl">
                  {pageTitle}
                </h1>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <span
                className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-slate-700 ring-1 ring-slate-200"
                data-testid="read-only-chip"
              >
                Solo lectura
              </span>
              {verdict ? (
                <span
                  className="inline-flex items-center rounded-full bg-brand-50 px-2.5 py-1 text-xs font-semibold text-brand-900 ring-1 ring-brand-600/30"
                  data-testid="operator-verdict-chip"
                >
                  Estado: {verdictTone(verdict).label}
                </span>
              ) : null}
              {data ? (
                <span
                  className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${backendChipClass(data.health.backend)}`}
                >
                  {backendLabel(data.health.backend)}
                </span>
              ) : null}
              <button
                type="button"
                onClick={loadAll}
                disabled={refreshing}
                className="rounded-lg bg-brand-600 px-3.5 py-1.5 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700 disabled:opacity-50 motion-reduce:transition-none"
              >
                {refreshing ? "Actualizando…" : "Actualizar"}
              </button>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 border-t border-[var(--color-border)]/70 px-4 py-1.5 text-[11px] text-[var(--color-muted)] sm:px-6">
            <span>Centro de comando operador</span>
            <span aria-hidden>·</span>
            <span>No envía correos ni modifica datos</span>
            <span className="hidden sm:inline" aria-hidden>
              ·
            </span>
            <code
              className="hidden rounded bg-slate-50 px-1.5 py-0.5 text-[10px] text-brand-900 ring-1 ring-slate-200 sm:inline"
              title="Base URL del API"
            >
              API {apiBase}
            </code>
          </div>
        </header>

        <main className="flex-1 px-4 py-5 sm:px-6 lg:px-8">
          <div className="mx-auto w-full max-w-[1600px] space-y-5">
            <ReadOnlyBanner mirrorBackend={Boolean(mirrorBackend)} />
            {devConfigWarning ? <DevLegacyPortWarning message={devConfigWarning} /> : null}
            {children}
          </div>
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
