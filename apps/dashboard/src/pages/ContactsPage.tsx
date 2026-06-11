import { useCallback, useEffect, useMemo, useState } from "react";
import type { LeadProspectListItemUi } from "../api/leadIntelTypes";
import { fetchLeadProspectsMirror } from "../api/mirrorLeadIntelClient";
import { InstitutionDrawer } from "../components/contacts/InstitutionDrawer";
import { TechnicalDetailDisclosure } from "../components/operator/TechnicalDetailDisclosure";
import { TablePaginationBar } from "../components/commercial/TablePaginationBar";
import { useDashboardData } from "../context/DashboardDataContext";
import {
  buildCustomerInstitutionGroups,
  filterCustomerInstitutionGroups,
  institutionKpis,
  institutionStatusChips,
  type CustomerInstitutionGroup,
  type InstitutionViewPreset,
} from "../lib/customerInstitutionGroups";
import { formatMirrorLoadError } from "../lib/humanizeApiError";
import { useClientTablePagination } from "../lib/useClientTablePagination";

function KpiCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] px-4 py-3 shadow-sm">
      <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-brand-900">{value}</p>
    </div>
  );
}

function gmailHistoryCell(group: CustomerInstitutionGroup): string {
  if (!group.hasGmailHistory) return "Sin historial";
  const last = group.latestGmailLastContactedAt ?? "—";
  return `${group.totalGmailSent} env. / ${group.totalGmailReceived} rec. · ${last}`;
}

export function ContactsPage() {
  const { setContactEmail } = useDashboardData();
  const [searchInput, setSearchInput] = useState("");
  const [preset, setPreset] = useState<InstitutionViewPreset>("all");
  const [sector, setSector] = useState("");
  const [region, setRegion] = useState("");
  const [minScore, setMinScore] = useState("");

  const [items, setItems] = useState<LeadProspectListItemUi[]>([]);
  const [disclaimer, setDisclaimer] = useState("");
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [listErrorDetail, setListErrorDetail] = useState<string | null>(null);
  const [selectedGroup, setSelectedGroup] = useState<CustomerInstitutionGroup | null>(null);

  const loadList = useCallback(async () => {
    setListLoading(true);
    setListError(null);
    setListErrorDetail(null);
    try {
      const res = await fetchLeadProspectsMirror({ limit: 200, include_blocked: false });
      setItems(res.items);
      setDisclaimer(res.disclaimer);
    } catch (e) {
      const formatted = formatMirrorLoadError("No se pudieron cargar instituciones", e);
      setListError(formatted.message);
      setListErrorDetail(formatted.detail);
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const allGroups = useMemo(() => buildCustomerInstitutionGroups(items), [items]);

  const filteredGroups = useMemo(
    () =>
      filterCustomerInstitutionGroups(allGroups, {
        search: searchInput,
        preset,
        sector,
        region,
        minScore: minScore.trim() ? Number(minScore) : null,
      }),
    [allGroups, searchInput, preset, sector, region, minScore],
  );

  const kpis = useMemo(() => institutionKpis(allGroups), [allGroups]);

  const { pageSize, setPage, setPageSize, pagination } = useClientTablePagination(filteredGroups, [
    searchInput,
    preset,
    sector,
    region,
    minScore,
    filteredGroups.length,
  ]);

  const pagedGroups = pagination.slice;

  return (
    <div className="space-y-6" data-testid="contacts-page">
      <header>
        <h1 className="text-2xl font-semibold text-brand-900">Clientes / instituciones</h1>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          Agrupa prospectos compradores por institución, dominio e historial de contacto. Solo lectura; no
          envía correos.
        </p>
        {disclaimer ? <p className="mt-2 text-xs text-sky-900">{disclaimer}</p> : null}
      </header>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5" data-testid="institution-kpis">
        <KpiCard label="Instituciones" value={kpis.institutions} />
        <KpiCard label="Con historial Gmail" value={kpis.withGmailHistory} />
        <KpiCard label="Sin email / investigar" value={kpis.missingEmail} />
        <KpiCard label="Seguras para revisar" value={kpis.safeToReview} />
        <KpiCard label="Bloqueadas / revisar" value={kpis.blockedOrRisk} />
      </div>

      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-4 shadow-sm">
        <div className="flex flex-wrap gap-3">
          <input
            type="search"
            placeholder="Buscar institución, dominio o email"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            className="min-w-[200px] flex-1 rounded-md border border-[var(--color-border)] px-3 py-2 text-sm"
            data-testid="institution-search"
          />
          <select
            value={preset}
            onChange={(e) => setPreset(e.target.value as InstitutionViewPreset)}
            className="rounded-md border border-[var(--color-border)] px-3 py-2 text-sm"
            aria-label="Vista"
            data-testid="institution-preset-filter"
          >
            <option value="all">Todas</option>
            <option value="contact_review">Contactar / revisar</option>
            <option value="gmail_history">Con historial Gmail</option>
            <option value="missing_email">Falta email</option>
            <option value="blocked_risk">Bloqueadas / riesgo</option>
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
          <input
            placeholder="Score mínimo"
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
            className="w-28 rounded-md border border-[var(--color-border)] px-3 py-2 text-sm"
          />
          <button
            type="button"
            onClick={() => void loadList()}
            className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Actualizar datos
          </button>
        </div>
      </section>

      {listError ? (
        <div className="text-sm text-red-800" role="alert">
          <p className="font-medium">{listError}</p>
          {listErrorDetail ? <TechnicalDetailDisclosure detail={listErrorDetail} /> : null}
        </div>
      ) : null}

      <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-white shadow-sm">
        <table className="min-w-full text-left text-sm">
          <thead className="border-b border-[var(--color-border)] bg-slate-50 text-xs uppercase text-[var(--color-muted)]">
            <tr>
              <th className="px-4 py-3">Institución</th>
              <th className="px-4 py-3">Contactos</th>
              <th className="px-4 py-3">Historial Gmail</th>
              <th className="px-4 py-3">Score</th>
              <th className="px-4 py-3">Sector / región</th>
              <th className="px-4 py-3">Estado</th>
              <th className="px-4 py-3">Próxima acción</th>
            </tr>
          </thead>
          <tbody>
            {pagedGroups.map((group) => {
              const chips = institutionStatusChips(group);
              return (
                <tr
                  key={group.key}
                  className="cursor-pointer border-b border-[var(--color-border)] hover:bg-brand-50/40"
                  onClick={() => setSelectedGroup(group)}
                  data-testid="institution-row"
                >
                  <td className="px-4 py-3">
                    <p className="font-medium">{group.institutionName}</p>
                    {group.domain ? (
                      <p className="text-xs text-[var(--color-muted)]">{group.domain}</p>
                    ) : null}
                  </td>
                  <td className="px-4 py-3">
                    {group.contactsWithEmail} con email
                    {group.contactsMissingEmail > 0 ? (
                      <span className="block text-xs text-amber-900">
                        {group.contactsMissingEmail} sin email
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 max-w-[12rem] text-xs">{gmailHistoryCell(group)}</td>
                  <td className="px-4 py-3">{group.maxFinalScore}</td>
                  <td className="px-4 py-3 max-w-[10rem] truncate">
                    {[group.sectors[0], group.regions[0]].filter(Boolean).join(" · ") || "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-wrap gap-1">
                      {chips.map((chip) => (
                        <span
                          key={chip.code}
                          className={`inline-block rounded-full border px-2 py-0.5 text-xs font-semibold ${chip.className}`}
                        >
                          {chip.label}
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-3 max-w-[14rem] truncate">{group.recommendedNextAction}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {filteredGroups.length > 0 && !listLoading ? (
          <TablePaginationBar
            page={pagination.page}
            totalPages={pagination.totalPages}
            pageSize={pageSize}
            onPageChange={setPage}
            onPageSizeChange={setPageSize}
            disabled={listLoading}
          />
        ) : null}
        <div className="border-t border-[var(--color-border)] px-4 py-2 text-xs text-[var(--color-muted)]">
          {listLoading ? (
            <p>Cargando…</p>
          ) : (
            <p>
              {filteredGroups.length} institución{filteredGroups.length === 1 ? "" : "es"} ·{" "}
              {items.length} prospecto{items.length === 1 ? "" : "s"} cargados
            </p>
          )}
        </div>
      </div>

      {selectedGroup ? (
        <InstitutionDrawer
          group={selectedGroup}
          onClose={() => setSelectedGroup(null)}
          onSelectEmail={setContactEmail}
        />
      ) : null}
    </div>
  );
}
