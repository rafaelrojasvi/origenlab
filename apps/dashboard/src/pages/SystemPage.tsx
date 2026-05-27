import { useDashboardData } from "../context/DashboardDataContext";
import { backendLabel } from "../lib/verdictStyles";

export function SystemPage() {
  const { data, warm, equipment, commercialDeals } = useDashboardData();

  return (
    <section className="space-y-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] px-5 py-5 shadow-sm">
      <h2 className="text-lg font-semibold text-brand-900">Sistema</h2>
      <p className="text-sm text-[var(--color-muted)]">
        Panel de solo lectura. No envía correos ni modifica contactos, envíos ni SQLite desde esta
        interfaz.
      </p>
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
          <dd className="font-medium">{equipment?.items.length ?? 0}</dd>
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
      <footer className="border-t border-[var(--color-border)] pt-4 text-xs text-[var(--color-muted)]">
        Rutas de solo lectura: estado del operador, casos tibios, oportunidades de equipos,
        negocios comerciales y contactos.
      </footer>
    </section>
  );
}
