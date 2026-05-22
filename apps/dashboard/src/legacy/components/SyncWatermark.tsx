import type { DashboardSyncMeta } from "../api/types";
import { isSyncMissing, isSyncStale, syncTimestampIso } from "../lib/syncFreshness";

interface Props {
  syncMeta: DashboardSyncMeta | null;
}

function formatSyncInstant(iso: string): string {
  return new Date(iso).toLocaleString("es-CL", {
    dateStyle: "medium",
    timeStyle: "short",
  });
}

export function SyncWatermark({ syncMeta }: Props) {
  const refreshNote =
    "Los nuevos correos no aparecen aquí hasta ejecutar ingest Gmail, rebuild del mart y sync del espejo Postgres.";

  if (!syncMeta) {
    return (
      <div className="space-y-1 text-xs text-[var(--color-muted)]">
        <p>Última sincronización del espejo Postgres: no disponible (error al consultar la API).</p>
        <p>{refreshNote}</p>
      </div>
    );
  }

  if (isSyncMissing(syncMeta)) {
    return (
      <div className="space-y-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
        <p className="font-medium">
          Última sincronización del espejo Postgres: sin datos o tabla ausente.
        </p>
        <p>{syncMeta.postgres_mirror_note}</p>
        <p>{refreshNote}</p>
      </div>
    );
  }

  const at = syncTimestampIso(syncMeta);
  const stale = isSyncStale(syncMeta);
  const label = at ? formatSyncInstant(at) : "—";
  const statusHint =
    syncMeta.status === "failed"
      ? " (última ejecución fallida)"
      : syncMeta.status === "dry_run"
        ? " (simulación)"
        : "";

  return (
    <div
      className={`space-y-1 rounded-lg border px-3 py-2 text-xs ${
        stale
          ? "border-amber-200 bg-amber-50 text-amber-900"
          : "border-[var(--color-border)] text-[var(--color-muted)]"
      }`}
    >
      <p>
        Última sincronización del espejo Postgres:{" "}
        <time dateTime={at ?? undefined}>
          {label}
          {statusHint}
        </time>
        {syncMeta.elapsed_seconds != null ? (
          <span className="ml-1">({syncMeta.elapsed_seconds}s)</span>
        ) : null}
      </p>
      {stale ? (
        <p className="font-medium">
          El espejo puede estar desactualizado (más de 48 h). Revise el flujo de refresh operador.
        </p>
      ) : null}
      <p>{refreshNote}</p>
    </div>
  );
}
