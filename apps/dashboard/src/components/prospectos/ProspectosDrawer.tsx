import type { LeadProspectDetailResponseUi } from "../../api/leadIntelTypes";
import { leadClassificationLabel, leadStatusLabel, prospectSafetyBanner } from "../../lib/leadIntelFormat";

export function ProspectosDrawer({
  detail,
  loading,
  error,
  onClose,
}: {
  detail: LeadProspectDetailResponseUi | null;
  loading: boolean;
  error: string | null;
  onClose: () => void;
}) {
  const p = detail?.prospect;
  const banner = p ? prospectSafetyBanner(p.classification, p.is_blocked) : null;

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-black/30"
      role="dialog"
      aria-modal="true"
      aria-labelledby="prospect-drawer-title"
      onClick={onClose}
    >
      <div
        className="h-full w-full max-w-lg overflow-y-auto border-l border-[var(--color-border)] bg-white shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-[var(--color-border)] bg-white px-5 py-4">
          <h2 id="prospect-drawer-title" className="text-lg font-semibold text-brand-900">
            Ficha del prospecto
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-[var(--color-border)] px-3 py-1.5 text-sm hover:bg-slate-50"
          >
            Cerrar
          </button>
        </div>

        <div className="space-y-5 px-5 py-5">
          {loading ? <p className="text-sm text-[var(--color-muted)]">Cargando ficha…</p> : null}
          {error ? (
            <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900" role="alert">
              {error}
            </p>
          ) : null}

          {p ? (
            <>
              {banner ? (
                <p
                  className={`rounded-lg border px-3 py-2 text-sm ${
                    p.is_blocked
                      ? "border-red-200 bg-red-50 text-red-900"
                      : p.classification === "public_tender_review"
                        ? "border-amber-200 bg-amber-50 text-amber-950"
                        : "border-sky-200 bg-sky-50 text-sky-950"
                  }`}
                  data-testid="prospect-safety-banner"
                >
                  {banner}
                </p>
              ) : null}

              <section>
                <h3 className="text-sm font-semibold text-brand-900">Resumen</h3>
                <p className="mt-1 text-base font-medium">{p.organization_name}</p>
                <dl className="mt-2 grid gap-1 text-sm">
                  <div>
                    <dt className="text-[var(--color-muted)]">Sector</dt>
                    <dd>{p.sector ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-[var(--color-muted)]">Región</dt>
                    <dd>{p.region ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-[var(--color-muted)]">Tipo comprador</dt>
                    <dd>{p.buyer_type ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-[var(--color-muted)]">Score / confianza</dt>
                    <dd>
                      {p.final_score} · {p.confidence ?? "—"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-[var(--color-muted)]">Estado</dt>
                    <dd>{leadStatusLabel(p.status)}</dd>
                  </div>
                </dl>
              </section>

              <section>
                <h3 className="text-sm font-semibold text-brand-900">Por qué importa</h3>
                <p className="mt-1 text-sm">{p.likely_need ?? "—"}</p>
                {detail?.recommendation?.why_this_lead ? (
                  <p className="mt-2 text-sm text-[var(--color-muted)]">{detail.recommendation.why_this_lead}</p>
                ) : null}
              </section>

              <section>
                <h3 className="text-sm font-semibold text-brand-900">Ángulo recomendado</h3>
                <p className="mt-1 text-sm">{p.product_angle ?? "—"}</p>
                <p className="mt-2 text-sm">{p.spanish_message_angle ?? "—"}</p>
              </section>

              <section>
                <h3 className="text-sm font-semibold text-brand-900">Evidencia</h3>
                {p.evidence_url ? (
                  <a
                    href={p.evidence_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 block text-sm text-brand-700 underline"
                  >
                    {p.evidence_url}
                  </a>
                ) : (
                  <p className="mt-1 text-sm">—</p>
                )}
                <p className="mt-1 text-sm text-[var(--color-muted)]">{p.evidence_note ?? ""}</p>
              </section>

              <section>
                <h3 className="text-sm font-semibold text-brand-900">Estado de seguridad</h3>
                <p className="mt-1 text-sm">{leadClassificationLabel(p.classification)}</p>
                {p.risk_flags ? (
                  <p className="mt-1 text-sm text-amber-900">Riesgos: {p.risk_flags}</p>
                ) : null}
                {p.block_or_review_reason ? (
                  <p className="mt-1 text-sm">{p.block_or_review_reason}</p>
                ) : null}
              </section>

              <section>
                <h3 className="text-sm font-semibold text-brand-900">Próxima acción</h3>
                <p className="mt-1 text-sm">{p.recommended_next_action ?? "—"}</p>
              </section>

              {detail?.recommendation?.suggested_body_preview && !p.is_blocked ? (
                <section>
                  <h3 className="text-sm font-semibold text-brand-900">Mensaje sugerido (solo vista)</h3>
                  <p className="mt-1 text-xs text-[var(--color-muted)]">
                    {detail.recommendation.safety_note}
                  </p>
                  <pre className="mt-2 whitespace-pre-wrap rounded-lg border border-[var(--color-border)] bg-slate-50 p-3 text-xs">
                    {detail.recommendation.suggested_subject}
                    {"\n\n"}
                    {detail.recommendation.suggested_body_preview}
                  </pre>
                </section>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </div>
  );
}
