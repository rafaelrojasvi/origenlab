import { useCallback, useEffect, useState } from "react";
import { fetchOperatorAutomationStatus } from "../../api/operatorClient";
import type { OperatorAutomationStatus } from "../../api/operatorTypes";
import {
  AUTOMATION_MISSING_STATE_HELP,
  automationRecommendedActionLabel,
  automationVerdictLabel,
  automationVerdictTone,
  formatAutomationBool,
  formatAutomationTimestamp,
  mailLoopStatusLabel,
  mirrorLoopStatusLabel,
  operatorAutomationStatePartiallyMissing,
} from "../../lib/automationHealthLabels";

export interface AutomationHealthCardProps {
  variant?: "summary" | "detailed";
  onRefresh?: () => void;
}

function DetailRow({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-[var(--color-muted)]">{label}</dt>
      <dd className="font-medium break-words">{value}</dd>
    </div>
  );
}

export function AutomationHealthCard({
  variant = "summary",
  onRefresh,
}: AutomationHealthCardProps) {
  const [status, setStatus] = useState<OperatorAutomationStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadStatus = useCallback(
    async (isRefresh: boolean) => {
      if (isRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError(null);
      try {
        const data = await fetchOperatorAutomationStatus();
        setStatus(data);
        if (isRefresh) {
          onRefresh?.();
        }
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : "Error desconocido");
        if (!isRefresh) {
          setStatus(null);
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [onRefresh],
  );

  useEffect(() => {
    void loadStatus(false);
  }, [loadStatus]);

  const refreshButton = (
    <button
      type="button"
      className="rounded-md border border-[var(--color-border)] bg-white px-3 py-1.5 text-xs font-medium text-brand-900 shadow-sm hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-60"
      onClick={() => void loadStatus(true)}
      disabled={loading || refreshing}
      data-testid="automation-refresh-button"
    >
      {refreshing ? "Actualizando…" : "Actualizar estado"}
    </button>
  );

  if (loading && !status) {
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

  if ((error && !status) || !status) {
    return (
      <section
        className="rounded-xl border border-amber-200 bg-amber-50/80 px-5 py-4 text-sm text-amber-950"
        data-testid="automation-health-card"
        role="status"
      >
        <div className="flex flex-wrap items-start justify-between gap-3">
          <p className="font-medium">No se pudo leer estado de automatización</p>
          {refreshButton}
        </div>
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
  const missingState = operatorAutomationStatePartiallyMissing(status);
  const cronNote = status.cron.note?.trim();

  return (
    <section
      className={`rounded-xl border px-5 py-5 shadow-sm ${tone.banner}`}
      data-testid="automation-health-card"
      aria-labelledby="automation-health-heading"
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          {variant === "summary" ? (
            <>
              <h2 id="automation-health-heading" className="text-lg font-semibold text-brand-900">
                Automatización operador
              </h2>
              <p className="mt-1 text-xs text-[var(--color-muted)]">
                Solo lectura: Gmail → SQLite y SQLite → espejo dashboard.
              </p>
            </>
          ) : (
            <h3 id="automation-health-heading" className="text-base font-semibold text-brand-900">
              Estado de automatización
            </h3>
          )}
        </div>
        {refreshButton}
      </div>

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

      {missingState ? (
        <p
          className="mt-3 rounded-md border border-amber-200 bg-amber-50/90 px-3 py-2 text-xs text-amber-950"
          data-testid="automation-missing-state-help"
        >
          {AUTOMATION_MISSING_STATE_HELP}
        </p>
      ) : null}

      {variant === "summary" ? (
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
      ) : (
        <div className="mt-4 space-y-4 text-sm">
          <dl className="grid gap-2 sm:grid-cols-2">
            <DetailRow label="Generado (UTC)" value={status.generated_at_utc || "—"} />
            <DetailRow label="Veredicto" value={automationVerdictLabel(status.verdict)} />
            <DetailRow
              label="Acción recomendada"
              value={automationRecommendedActionLabel(status.recommended_action)}
            />
          </dl>

          <div className="rounded-lg border border-[var(--color-border)] bg-white/60 px-3 py-3">
            <h4 className="font-semibold text-brand-900">Daily-core</h4>
            <dl className="mt-2 grid gap-2 sm:grid-cols-2">
              <DetailRow
                label="Manifiesto presente"
                value={formatAutomationBool(status.daily_core.exists)}
              />
              <DetailRow label="Estado" value={status.daily_core.status ?? "—"} />
              <DetailRow
                label="Generado (UTC)"
                value={formatAutomationTimestamp(status.daily_core.generated_at_utc)}
              />
              <DetailRow
                label="Returncode"
                value={
                  status.daily_core.returncode != null ? String(status.daily_core.returncode) : "—"
                }
              />
            </dl>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-white/60 px-3 py-3">
            <h4 className="font-semibold text-brand-900">Mail auto-refresh</h4>
            <dl className="mt-2 grid gap-2 sm:grid-cols-2">
              <DetailRow
                label="Estado presente"
                value={formatAutomationBool(status.mail_auto_refresh.state_exists)}
              />
              <DetailRow
                label="Dirty / pending"
                value={`${formatAutomationBool(status.mail_auto_refresh.dirty)} / ${formatAutomationBool(status.mail_auto_refresh.pending)}`}
              />
              <DetailRow
                label="Último resultado"
                value={status.mail_auto_refresh.last_result ?? "—"}
              />
              <DetailRow
                label="Último refresh exitoso"
                value={formatAutomationTimestamp(
                  status.mail_auto_refresh.last_successful_refresh_at,
                )}
              />
              <DetailRow
                label="INBOX / Sent vistos"
                value={`${status.mail_auto_refresh.last_seen_inbox_total ?? "—"} / ${status.mail_auto_refresh.last_seen_sent_total ?? "—"}`}
              />
            </dl>
          </div>

          <div className="rounded-lg border border-[var(--color-border)] bg-white/60 px-3 py-3">
            <h4 className="font-semibold text-brand-900">Dashboard auto-mirror</h4>
            <dl className="mt-2 grid gap-2 sm:grid-cols-2">
              <DetailRow
                label="Estado presente"
                value={formatAutomationBool(status.dashboard_auto_mirror.state_exists)}
              />
              <DetailRow
                label="Último resultado"
                value={status.dashboard_auto_mirror.last_result ?? "—"}
              />
              <DetailRow
                label="Último espejo exitoso"
                value={formatAutomationTimestamp(
                  status.dashboard_auto_mirror.last_successful_mirror_at,
                )}
              />
              <DetailRow
                label="Espejo al día con daily-core"
                value={formatAutomationBool(status.dashboard_auto_mirror.mirror_matches_daily_core)}
              />
              <DetailRow
                label="Cooldown restante"
                value={`${status.dashboard_auto_mirror.cooldown_remaining_seconds}s`}
              />
            </dl>
          </div>

          {cronNote ? (
            <p className="text-xs text-[var(--color-muted)]">
              <span className="font-medium text-brand-900">Cron:</span> {cronNote}
            </p>
          ) : null}
        </div>
      )}

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
