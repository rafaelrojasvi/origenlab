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
  catalogConfidenceLabel,
  catalogEquipmentClassLabel,
  listLinksHint,
  listOfferHint,
} from "../lib/catalogFormat";

function formatLoadError(label: string, e: unknown): string {
  if (e instanceof OperatorApiError) {
    return `${label} (API ${e.status}): ${e.message}`;
  }
  if (e instanceof Error) {
    return `${label}: ${e.message}`;
  }
  return `${label}: error desconocido`;
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

  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [detail, setDetail] = useState<CatalogProductDetailUi | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);

  const loadList = useCallback(async (query: CatalogListQuery) => {
    setListLoading(true);
    setListError(null);
    try {
      const body = await fetchCatalogProductsMirror(query);
      setItems(body.items);
      setTotal(body.total);
      setDisclaimer(body.disclaimer);
    } catch (e) {
      setListError(formatLoadError("Catálogo", e));
      setItems([]);
      setTotal(0);
    } finally {
      setListLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadList(appliedQuery);
  }, [appliedQuery, loadList]);

  const brandOptions = useMemo(() => {
    const brands = new Set<string>();
    for (const item of items) {
      if (item.brand?.trim()) {
        brands.add(item.brand.trim());
      }
    }
    return Array.from(brands).sort((a, b) => a.localeCompare(b, "es"));
  }, [items]);

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
    setAppliedQuery(next);
  };

  const openProduct = (productKey: string) => {
    setSelectedKey(productKey);
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

      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-card)] p-4 shadow-sm">
        <div className="grid gap-3 lg:grid-cols-4">
          <label className="block lg:col-span-2">
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
          <label className="block">
            <span className="text-xs font-semibold uppercase tracking-wide text-[var(--color-muted)]">
              Marca
            </span>
            <select
              value={brandFilter}
              onChange={(e) => setBrandFilter(e.target.value)}
              className="mt-1 w-full rounded-lg border border-[var(--color-border)] px-3 py-2 text-sm"
            >
              <option value="">Todas</option>
              {brandOptions.map((brand) => (
                <option key={brand} value={brand}>
                  {brand}
                </option>
              ))}
            </select>
          </label>
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
          <label className="block lg:col-span-2">
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
          <div className="flex items-end lg:col-span-2">
            <button
              type="button"
              onClick={applyFilters}
              className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
            >
              Aplicar filtros
            </button>
          </div>
        </div>
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
                <th className="px-3 py-3 font-semibold">Última oferta proveedor</th>
                <th className="px-3 py-3 font-semibold">Vínculos</th>
                <th className="px-3 py-3 font-semibold">Estado</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--color-border)]">
              {items.map((item) => (
                <tr key={item.product_key} className="hover:bg-brand-50/40">
                  <td className="px-3 py-3">
                    <button
                      type="button"
                      onClick={() => openProduct(item.product_key)}
                      className="text-left font-medium text-brand-800 hover:underline"
                    >
                      {item.display_name}
                    </button>
                  </td>
                  <td className="px-3 py-3">{item.brand ?? "—"}</td>
                  <td className="px-3 py-3 text-[var(--color-muted)]">Ver detalle</td>
                  <td className="px-3 py-3">
                    {catalogEquipmentClassLabel(item.equipment_class)}
                  </td>
                  <td className="px-3 py-3">{item.model_number ?? "—"}</td>
                  <td className="max-w-xs px-3 py-3 text-[var(--color-muted)]">
                    {listOfferHint(item)}
                  </td>
                  <td className="px-3 py-3 text-[var(--color-muted)]">{listLinksHint(item)}</td>
                  <td className="px-3 py-3">{catalogConfidenceLabel(item.confidence)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-[var(--color-border)] px-3 py-2 text-xs text-[var(--color-muted)]">
            {total} producto{total === 1 ? "" : "s"} catalogado{total === 1 ? "" : "s"}
          </p>
        </div>
      ) : null}

      <CatalogProductDrawer
        product={detail}
        loading={detailLoading}
        error={detailError}
        open={selectedKey !== null}
        onClose={closeDrawer}
      />
    </div>
  );
}
