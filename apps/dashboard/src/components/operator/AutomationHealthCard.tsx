import { useEffect, useState } from "react";
import { fetchOperatorAutomationStatus } from "../../api/operatorClient";
import type { OperatorAutomationStatus } from "../../api/operatorTypes";
import {
  automationRecommendedActionLabel,
  automationVerdictLabel,
  automationVerdictTone,
  formatAutomationTimestamp,
  mailLoopStatusLabel,
  mirrorLoopStatusLabel,
} from "../../lib/automationHealthLabels";

export function AutomationHealthCard() {
  const [status, setStatus] = useState<OperatorAutomationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetchOperatorAutomationStatus()
      .then((data) => {
        if (!cancelled) {
          setStatus(data);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Error desconocido");
          setStatus(null);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return (
      <section
        className="rounded-xl border border-slate-200 bg-slate-50/60 px-5 py-4"
        data-testid="automation-health-card"
        aria-busy="true"
      >
        <div className="h-16 animate-pulse rounded-md bg-slate-200/70" />
      </section>
    );
  }

  if (error || !status) {
    return (
      <section
        className="rounded-xl border border-amber-200 bg-amber-50/80 px-5 py-4 text-sm text-amber-950"
        data-testid="automation-health-card"
        role="status"
      >
        <p className="font-medium">No se pudo leer estado de automatización</p>
        {error ? <p className="mt-1 break-words text-xs">{error}</p> : null}
      </section>
    );
  }

  const tone = automationVerdictTone(status.verdict);
  const mirrorSynced = mirrorLoopStatusLabel(status);
  const showLockOrPause =
    status.mail_auto_refresh.lock_live ||
    status.dashboard_auto_mirror.lock_live ||
    status.mail_auto_refresh.paused ||
    status.dashboard_auto_mirror.paused;

  return (
    <section
      className={`rounded-xl border px-5 py-5 shadow-sm ${tone.banner}`}
      data-testid="automation-health-card"
      aria-labelledby="automation-health-heading"
    >
      <h2 id="automation-health-heading" className="text-lg font-semibold text-brand-900">
        Automatización operador
      </h2>
      <p className="mt-1 text-xs text-[var(--color-muted)]">
        Solo lectura: Gmail → SQLite y SQLite → espejo dashboard.
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <span
          className={`rounded-md px-3 py-1 text-sm font-bold uppercase tracking-wide ${tone.badge}`}
        >
          {automationVerdictLabel(status.verdict)}
        </span>
        <span className="text-sm text-[var(--color-muted)]">
          {automationRecommendedActionLabel(status.recommended_action)}
        </span>
      </div>
      <ul className="mt-4 grid gap-2 text-sm sm:grid-cols-2">
        <li>
          <span className="text-[var(--color-muted)]">Gmail → SQLite:</span>{" "}
          <span className="font-medium">{mailLoopStatusLabel(status)}</span>
        </li>
        <li>
          <span className="text-[var(--color-muted)]">SQLite → Dashboard:</span>{" "}
          <span className="font-medium">
            {mirrorSynced === true
              ? "sincronizado"
              : mirrorSynced === false
                ? "atrás"
                : "desconocido"}
          </span>
        </li>
        <li>
          <span className="text-[var(--color-muted)]">Último refresh Gmail:</span>{" "}
          <span className="font-medium">
            {formatAutomationTimestamp(status.mail_auto_refresh.last_successful_refresh_at)}
          </span>
        </li>
        <li>
          <span className="text-[var(--color-muted)]">Último espejo:</span>{" "}
          <span className="font-medium">
            {formatAutomationTimestamp(status.dashboard_auto_mirror.last_successful_mirror_at)}
          </span>
        </li>
        <li>
          <span className="text-[var(--color-muted)]">INBOX / Sent:</span>{" "}
          <span className="font-medium">
            {status.mail_auto_refresh.last_seen_inbox_total ?? "—"} /{" "}
            {status.mail_auto_refresh.last_seen_sent_total ?? "—"}
          </span>
        </li>
        <li>
          <span className="text-[var(--color-muted)]">Daily-core:</span>{" "}
          <span className="font-medium">
            {status.daily_core.generated_at_utc ?? "—"}
            {status.daily_core.age_seconds != null
              ? ` (${status.daily_core.age_seconds}s)`
              : ""}
          </span>
        </li>
        {status.dashboard_auto_mirror.cooldown_remaining_seconds > 0 ? (
          <li>
            <span className="text-[var(--color-muted)]">Cooldown espejo:</span>{" "}
            <span className="font-medium">
              {status.dashboard_auto_mirror.cooldown_remaining_seconds}s
            </span>
          </li>
        ) : null}
      </ul>
      {showLockOrPause ? (
        <p className="mt-3 text-xs text-amber-900" data-testid="automation-lock-pause-hint">
          {status.mail_auto_refresh.paused || status.dashboard_auto_mirror.paused
            ? "Pausa activa. "
            : ""}
          {status.mail_auto_refresh.lock_live ? "Refresh Gmail en curso. " : ""}
          {status.dashboard_auto_mirror.lock_live ? "Publicación espejo en curso." : ""}
        </p>
      ) : null}
    </section>
  );
}
