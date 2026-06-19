import type { OperatorAutomationStatus } from "../api/operatorTypes";

export type FreshnessTone = "fresh" | "warning" | "stale" | "unknown";

export type MirrorSourceLabel = "Espejo Postgres" | "Loop auto-mirror";

export type AutomationFreshnessSummary = {
  tone: FreshnessTone;
  title: string;
  detail: string;
  gmailAgeLabel: string;
  mirrorAgeLabel: string;
  mirrorSourceLabel: MirrorSourceLabel;
  snapshotAgeLabel: string;
  warning: string | null;
  loopWarning: string | null;
};

export const AUTOMATION_FRESHNESS_TONE_CLASS: Record<FreshnessTone, string> = {
  fresh: "border-emerald-200 bg-emerald-50/90 text-emerald-950",
  warning: "border-amber-200 bg-amber-50/90 text-amber-950",
  stale: "border-red-200 bg-red-50/90 text-red-950",
  unknown: "border-slate-200 bg-slate-50/90 text-slate-800",
};

const GMAIL_FRESH_MS = 10 * 60 * 1000;
const MIRROR_FRESH_MS = 20 * 60 * 1000;
const SNAPSHOT_FRESH_MS = 30 * 60 * 1000;
const MS_PER_MINUTE = 60 * 1000;

function parseTimestamp(value: string | null | undefined): number | null {
  const trimmed = value?.trim();
  if (!trimmed) {
    return null;
  }
  const parsed = Date.parse(trimmed);
  return Number.isFinite(parsed) ? parsed : null;
}

export function formatAutomationFreshnessAgeLabel(ageMs: number | null): string {
  if (ageMs == null || ageMs < 0) {
    return "sin dato";
  }
  const minutes = Math.floor(ageMs / MS_PER_MINUTE);
  if (minutes < 60) {
    return `hace ${minutes} min`;
  }
  const hours = Math.floor(minutes / 60);
  return `hace ${hours} h`;
}

function resolveSnapshotTimestamp(status: OperatorAutomationStatus): number | null {
  return (
    parseTimestamp(status.snapshot_updated_at) ?? parseTimestamp(status.generated_at_utc)
  );
}

function resolveMirrorTimestamp(status: OperatorAutomationStatus): {
  ts: number | null;
  source: MirrorSourceLabel;
} {
  const sync = status.dashboard_mirror_sync;
  if (sync?.status === "success") {
    const finishedAt = parseTimestamp(sync.finished_at);
    if (finishedAt != null) {
      return { ts: finishedAt, source: "Espejo Postgres" };
    }
  }
  return {
    ts: parseTimestamp(status.dashboard_auto_mirror.last_successful_mirror_at),
    source: "Loop auto-mirror",
  };
}

function buildLoopWarning(
  status: OperatorAutomationStatus,
  mirrorSource: MirrorSourceLabel,
  mirrorFresh: boolean,
): string | null {
  if (mirrorSource !== "Espejo Postgres" || !mirrorFresh) {
    return null;
  }
  const loop = status.dashboard_auto_mirror;
  const hints: string[] = [];
  if (loop.last_result === "mail_dirty") {
    hints.push("El loop auto-mirror está esperando cambios de correo");
  }
  if (loop.mirror_matches_daily_core === false) {
    hints.push("el loop auto-mirror no coincide con daily-core");
  }
  if (!hints.length) {
    return null;
  }
  return `${hints.join("; ")}; el espejo Postgres ya fue actualizado manualmente.`;
}

export function buildAutomationFreshnessSummary(
  status: OperatorAutomationStatus,
  options?: { now?: Date },
): AutomationFreshnessSummary {
  const nowMs = (options?.now ?? new Date()).getTime();

  const gmailTs = parseTimestamp(status.mail_auto_refresh.last_successful_refresh_at);
  const { ts: mirrorTs, source: mirrorSourceLabel } = resolveMirrorTimestamp(status);
  const snapshotTs = resolveSnapshotTimestamp(status);

  const gmailAgeMs = gmailTs != null ? nowMs - gmailTs : null;
  const mirrorAgeMs = mirrorTs != null ? nowMs - mirrorTs : null;
  const snapshotAgeMs = snapshotTs != null ? nowMs - snapshotTs : null;

  const gmailAgeLabel = formatAutomationFreshnessAgeLabel(gmailAgeMs);
  const mirrorAgeLabel = formatAutomationFreshnessAgeLabel(mirrorAgeMs);
  const snapshotAgeLabel = formatAutomationFreshnessAgeLabel(snapshotAgeMs);

  const base = {
    gmailAgeLabel,
    mirrorAgeLabel,
    mirrorSourceLabel,
    snapshotAgeLabel,
  };

  const coreMissing = gmailTs == null || mirrorTs == null || snapshotTs == null;
  if (coreMissing) {
    return {
      ...base,
      tone: "unknown",
      title: "Frescura desconocida",
      detail: "Faltan marcas de tiempo para confirmar si los datos están al día.",
      warning: "No se pudo confirmar frescura completa.",
      loopWarning: null,
    };
  }

  const gmailFresh = gmailAgeMs! <= GMAIL_FRESH_MS;
  const mirrorFresh = mirrorAgeMs! <= MIRROR_FRESH_MS;
  const snapshotFresh = snapshotAgeMs! <= SNAPSHOT_FRESH_MS;
  const loopWarning = buildLoopWarning(status, mirrorSourceLabel, mirrorFresh);

  if (status.snapshot_stale === true) {
    return {
      ...base,
      tone: "stale",
      title: "Datos desactualizados",
      detail: "El snapshot del API indica datos viejos para el dashboard.",
      warning: "Dashboard puede estar desactualizado.",
      loopWarning,
    };
  }

  if (!mirrorFresh) {
    const staleTitle =
      mirrorSourceLabel === "Espejo Postgres"
        ? "Espejo Postgres desactualizado"
        : "Loop auto-mirror desactualizado";
    const staleDetail =
      mirrorSourceLabel === "Espejo Postgres"
        ? "El último sync exitoso del espejo Postgres supera el umbral de frescura."
        : "El loop SQLite → Dashboard no se ha actualizado recientemente.";
    return {
      ...base,
      tone: "stale",
      title: staleTitle,
      detail: staleDetail,
      warning: null,
      loopWarning: null,
    };
  }

  if (!gmailFresh) {
    return {
      ...base,
      tone: "warning",
      title: "Gmail/SQLite con retraso",
      detail:
        mirrorSourceLabel === "Espejo Postgres"
          ? "Gmail → SQLite lleva más tiempo sin refresh exitoso, aunque el espejo Postgres sigue reciente."
          : "Gmail → SQLite lleva más tiempo sin refresh exitoso, aunque el loop auto-mirror sigue reciente.",
      warning: null,
      loopWarning,
    };
  }

  if (!snapshotFresh) {
    return {
      ...base,
      tone: "stale",
      title: "Snapshot API con retraso",
      detail: "El snapshot del API supera el umbral de frescura esperado.",
      warning: "Dashboard puede estar desactualizado.",
      loopWarning,
    };
  }

  return {
    ...base,
    tone: "fresh",
    title: "Datos frescos",
    detail:
      mirrorSourceLabel === "Espejo Postgres"
        ? "Gmail/SQLite, espejo Postgres y snapshot API están dentro de los umbrales esperados."
        : "Gmail/SQLite, loop auto-mirror y snapshot API están dentro de los umbrales esperados.",
    warning: null,
    loopWarning,
  };
}
