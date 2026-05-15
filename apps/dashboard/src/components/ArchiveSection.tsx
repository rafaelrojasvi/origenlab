import type { DashboardSummary } from "../api/types";
import { formatCount } from "../lib/format";

interface Props {
  archive: DashboardSummary;
}

export function ArchiveSection({ archive }: Props) {
  return (
    <details className="group rounded-xl border border-[var(--color-border)] bg-slate-50/80">
      <summary className="cursor-pointer list-none px-5 py-4 font-semibold text-slate-800 marker:content-none">
        <span className="flex items-center justify-between gap-2">
          <span>Archivo histórico / mart completo</span>
          <span className="text-xs font-normal text-[var(--color-muted)] group-open:hidden">
            Mostrar comparación
          </span>
          <span className="hidden text-xs font-normal text-[var(--color-muted)] group-open:inline">
            Ocultar
          </span>
        </span>
        <p className="mt-1 text-sm font-normal text-[var(--color-muted)]">
          Totales del mart reconstruido sobre el archivo completo (Labdelivery, PST, IMAP, etc.).
          Requiere <code className="rounded bg-white px-1">?scope=archive</code> en la API.
        </p>
      </summary>
      <div className="grid gap-4 border-t border-[var(--color-border)] px-5 py-4 sm:grid-cols-3">
        <div>
          <p className="text-sm text-[var(--color-muted)]">Contactos (archivo)</p>
          <p className="text-2xl font-semibold tabular-nums">{formatCount(archive.contact_count)}</p>
        </div>
        <div>
          <p className="text-sm text-[var(--color-muted)]">Organizaciones (archivo)</p>
          <p className="text-2xl font-semibold tabular-nums">
            {formatCount(archive.organization_count)}
          </p>
        </div>
        <div>
          <p className="text-sm text-[var(--color-muted)]">Señales (archivo)</p>
          <p className="text-2xl font-semibold tabular-nums">
            {formatCount(archive.opportunity_signal_count)}
          </p>
        </div>
      </div>
      {archive.scope_note ? (
        <p className="border-t border-[var(--color-border)] px-5 py-3 text-xs text-[var(--color-muted)]">
          {archive.scope_note}
        </p>
      ) : null}
    </details>
  );
}
