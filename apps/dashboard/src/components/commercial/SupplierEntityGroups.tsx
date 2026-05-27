import { useMemo, useState } from "react";
import type { WarmCaseItem } from "../../api/commercialTypes";
import type { ApiBackend } from "../../api/operatorTypes";
import {
  groupSupplierWarmCases,
  type SupplierEntityGroup,
} from "../../lib/supplierEntityGrouping";
import { WarmCasesTable } from "./WarmCasesTable";

function SupplierEntityCard({
  group,
  active,
  onSelect,
}: {
  group: SupplierEntityGroup;
  active: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      aria-label={`${group.label}, ${group.summaryLabel}`}
      onClick={onSelect}
      className={`w-full rounded-lg border px-3 py-3 text-left transition-all ${
        active
          ? "border-brand-600 bg-brand-50 shadow-sm ring-2 ring-brand-600/25"
          : "border-[var(--color-border)] bg-[var(--color-card)] hover:border-brand-500/60 hover:bg-brand-50/40"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm font-semibold text-brand-950">{group.label}</p>
        {active ? (
          <span className="shrink-0 rounded-full bg-brand-600 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
            Seleccionado
          </span>
        ) : (
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium ${
              group.roleBadge === "Cotización recibida"
                ? "bg-teal-100 text-teal-900"
                : group.roleBadge === "Seguimiento"
                  ? "bg-amber-100 text-amber-950"
                  : "bg-slate-100 text-slate-700"
            }`}
          >
            {group.roleBadge}
          </span>
        )}
      </div>
      <p className="mt-1.5 text-xs font-medium text-brand-800">{group.summaryLabel}</p>
      <p className="mt-1 text-[11px] text-[var(--color-muted)]">
        Último hilo · {group.latestActivityLabel ?? "sin fecha"}
      </p>
      <p className="mt-1 line-clamp-2 text-xs text-slate-700" title={group.latestSubject}>
        {group.latestSubject}
      </p>
    </button>
  );
}

export function SupplierEntityGroups({
  backend,
  allItems,
  meta,
  loading,
  error,
  onRetry,
  onContactSelect,
}: {
  backend: ApiBackend;
  allItems: WarmCaseItem[];
  meta: {
    data_source: "sqlite" | "postgres_mirror";
    reduced_mode: boolean;
    note: string;
    count: number;
  } | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  onContactSelect: (email: string) => void;
}) {
  const groups = useMemo(() => groupSupplierWarmCases(allItems), [allItems]);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);

  const selectedGroup: SupplierEntityGroup | null = useMemo(() => {
    if (!selectedGroupId) {
      return null;
    }
    return groups.find((g) => g.id === selectedGroupId) ?? null;
  }, [groups, selectedGroupId]);

  if (loading || error || allItems.length === 0) {
    return (
      <WarmCasesTable
        backend={backend}
        items={allItems}
        meta={meta}
        loading={loading}
        error={error}
        onRetry={onRetry}
        onContactSelect={onContactSelect}
        title="Proveedores"
        subtitle="Cotizaciones y seguimientos de proveedores."
        showViewPresets={false}
        initialFilters={{ preset: "todo", hideInternalContacts: false }}
      />
    );
  }

  return (
    <div className="space-y-6">
      <section aria-labelledby="supplier-groups-heading">
        <h2 id="supplier-groups-heading" className="text-lg font-semibold text-brand-950">
          Proveedores por entidad
        </h2>
        <p className="mt-1 text-sm text-[var(--color-muted)]">
          Selecciona un proveedor para revisar sus hilos.
        </p>
        <div
          className="mt-4 grid list-none gap-3 sm:grid-cols-2 lg:grid-cols-3"
          data-testid="supplier-entity-cards"
        >
          {groups.map((group) => {
            const active = selectedGroupId === group.id;
            return (
              <SupplierEntityCard
                key={group.id}
                group={group}
                active={active}
                onSelect={() => setSelectedGroupId(active ? null : group.id)}
              />
            );
          })}
        </div>
      </section>

      {selectedGroup ? (
        <WarmCasesTable
          backend={backend}
          items={selectedGroup.items}
          meta={meta}
          loading={false}
          error={null}
          onRetry={onRetry}
          onContactSelect={onContactSelect}
          title={`Hilos de ${selectedGroup.label}`}
          subtitle={`${selectedGroup.summaryLabel} · cola de solo lectura`}
          showViewPresets={false}
          initialFilters={{ preset: "todo", hideInternalContacts: false }}
        />
      ) : (
        <p className="text-sm text-[var(--color-muted)]" role="status">
          Selecciona un proveedor arriba para ver sus casos tibios.
        </p>
      )}
    </div>
  );
}
