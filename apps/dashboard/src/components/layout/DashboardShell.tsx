import type { ReactNode } from "react";
import { getOperatorApiBaseUrl } from "../../api/operatorClient";
import { useDashboardData } from "../../context/DashboardDataContext";
import { dashboardSectionLabel, type DashboardSection } from "../../lib/dashboardNav";
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
  const verdict = data?.operator.verdict;

  return (
    <div className="flex min-h-screen bg-[var(--color-surface)]">
      <DashboardSidebar active={section} onNavigate={onNavigate} />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="border-b border-[var(--color-border)] bg-[var(--color-card)] shadow-sm">
          <div className="flex flex-wrap items-center justify-between gap-4 px-4 py-4 sm:px-6">
            <div className="flex min-w-0 flex-1 items-center gap-4">
              <OrigenLabAnimatedLogo />
              <div className="hidden h-8 w-px bg-[var(--color-border)] sm:block" aria-hidden />
              <div className="min-w-0">
                <h1 className="text-xl font-semibold text-brand-950 sm:text-2xl">{pageTitle}</h1>
                <p className="text-sm text-[var(--color-muted)]">Panel operador · solo lectura</p>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {verdict ? (
                <span className="inline-flex items-center rounded-full bg-brand-50 px-3 py-1 text-xs font-semibold text-brand-900 ring-1 ring-brand-600/30">
                  Estado: {verdictTone(verdict).label}
                </span>
              ) : null}
              {data ? (
                <span
                  className={`inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold ring-1 ring-inset ${backendChipClass(data.health.backend)}`}
                >
                  {backendLabel(data.health.backend)}
                </span>
              ) : null}
              <button
                type="button"
                onClick={loadAll}
                disabled={refreshing}
                className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-brand-700 disabled:opacity-50"
              >
                {refreshing ? "Actualizando…" : "Actualizar"}
              </button>
            </div>
          </div>
          <div className="border-t border-[var(--color-border)] bg-brand-50/50 px-4 py-2 sm:px-6">
            <p className="text-xs text-[var(--color-muted)]">
              API:{" "}
              <code className="rounded bg-white/80 px-1 text-brand-900">
                {getOperatorApiBaseUrl() || "(proxy Vite)"}
              </code>
              <span className="mx-2">·</span>
              No envía correos · no modifica contactos ni envíos
            </p>
          </div>
        </header>

        <main className="flex-1 space-y-6 px-4 py-6 sm:px-8">
          <ReadOnlyBanner mirrorBackend={Boolean(mirrorBackend)} />
          {devConfigWarning ? <DevLegacyPortWarning message={devConfigWarning} /> : null}
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
