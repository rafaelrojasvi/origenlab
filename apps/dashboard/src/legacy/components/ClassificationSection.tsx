import type {
  ClassificationActions,
  ClassificationEmailRow,
  ClassificationRecent,
  ClassificationSummary,
} from "../api/types";
import { formatCount } from "../lib/format";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { DataTable } from "./DataTable";

const KPI_LABELS: Record<string, string> = {
  posibles_solicitudes: "Posibles solicitudes",
  cotizaciones_enviadas: "Cotizaciones enviadas",
  seguimientos: "Seguimientos",
  rebotes_malos_correos: "Rebotes / malos correos",
  proveedores: "Proveedores",
  sin_clasificar: "Sin clasificar",
};

interface Props {
  summary: ClassificationSummary | null;
  recent: ClassificationRecent | null;
  actions: ClassificationActions | null;
}

export function ClassificationSection({ summary, recent, actions }: Props) {
  if (!summary?.table_available) {
    return (
      <section className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <p className="font-medium">Clasificación comercial no disponible</p>
        <p className="mt-1">
          Ejecute migraciones Alembic (0009) y sincronice el espejo Postgres para cargar la tabla
          de clasificación canónica.
        </p>
      </section>
    );
  }

  if (summary.status === "no_rows") {
    return (
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-6 text-sm text-[var(--color-muted)]">
        Sin filas de clasificación en el espejo actual. Ejecute sync del dashboard tras ingest y
        rebuild del mart.
      </section>
    );
  }

  const kpiEntries = Object.entries(summary.kpi).filter(([k]) => k in KPI_LABELS);

  return (
    <div className="space-y-8">
      <section>
        <h2 className="text-lg font-semibold text-brand-900">Clasificación comercial</h2>
        <p className="mt-1 text-sm text-[var(--color-muted)]">{summary.disclaimer}</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {kpiEntries.map(([key, value]) => (
            <article
              key={key}
              className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-4 shadow-sm"
            >
              <p className="text-sm text-[var(--color-muted)]">{KPI_LABELS[key]}</p>
              <p className="mt-2 text-2xl font-semibold tabular-nums">
                {formatCount(Number(value))}
              </p>
            </article>
          ))}
        </div>
      </section>

      <section>
        <h3 className="mb-3 text-base font-semibold text-slate-800">Acciones sugeridas</h3>
        <p className="mb-3 text-xs text-[var(--color-muted)]">
          Agrupación heurística; no ejecuta envíos ni cambios en CRM.
        </p>
        <div className="grid gap-3 md:grid-cols-2">
          {(actions?.groups ?? []).map((g) => (
            <article
              key={g.recommended_action}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-card)] p-4"
            >
              <div className="flex items-start justify-between gap-2">
                <h4 className="font-medium text-slate-900">{g.action_label_es}</h4>
                <span className="rounded-full bg-brand-100 px-2 py-0.5 text-xs font-semibold text-brand-800">
                  {formatCount(g.count)}
                </span>
              </div>
              {g.sample_subjects.length > 0 ? (
                <ul className="mt-2 list-inside list-disc text-xs text-[var(--color-muted)]">
                  {g.sample_subjects.map((s) => (
                    <li key={s} className="truncate">
                      {s}
                    </li>
                  ))}
                </ul>
              ) : null}
            </article>
          ))}
        </div>
      </section>

      <DataTable<ClassificationEmailRow>
        title="Correos clasificados recientes"
        caption="Heurística sobre Gmail canónico · no es verdad CRM"
        rows={recent?.items ?? []}
        emptyMessage="Sin correos clasificados en el espejo."
        columns={[
          {
            key: "date",
            header: "Fecha",
            render: (r) => (r.date_iso ? r.date_iso.slice(0, 16) : "—"),
          },
          {
            key: "contact",
            header: "Contacto",
            render: (r) => r.contact_email ?? r.from_addr ?? "—",
          },
          { key: "subject", header: "Asunto", render: (r) => r.subject ?? "—" },
          { key: "label", header: "Etiqueta", render: (r) => r.etiqueta_ui },
          {
            key: "conf",
            header: "Confianza",
            render: (r) => <ConfidenceBadge confidence={r.confidence} />,
          },
          {
            key: "action",
            header: "Acción sugerida",
            render: (r) => r.recommended_action.replace(/_/g, " "),
          },
        ]}
      />
    </div>
  );
}
