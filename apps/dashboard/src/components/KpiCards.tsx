import type { DashboardSummary } from "../api/types";
import { formatCount } from "../lib/format";

interface Props {
  summary: DashboardSummary;
}

export function KpiCards({ summary }: Props) {
  const items = [
    { label: "Contactos operativos", value: summary.contact_count },
    { label: "Organizaciones operativas", value: summary.organization_count },
    { label: "Señales operativas", value: summary.opportunity_signal_count },
    { label: "Emails suprimidos", value: summary.email_suppression_count },
    { label: "Dominios suprimidos", value: summary.domain_suppression_count },
    { label: "Memoria outreach", value: summary.outreach_state_count },
  ];

  return (
    <section aria-labelledby="kpi-heading">
      <div className="mb-3 flex flex-wrap items-end justify-between gap-2">
        <h2 id="kpi-heading" className="text-lg font-semibold text-brand-900">
          Indicadores operativos
        </h2>
        <span className="rounded-full bg-brand-100 px-3 py-1 text-xs font-medium text-brand-700">
          Ámbito: canónico (Gmail operativo)
        </span>
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {items.map(({ label, value }) => (
          <article
            key={label}
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-4 shadow-sm"
          >
            <p className="text-sm text-[var(--color-muted)]">{label}</p>
            <p className="mt-2 text-3xl font-semibold tabular-nums text-slate-900">
              {formatCount(value)}
            </p>
          </article>
        ))}
      </div>
      {summary.scope_note ? (
        <p className="mt-3 text-xs text-[var(--color-muted)]">{summary.scope_note}</p>
      ) : null}
    </section>
  );
}
