import { useDashboardData } from "../context/DashboardDataContext";
import { backendLabel } from "../lib/verdictStyles";

export function SystemPage() {
  const { data, warm, equipment, commercialDeals, leadResearchSummary } = useDashboardData();

  return (
    <section className="space-y-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] px-5 py-5 shadow-sm">
      <h2 className="text-lg font-semibold text-brand-900">Sistema</h2>
      <p className="text-sm text-[var(--color-muted)]">
        Panel de solo lectura. No envía correos ni modifica contactos, envíos ni SQLite desde esta
        interfaz.
      </p>

      <div className="rounded-lg border border-sky-100 bg-sky-50/80 px-4 py-4 text-sm text-sky-950">
        <h3 className="font-semibold text-sky-900">Alcance del correo en el panel</h3>
        <ul className="mt-2 list-disc space-y-2 pl-5">
          <li>
            El archivo SQLite operativo conserva el historial completo del buzón (del orden de{" "}
            <strong>216&nbsp;000</strong> mensajes indexados).
          </li>
          <li>
            El subconjunto <strong>canónico de Gmail</strong> para{" "}
            <code className="text-xs">contacto@origenlab.cl</code> es mucho menor (aprox.{" "}
            <strong>1&nbsp;100</strong> mensajes útiles para operación diaria).
          </li>
          <li>
            La cola de casos tibios del dashboard usa casos recientes enriquecidos o filtrados desde
            ese subconjunto canónico — <strong>no</strong> todo el archivo histórico.
          </li>
        </ul>
      </div>

      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-[var(--color-muted)]">Servicio API</dt>
          <dd className="font-medium">{data?.health.service ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-[var(--color-muted)]">Fuente de datos</dt>
          <dd className="font-medium">
            {data?.health.backend ? backendLabel(data.health.backend) : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-[var(--color-muted)]">Casos tibios cargados</dt>
          <dd className="font-medium">{warm?.items.length ?? 0}</dd>
        </div>
        <div>
          <dt className="text-[var(--color-muted)]">Filas de equipos cargadas</dt>
          <dd className="font-medium">
            {equipment?.meta?.reduced_mode
              ? "N/D (fuente no disponible)"
              : (equipment?.items.length ?? 0)}
          </dd>
        </div>
        <div>
          <dt className="text-[var(--color-muted)]">Espejo de negocios</dt>
          <dd className="font-medium">
            {commercialDeals?.table_available
              ? `${commercialDeals.total} negocios`
              : "aún no sincronizado"}
          </dd>
        </div>
      </dl>
      <div className="rounded-lg border border-[var(--color-border)] bg-slate-50/80 px-4 py-4 text-sm">
        <h3 className="font-semibold text-brand-900">Lead intelligence</h3>
        <dl className="mt-2 grid gap-2 sm:grid-cols-2">
          <div>
            <dt className="text-[var(--color-muted)]">Fuente</dt>
            <dd>CSV DeepSearch / Phase 10B</dd>
          </div>
          <div>
            <dt className="text-[var(--color-muted)]">Modo</dt>
            <dd>Solo lectura · no envía correos</dd>
          </div>
          <div>
            <dt className="text-[var(--color-muted)]">En revisión</dt>
            <dd>{leadResearchSummary?.review_count ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-[var(--color-muted)]">Bloqueados</dt>
            <dd>{leadResearchSummary?.blocked_count ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-[var(--color-muted)]">Total espejo</dt>
            <dd>
              {leadResearchSummary?.table_available
                ? leadResearchSummary.total
                : "aún no sincronizado"}
            </dd>
          </div>
        </dl>
      </div>

      <footer className="border-t border-[var(--color-border)] pt-4 text-xs text-[var(--color-muted)]">
        Rutas de solo lectura: estado del operador, casos tibios, oportunidades de equipos,
        negocios comerciales y contactos.
      </footer>
    </section>
  );
}
