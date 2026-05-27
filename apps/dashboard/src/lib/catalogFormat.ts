/** Spanish labels and formatting for catalog mirror UI. */

import type {
  CatalogCommercialLinkUi,
  CatalogPriceSnapshotUi,
  CatalogProductDetailUi,
  CatalogProductListItemUi,
  CatalogSupplierOfferUi,
} from "../api/catalogTypes";

export const CATALOG_CATEGORY_FILTER_OPTIONS: { key: string; label: string }[] = [
  { key: "electrophoresis_reagent", label: "Reactivo de electroforesis" },
  { key: "heating_accessory", label: "Accesorio de calentamiento" },
  { key: "lab_reactor", label: "Reactor de laboratorio" },
  { key: "ultrasonic_processor", label: "Procesador ultrasónico" },
  { key: "microcentrifuge", label: "Microcentrífuga" },
  { key: "analytical_balance", label: "Balanza analítica" },
];

const PRODUCT_KIND_LABELS: Record<string, string> = {
  reagent: "Reactivo",
  equipment: "Equipo",
  accessory: "Accesorio",
  spare_part: "Repuesto",
};

const EQUIPMENT_CLASS_LABELS: Record<string, string> = {
  reactor: "Reactor",
  sonicator: "Procesador ultrasónico",
  centrifuge: "Centrífuga",
  balance: "Balanza",
};

const CONFIDENCE_LABELS: Record<string, string> = {
  website_editorial: "Ficha web",
  operator_confirmed: "Confirmado por operador",
  extracted_needs_review: "Requiere revisión",
};

export function catalogProductKindLabel(kind: string | null | undefined): string {
  const key = (kind ?? "").trim().toLowerCase();
  return PRODUCT_KIND_LABELS[key] ?? kind ?? "—";
}

export function catalogEquipmentClassLabel(value: string | null | undefined): string {
  if (!value?.trim()) {
    return "—";
  }
  const key = value.trim().toLowerCase();
  return EQUIPMENT_CLASS_LABELS[key] ?? value;
}

export function catalogConfidenceLabel(confidence: string | null | undefined): string {
  const key = (confidence ?? "").trim().toLowerCase();
  return CONFIDENCE_LABELS[key] ?? confidence ?? "—";
}

export function catalogCurrencyLabel(currency: string | null | undefined): string {
  const c = currency?.trim();
  if (!c) {
    return "Moneda pendiente";
  }
  return c.toUpperCase();
}

export function formatCatalogAmount(amount: string | null | undefined, currency: string | null): string {
  const value = amount?.trim();
  if (!value) {
    return "—";
  }
  const cur = currency?.trim();
  if (!cur) {
    return value;
  }
  return `${cur.toUpperCase()} ${value}`;
}

export function supplierPriceVisibilityLabel(isPublicSafe: boolean): string {
  return isPublicSafe ? "Precio público" : "Precio interno / no público";
}

export function primaryCategoryLabel(detail: CatalogProductDetailUi | null): string {
  if (!detail?.categories?.length) {
    return "—";
  }
  const primary = detail.categories.find((c) => c.is_primary) ?? detail.categories[0];
  return primary.display_name || "—";
}

export function listOfferHint(item: CatalogProductListItemUi): string {
  const summary = item.public_summary?.trim();
  if (!summary) {
    return "Sin oferta registrada";
  }
  if (summary.length > 72) {
    return `${summary.slice(0, 72)}…`;
  }
  return summary;
}

export function listLinksHint(item: CatalogProductListItemUi): string {
  return item.confidence === "extracted_needs_review" ? "Revisar vínculos" : "Ver detalle";
}

export function formatCommercialLinkRef(link: CatalogCommercialLinkUi): string {
  const ref = link.link_ref.trim();
  if (link.link_kind === "commercial_deal_line") {
    const dealPart = ref.replace(/^deal:/, "").split(":line:")[0];
    return `Negocio ${dealPart}`;
  }
  if (link.link_kind === "warm_case") {
    return `Caso ${ref.replace(/^warm_case:/, "")}`;
  }
  if (link.link_kind === "website_product") {
    return `Web ${ref.replace(/^web:/, "")}`;
  }
  if (link.link_kind === "equipment_opportunity") {
    return `Oportunidad ${ref.replace(/^equipment:/, "")}`;
  }
  return ref || "—";
}

export function latestSupplierOffer(
  offers: CatalogSupplierOfferUi[],
): CatalogSupplierOfferUi | null {
  if (!offers.length) {
    return null;
  }
  return offers[0];
}

export function latestPriceSnapshot(
  snapshots: CatalogPriceSnapshotUi[],
): CatalogPriceSnapshotUi | null {
  if (!snapshots.length) {
    return null;
  }
  return snapshots[0];
}
