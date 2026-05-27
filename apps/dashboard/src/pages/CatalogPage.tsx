import { useCallback, useEffect, useMemo, useState } from "react";
import type { CatalogListQuery, CatalogProductDetailUi, CatalogProductListItemUi } from "../api/catalogTypes";
import {
  fetchCatalogProductDetailMirror,
  fetchCatalogProductsMirror,
} from "../api/mirrorCatalogClient";
import { CatalogProductDrawer } from "../components/catalog/CatalogProductDrawer";
import { OperatorApiError } from "../api/operatorClient";
import {
  CATALOG_CATEGORY_FILTER_OPTIONS,
  buildListLinksSummary,
  buildListOfferSummary,
  catalogConfidenceLabel,
  catalogEquipmentClassLabel,
  primaryCategoryLabel,
} from "../lib/catalogFormat";

const ALL_BRANDS = ["CRTOP", "Hielscher", "IKA", "Ollital", "Ortoalresa", "SERVA"] as const;

function formatLoadError(label: string, e: unknown): string {
  if (e instanceof OperatorApiError) {
    return `${label} (API ${e.status}): ${e.message}`;
  }
  if (e instanceof Error) {
    return `${label}: ${e.message}`;
  }
  return `${label}: error desconocido`;
}

function FilterChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
        active
          ? "border-brand-600 bg-brand-600 text-white"
          : "border-[var(--color-border)] bg-white text-slate-700 hover:border-brand-400"
      }`}
    >
      {label}
    </button>
  );
}

function ActiveFilterChip({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <button
      type="button"
      onClick={onClear}
      className="inline-flex items-center gap-1 rounded-full border border-brand-200 bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-900 hover:bg-brand-100"
    >
      {label}
      <span aria-hidden>×</span>
    </button>
  );
}

export function CatalogPage() {
  const [searchInput, setSearchInput] = useState("");
  const [brandFilter, setBrandFilter] = useState("");
  const [equipmentClassFilter, setEquipmentClassFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [appliedQuery, setAppliedQuery] = useState<CatalogListQuery>({ limit: 100 });

  const [items, setItems] = useState<CatalogProductListItemUi[]>([]);
  const [total, setTotal] = useState(0);
  const [disclaimer, setDisclaimer] = useState("");
  const [listLoading, setListLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [detailsByKey, setDetailsByKey] = useState<Record<string, CatalogProductDetailUi>>({});

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<CatalogProductDetailUi | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const buildQueryFromFilters = useCallback((): CatalogListQuery => {
    const next: CatalogListQuery = { limit: 100 };
    if (searchInput.trim()) {
      next.q = searchInput.trim();
    }
    if (brandFilter.trim()) {
      next.brand = brandFilter.trim();
    }
    if (equipmentClassFilter.trim()) {
      next.equipment_class = equipmentClassFilter.trim();
    }
    if (categoryFilter.trim()) {
      next.category_key = categoryFilter.trim();
    }
    return next;
  }, [searchInput, brandFilter, equipmentClassFilter, categoryFilter]);

  const loadList = useCallback(async (query: CatalogListQuery) => {
    setListLoading(true);
    setListError(null);
    try {
      const body = await fetchCatalogProductsMirror(query);
      setItems(body.items);
      setTotal(body.total);
      setDisclaimer(body.disclaimer);

      const entries = await Promise.all(
        body.items.map(async (item) => {
          try {
            const response = await fetchCatalogProductDetailMirror(item.product_key);
            return response.product ? ([item.product_key, response.product] as const) : null;
          } catch {
            return null;
          }
        }),
      );
      const map: Record<string, CatalogProductDetailUi> = {};
      for (const entry of entries) {
        if (entry) {
          map[entry[0]] = entry[1];
        }
      }
      setDetailsByKey(map);
    } catch (e) {
      setListError(formatLoadError("Catálogo", e));
      setItems([]);
      setTotal(0);
      setDetailsByKey({});
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadList(appliedQuery);
  }, [appliedQuery, loadList]);

  const equipmentClassOptions = useMemo(() => {
    const values = new Set<string>();
    for (const item of items) {
      if (item.equipment_class?.trim()) {
        values.add(item.equipment_class.trim());
      }
    }
    return Array.from(values).sort((a, b) => a.localeCompare(b, "es"));
  }, [items]);

  const applyFilters = () => {
    setAppliedQuery(buildQueryFromFilters());
  };

  const clearAllFilters = () => {
    setSearchInput("");
    setBrandFilter("");
    setEquipmentClassFilter("");
    setCategoryFilter("");
    setAppliedQuery({ limit: 100 });
  };

  const toggleBrand = (brand: string) => {
    const nextBrand = brandFilter === brand ? "" : brand;
    setBrandFilter(nextBrand);
    const next: CatalogListQuery = { limit: 100 };
    if (searchInput.trim()) {
      next.q = searchInput.trim();
    }
    if (nextBrand) {
      next.brand = nextBrand;
    }
    if (equipmentClassFilter.trim()) {
      next.equipment_class = equipmentClassFilter.trim();
    }
    if (categoryFilter.trim()) {
      next.category_key = categoryFilter.trim();
    }
    setAppliedQuery(next);
  };

  const openProduct = (productKey: string) => {
    setSelectedKey(productKey);
    const cached = detailsByKey[productKey];
    if (cached) {
      setDetail(cached);
      setDetailError(null);
      setDetailLoading(false);
      return;
    }
    setDetail(null);
    setDetailError(null);
    setDetailLoading(true);
    void fetchCatalogProductDetailMirror(productKey)
      .then((body) => {
        if (!body.product) {
          setDetailError("Producto no encontrado en el espejo.");
          setDetail(null);
          return;
        }
        setDetail(body.product);
        setDetailsByKey((prev) => ({ ...prev, [productKey]: body.product! }));
      })
      .catch((e) => {
        setDetailError(formatLoadError("Detalle de producto", e));
        setDetail(null);
      })
      .finally(() => setDetailLoading(false));
  };

  const closeDrawer = () => {
    setSelectedKey(null);
    setDetail(null);
    setDetailError(null);
  };

  const activeProduct =
    selectedKey != null ? detailsByKey[selectedKey] ?? detail : null;

  const hasActiveFilters = Boolean(
    searchInput.trim() || brandFilter || equipmentClassFilter || categoryFilter,
  );

  const categoryLabel =
    CATALOG_CATEGORY_FILTER_OPTIONS.find((c) => c.key === categoryFilter)?.label ?? categoryFilter;

  const applyQueryWith = (overrides: {
    search?: string;
    brand?: string;
    equipmentClass?: string;
    category?: string;
  }) => {
    const next: CatalogListQuery = { limit: 100 };
    const q = overrides.search ?? searchInput;
    const brand = overrides.brand ?? brandFilter;
    const eq = overrides.equipmentClass ?? equipmentClassFilter;
    const cat = overrides.category ?? categoryFilter;
    if (q.trim()) {
      next.q = q.trim();
    }
    if (brand.trim()) {
      next.brand = brand.trim();
    }
    if (eq.trim()) {
      next.equipment_class = eq.trim();
    }
    if (cat.trim()) {
      next.category_key = cat.trim();
    }
    setAppliedQuery(next);
  };

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-[var(--color-muted)]">
          Productos, reactivos, equipos y repuestos cotizables por OrigenLab.
        </p>
        {disclaimer ? (
          <p className="mt-2 rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-950">
            {disclaimer}
          </p>
        ) : null}
      </div>

      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-4 shadow-sm space-y-4">
        <label className="block">
          <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Buscar
          </span>
          <input
            type="search"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                applyFilters();
              }
            }}
            placeholder="Buscar producto, marca o modelo"
            className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm"
          />
        </label>

        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
            Marca
          </p>
          <div className="mt-2 flex flex-wrap gap-2">
            {ALL_BRANDS.map((brand) => (
              <FilterChip
                key={brand}
                label={brand}
                active={brandFilter === brand}
                onClick={() => toggleBrand(brand)}
              />
            ))}
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
              Clase de equipo
            </span>
            <select
              value={equipmentClassFilter}
              onChange={(e) => setEquipmentClassFilter(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm"
            >
              <option value="">Todas</option>
              {equipmentClassOptions.map((value) => (
                <option key={value} value={value}>
                  {catalogEquipmentClassLabel(value)}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
              Categoría
            </span>
            <select
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm"
            >
              <option value="">Todas</option>
              {CATALOG_CATEGORY_FILTER_OPTIONS.map((opt) => (
                <option key={opt.key} value={opt.key}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={applyFilters}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
          >
            Aplicar filtros
          </button>
          <button
            type="button"
            onClick={clearAllFilters}
            className="rounded-lg border border-[var(--color-border)] bg-white px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
          >
            Limpiar filtros
          </button>
        </div>

        {hasActiveFilters ? (
          <div className="flex flex-wrap gap-2 border-t border-[var(--color-border)] pt-3">
            {searchInput.trim() ? (
              <ActiveFilterChip
                label={`Búsqueda: ${searchInput.trim()}`}
                onClear={() => {
                  setSearchInput("");
                  applyQueryWith({ search: "" });
                }}
              />
            ) : null}
            {brandFilter ? (
              <ActiveFilterChip
                label={`Marca: ${brandFilter}`}
                onClear={() => {
                  setBrandFilter("");
                  applyQueryWith({ brand: "" });
                }}
              />
            ) : null}
            {equipmentClassFilter ? (
              <ActiveFilterChip
                label={`Clase: ${catalogEquipmentClassLabel(equipmentClassFilter)}`}
                onClear={() => {
                  setEquipmentClassFilter("");
                  applyQueryWith({ equipmentClass: "" });
                }}
              />
            ) : null}
            {categoryFilter ? (
              <ActiveFilterChip
                label={`Categoría: ${categoryLabel}`}
                onClear={() => {
                  setCategoryFilter("");
                  applyQueryWith({ category: "" });
                }}
              />
            ) : null}
          </div>
        ) : null}
      </div>

      {listError ? (
        <div
          className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-900"
          role="alert"
        >
          <p className="font-medium">{listError}</p>
          <button
            type="button"
            onClick={() => void loadList(appliedQuery)}
            className="mt-2 rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-800"
          >
            Reintentar
          </button>
        </div>
      ) : null}

      {listLoading ? (
        <p className="text-sm text-[var(--color-muted)]" role="status">
          Cargando catálogo…
        </p>
      ) : null}

      {!listLoading && !listError && items.length === 0 ? (
        <p className="rounded-lg border border-[var(--color-border)] bg-slate-50 px-4 py-8 text-center text-sm text-[var(--color-muted)]">
          Aún no hay productos catalogados.
        </p>
      ) : null}

      {!listLoading && items.length > 0 ? (
        <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] shadow-sm">
          <table className="min-w-full text-left text-sm">
            <caption className="sr-only">Listado de productos del catálogo</caption>
            <thead className="border-b border-[var(--color-border)] bg-slate-50 text-xs uppercase tracking-wide text-[var(--color-muted)]">
              <tr>
                <th className="px-3 py-3 font-semibold">Producto</th>
                <th className="px-3 py-3 font-semibold">Marca</th>
                <th className="px-3 py-3 font-semibold">Categoría</th>
                <th className="px-3 py-3 font-semibold">Clase</th>
                <th className="px-3 py-3 font-semibold">Modelo</th>
                <th className="px-3 py-3 font-semibold">Último dato comercial</th>
                <th className="px-3 py-3 font-semibold">Vínculos</th>
                <th className="px-3 py-3 font-semibold">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {items.map((item) => {
                const rowDetail = detailsByKey[item.product_key] ?? null;
                return (
                  <tr
                    key={item.product_key}
                    tabIndex={0}
                    role="button"
                    onClick={() => openProduct(item.product_key)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        openProduct(item.product_key);
                      }
                    }}
                    className="cursor-pointer hover:bg-brand-50/40 focus-visible:bg-brand-50/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand-600"
                    aria-label={`Abrir ficha de ${item.display_name}`}
                  >
                    <td className="px-3 py-3 font-medium text-brand-800">{item.display_name}</td>
                    <td className="px-3 py-3">{item.brand ?? "—"}</td>
                    <td className="px-3 py-3">{primaryCategoryLabel(rowDetail)}</td>
                    <td className="px-3 py-3">
                      {catalogEquipmentClassLabel(item.equipment_class)}
                    </td>
                    <td className="px-3 py-3">{item.model_number ?? "—"}</td>
                    <td className="max-w-xs px-3 py-3 text-[var(--color-muted)]">
                      {buildListOfferSummary(rowDetail)}
                    </td>
                    <td className="px-3 py-3 text-[var(--color-muted)]">
                      {buildListLinksSummary(rowDetail)}
                    </td>
                    <td className="px-3 py-3">{catalogConfidenceLabel(item.confidence)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="border-t border-[var(--color-border)] px-3 py-2 text-xs text-[var(--color-muted)]">
            {total} producto{total === 1 ? "" : "s"} catalogado{total === 1 ? "" : "s"}
          </p>
        </div>
      ) : null}

      <CatalogProductDrawer
        product={activeProduct}
        loading={detailLoading && activeProduct == null}
        error={detailError}
        open={selectedKey !== null}
        onClose={closeDrawer}
      />
    </div>
  );
}
