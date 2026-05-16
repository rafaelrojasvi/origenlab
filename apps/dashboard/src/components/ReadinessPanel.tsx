import type { OutboundReadiness } from "../api/types";
import { verdictLabel } from "../lib/format";
import { translateApiMessage, translateApiMessages } from "../lib/translateApi";

interface Props {
  readiness: OutboundReadiness;
}

function verdictClasses(verdict: string): string {
  switch (verdict) {
    case "ready":
      return "bg-emerald-100 text-emerald-800";
    case "ready_with_warnings":
      return "bg-amber-100 text-amber-900";
    case "not_ready":
      return "bg-red-100 text-red-800";
    default:
      return "bg-slate-100 text-slate-700";
  }
}

export function ReadinessPanel({ readiness }: Props) {
  const warnings = translateApiMessages(readiness.warnings);
  const errors = translateApiMessages(readiness.errors);

  return (
    <section
      aria-labelledby="readiness-heading"
      className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-5 shadow-sm"
    >
      <h2 id="readiness-heading" className="text-lg font-semibold text-brand-900">
        Estado y frescura de datos
      </h2>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <span
          className={`rounded-full px-3 py-1 text-sm font-medium ${verdictClasses(readiness.verdict)}`}
        >
          {verdictLabel(readiness.verdict)}
        </span>
        {readiness.eventually_consistent ? (
          <span className="text-xs text-amber-800">
            Espejo Postgres · puede diferir de SQLite/Streamlit hasta sincronizar
          </span>
        ) : null}
      </div>
      <p className="mt-4 rounded-lg border border-brand-100 bg-brand-50 px-3 py-2 text-sm text-slate-700">
        <strong>Autoridad de datos:</strong> SQLite y Gmail siguen siendo la fuente
        operativa. Este panel lee el espejo Postgres (solo lectura).
      </p>
      {readiness.disclaimer ? (
        <p className="mt-2 text-xs text-[var(--color-muted)]">
          {translateApiMessage(readiness.disclaimer)}
        </p>
      ) : null}
      {warnings.length > 0 ? (
        <div className="mt-4">
          <h3 className="text-sm font-medium text-slate-800">Advertencias</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {errors.length > 0 ? (
        <div className="mt-4">
          <h3 className="text-sm font-medium text-red-800">Errores</h3>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-red-700">
            {errors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
