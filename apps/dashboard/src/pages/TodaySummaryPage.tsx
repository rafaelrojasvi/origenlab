import { useMemo } from "react";
import { useDashboardData } from "../context/DashboardDataContext";
import { dashboardSectionToHash } from "../lib/dashboardHashRoute";
import type { DashboardSection } from "../lib/dashboardNav";
import { isEquipmentFeedUnavailable } from "../lib/equipmentFeedStatus";
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
        Preparación de salida: <span className="font-medium text-slate-800">{readiness}</span>
      </p>
    );
  }
  return (
    <p className="text-sm text-[var(--color-muted)]">
      Frescura del espejo: <span className="font-medium text-slate-800">{readiness}</span>
      <span className="mt-1 block text-xs text-sky-800">
        Refleja la última sincronización al espejo Postgres, no la aprobación de envío en SQLite.
      </span>
    </p>
  );
}

function navigateToSection(section: DashboardSection) {
  window.location.hash = dashboardSectionToHash(section);
}

function SummaryCard({
  label,
  value,
  displayValue,
  hint,
  section,
}: {
  label: string;
  value: number;
  displayValue?: string;
  hint?: string;
  section: DashboardSection;
}) {
  const shown = displayValue ?? String(value);
  return (
    <button
      type="button"
      onClick={() => navigateToSection(section)}
      className="w-full rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] px-4 py-4 text-left shadow-sm transition-all hover:border-brand-600/60 hover:shadow-md focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-600"
      aria-label={`${label}: ${shown}. Abrir sección.`}
    >
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
        {label}
      </p>
      <p className="mt-2 text-3xl font-semibold text-brand-900">{shown}</p>
      {hint ? <p className="mt-1 text-xs text-[var(--color-muted)]">{hint}</p> : null}
      <p className="mt-2 text-xs font-medium text-brand-700">Ver sección →</p>
    </button>
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
    catalogProducts,
    mirrorBackend,
    loadPanel,
    setContactEmail,
  } = useDashboardData();

  const tone = data ? verdictTone(data.operator.verdict) : null;
  const warnings = data?.operator.warnings ?? [];
  const warningsMore = Math.max(0, warnings.length - WARNINGS_PREVIEW);

  const equipmentFeedUnavailable = isEquipmentFeedUnavailable(equipment?.meta ?? null);

  const counts = useMemo(
    () =>
      computeTodaySummaryCounts(
        warm?.items ?? [],
        equipment?.items.length ?? 0,
        commercialDeals?.items ?? [],
        equipmentFeedUnavailable,
      ),
    [warm?.items, equipment?.items.length, commercialDeals?.items, equipmentFeedUnavailable],
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
          <p className="font-medium">No se pudo cargar el estado del operador</p>
          <p className="mt-1 break-words">{panelError}</p>
          <button
            type="button"
            onClick={() => void loadPanel()}
            className="mt-3 rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-50"
          >
            Reintentar
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
              <span className="text-sm font-medium">Estado del operador</span>
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2">
              <p className="text-sm">
                <span className="text-[var(--color-muted)]">Modo del servicio:</span>{" "}
                <code className="text-xs">{data.health.mode}</code>
              </p>
              <p className="text-sm">
                <span className="text-[var(--color-muted)]">Salud:</span>{" "}
                {data.health.ok ? "ok" : "degradado"}
              </p>
              {data.operator.campaign_mode ? (
                <p className="text-sm">
                  <span className="text-[var(--color-muted)]">Campaña:</span>{" "}
                  <span className="font-medium">{data.operator.campaign_mode}</span>
                </p>
              ) : null}
              {data.operator.operator_focus ? (
                <p className="text-sm">
                  <span className="text-[var(--color-muted)]">Foco:</span>{" "}
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
              Sin alertas del estado del operador.
            </p>
          )}

          {data.health.backend === "sqlite" ? (
            <p className="text-sm text-[var(--color-muted)]" role="status">
              El servidor usa SQLite local (la ruta no se muestra en el panel).
            </p>
          ) : null}
        </>
      ) : null}

      {equipmentFeedUnavailable ? (
        <div
          className="rounded-xl border border-amber-200 bg-amber-50/90 px-4 py-4 text-sm text-amber-950"
          role="status"
          data-testid="today-equipment-feed-unavailable"
        >
          <p className="font-semibold">Fuente de licitaciones no disponible</p>
          <p className="mt-2">
            No significa que no existan oportunidades. Revisar generación de{" "}
            <code className="text-xs">equipment_first_operator_queue</code>.
          </p>
        </div>
      ) : null}

      <section aria-labelledby="today-summary-heading">
        <h2 id="today-summary-heading" className="text-lg font-semibold text-brand-900">
          Resumen de colas
        </h2>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          Conteos según los datos cargados: correos tibios, oportunidades de equipos y negocios
          comerciales.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <SummaryCard
            label="Oportunidades de clientes"
            value={counts.clientOpportunities}
            hint="Oportunidad o respuesta de cliente"
            section="inbox"
          />
          <SummaryCard
            label="Cotizaciones y seguimientos de proveedores"
            value={counts.supplierQuotesFollowups}
            hint="Cotización recibida o seguimiento"
            section="suppliers"
          />
          <SummaryCard
            label="Pagos y logística"
            value={counts.paymentsLogistics}
            hint="Administración de pago o transporte"
            section="payments-logistics"
          />
          <SummaryCard
            label="Evidencia de negocio"
            value={counts.dealEvidence}
            hint="Hilos ligados a un negocio en curso"
            section="deals"
          />
          <SummaryCard
            label="Bloqueos de margen"
            value={counts.dealBlockers}
            hint="Espejo de negocios comerciales"
            section="deals"
          />
          <SummaryCard
            label="Licitaciones / equipos"
            value={counts.tendersEquipment}
            displayValue={equipmentFeedUnavailable ? "N/D" : undefined}
            hint={
              equipmentFeedUnavailable
                ? "Fuente de licitaciones no disponible (modo reducido)"
                : "Cola de oportunidades de equipos"
            }
            section="tenders"
          />
          <SummaryCard
            label="Productos catalogados"
            value={catalogProducts?.total ?? 0}
            hint="Catálogo operador (espejo Postgres)"
            section="catalogo"
          />
        </div>
      </section>
    </div>
  );
}
