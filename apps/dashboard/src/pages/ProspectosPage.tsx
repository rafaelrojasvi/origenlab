import { useCallback, useEffect, useMemo, useState } from "react";
import type { LeadProspectDetailResponseUi, LeadProspectListItemUi, LeadProspectsListQuery } from "../api/leadIntelTypes";
import {
  fetchLeadProspectDetailMirror,
  fetchLeadProspectsMirror,
  fetchLeadResearchSummaryMirror,
} from "../api/mirrorLeadIntelClient";
import { ProspectosDrawer } from "../components/prospectos/ProspectosDrawer";
import { OperatorApiError } from "../api/operatorClient";
import {
  prospectContactCell,
  prospectClassificationLabel,
  prospectTableBadge,
} from "../lib/prospectLabels";
import type { LeadResearchSummaryUi } from "../api/leadIntelTypes";

function formatLoadError(label: string, e: unknown): string {
  if (e instanceof OperatorApiError) {
    return `${label} (API ${e.status}): ${e.message}`;
  }
  if (e instanceof Error) {
    return `${label}: ${e.message}`;
  }
  return `${label}: error desconocido`;
}

function KpiCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] px-4 py-3 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-brand-900">{value}</p>
    </div>
  );
}

export function ProspectosPage() {
  const [summary, setSummary] = useState<LeadResearchSummaryUi | null>(null);
  const [searchInput, setSearchInput] = useState("");
  const [classification, setClassification] = useState("");
  const [sector, setSector] = useState("");
  const [region, setRegion] = useState("");
  const [campaignBucket, setCampaignBucket] = useState("");
  const [minScore, setMinScore] = useState("");
  const [showBlocked, setShowBlocked] = useState(false);

  const [items, setItems] = useState<LeadProspectListItemUi[]>([]);
  const [total, setTotal] = useState(0);
  const [disclaimer, setDisclaimer] = useState("");
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<LeadProspectDetailResponseUi | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const buildQuery = useCallback((): LeadProspectsListQuery => {
    const q: LeadProspectsListQuery = {
      limit: 100,
      include_blocked: showBlocked,
    };
    if (searchInput.trim()) q.q = searchInput.trim();
    if (classification) q.classification = classification;
    if (sector.trim()) q.sector = sector.trim();
    if (region.trim()) q.region = region.trim();
    if (campaignBucket) q.campaign_bucket = campaignBucket;
    if (minScore.trim()) q.min_score = Number(minScore);
    return q;
  }, [searchInput, classification, sector, region, campaignBucket, minScore, showBlocked]);

  const loadList = useCallback(async (query: LeadProspectsListQuery) => {
    setListLoading(true);
    setListError(null);
    try {
      const res = await fetchLeadProspectsMirror(query);
      setItems(res.items);
      setTotal(res.total);
      setDisclaimer(res.disclaimer);
    } catch (e) {
      setListError(formatLoadError("No se pudieron cargar prospectos", e));
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchLeadResearchSummaryMirror()
      .then(setSummary)
      .catch(() => setSummary(null));
  }, []);

  useEffect(() => {
    void loadList(buildQuery());
  }, [loadList, buildQuery]);

  useEffect(() => {
    if (!selectedKey) {
      setDetail(null);
      return;
    }
    setDetailLoading(true);
    setDetailError(null);
    void fetchLeadProspectDetailMirror(selectedKey)
      .then(setDetail)
      .catch((e) => setDetailError(formatLoadError("Ficha", e)))
      .finally(() => setDetailLoading(false));
  }, [selectedKey]);

  const priorHistoryWarning = useMemo(() => {
    if (!summary) return false;
    return summary.same_domain_review >= 3 || summary.blocked_count >= 5;
  }, [summary]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-brand-900">Prospectos</h1>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          Nuevas oportunidades de clientes · revisión humana · no envía correos
        </p>
        {disclaimer ? <p className="mt-2 text-xs text-sky-900">{disclaimer}</p> : null}
      </header>

      {summary?.table_available ? (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <KpiCard label="En revisión" value={summary.review_count} />
          <KpiCard label="Net-new seguros" value={summary.net_new_safe} />
          <KpiCard label="Licitaciones públicas" value={summary.public_tender_review} />
          <KpiCard label="Mismo dominio / revisar" value={summary.same_domain_review} />
          <KpiCard label="Falta email" value={summary.research_needed} />
          <KpiCard label="Bloqueados" value={summary.blocked_count} />
        </div>
      ) : null}

      {priorHistoryWarning ? (
        <p
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-950"
          data-testid="prospectos-prior-history-warning"
        >
          Hay prospectos con historial previo; revisar antes de contactar.
        </p>
      ) : null}

      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-4 shadow-sm">
        <div className="flex flex-wrap gap-3">
          <input
            type="search"
            placeholder="Buscar organización o contacto"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="min-w-[200px] flex-1 rounded-md border border-[var(--color-border)] px-3 py-2 text-sm"
          />
          <select
            value={classification}
            onChange={(e) => setClassification(e.target.value)}
            className="rounded-md border border-[var(--color-border)] px-3 py-2 text-sm"
            aria-label="Clasificación"
          >
            <option value="">Todas las clasificaciones</option>
            <option value="net_new_safe_review">Prospecto nuevo seguro</option>
            <option value="same_domain_contacted_review">Mismo dominio</option>
            <option value="public_tender_review">Licitación pública</option>
            <option value="research_only_contact_needed">Falta contacto</option>
          </select>
          <input
            placeholder="Sector"
            value={sector}
            onChange={(e) => setSector(e.target.value)}
            className="rounded-md border border-[var(--color-border)] px-3 py-2 text-sm"
          />
          <input
            placeholder="Región"
            value={region}
            onChange={(e) => setRegion(e.target.value)}
            className="rounded-md border border-[var(--color-border)] px-3 py-2 text-sm"
          />
          <select
            value={campaignBucket}
            onChange={(e) => setCampaignBucket(e.target.value)}
            className="rounded-md border border-[var(--color-border)] px-3 py-2 text-sm"
            aria-label="Bucket de campaña"
          >
            <option value="">Todos los buckets</option>
            <option value="private_lab">Laboratorio privado</option>
            <option value="public_tender">Licitación pública</option>
            <option value="university">Universidad</option>
            <option value="same_domain">Mismo dominio</option>
          </select>
          <input
            placeholder="Score mínimo"
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
            className="w-28 rounded-md border border-[var(--color-border)] px-3 py-2 text-sm"
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={showBlocked}
              onChange={(e) => setShowBlocked(e.target.checked)}
            />
            Mostrar bloqueados
          </label>
          <button
            type="button"
            onClick={() => void loadList(buildQuery())}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Aplicar filtros
          </button>
        </div>
      </section>

      {listError ? (
        <p className="text-sm text-red-800" role="alert">
          {listError}
        </p>
      ) : null}

      <p className="text-sm text-[var(--color-muted)]">
        {listLoading ? "Cargando…" : `${total} prospectos`}
      </p>

      <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-white shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-[var(--color-border)] bg-slate-50 text-xs uppercase text-[var(--color-muted)]">
            <tr>
              <th className="px-4 py-3">Organización</th>
              <th className="px-4 py-3">Contacto</th>
              <th className="px-4 py-3">Estado</th>
              <th className="px-4 py-3">Score</th>
              <th className="px-4 py-3">Sector</th>
              <th className="px-4 py-3">Ángulo</th>
              <th className="px-4 py-3">Próxima acción</th>
            </tr>
          </thead>
          <tbody>
            {items.map((row) => (
              <tr
                key={row.prospect_key}
                className="cursor-pointer border-b border-[var(--color-border)] hover:bg-brand-50/40"
                onClick={() => setSelectedKey(row.prospect_key)}
              >
                <td className="px-4 py-3 font-medium">{row.organization_name}</td>
                <td className="px-4 py-3 text-sm">{prospectContactCell(row)}</td>
                <td className="px-4 py-3">
                  {(() => {
                    const badge = prospectTableBadge(row);
                    return badge ? (
                      <span
                        className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-semibold ${badge.className}`}
                      >
                        {badge.label}
                      </span>
                    ) : (
                      <span className="text-sm">{prospectClassificationLabel(row.classification)}</span>
                    );
                  })()}
                </td>
                <td className="px-4 py-3">{row.final_score}</td>
                <td className="px-4 py-3 max-w-[10rem] truncate">{row.sector ?? "—"}</td>
                <td className="px-4 py-3 max-w-[12rem] truncate">{row.product_angle ?? "—"}</td>
                <td className="px-4 py-3 max-w-[14rem] truncate">{row.recommended_next_action ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedKey ? (
        <ProspectosDrawer
          detail={detail}
          loading={detailLoading}
          error={detailError}
          onClose={() => setSelectedKey(null)}
        />
      ) : null}
    </div>
  );
}
