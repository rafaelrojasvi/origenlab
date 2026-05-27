/** Spanish labels and formatting for catalog mirror UI. */

import type {
  CatalogCommercialLinkUi,
  CatalogPriceSnapshotUi,
  CatalogProductDetailUi,
  CatalogProductListItemUi,
  CatalogProductSpecUi,
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

const SPEC_GROUP_LABELS: Record<string, string> = {
  operation: "Operación",
  design: "Diseño",
  material: "Material",
  electrical: "Eléctrico",
  dimensions: "Dimensiones / capacidad",
  capacity: "Dimensiones / capacidad",
};

const MONTHS_ES = [
  "ene",
  "feb",
  "mar",
  "abr",
  "may",
  "jun",
  "jul",
  "ago",
  "sep",
  "oct",
  "nov",
  "dic",
] as const;

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

export function catalogSpecGroupLabel(group: string | null | undefined): string {
  const key = (group ?? "").trim().toLowerCase();
  if (!key) {
    return "General";
  }
  return SPEC_GROUP_LABELS[key] ?? group;
}

export function catalogCurrencyLabel(currency: string | null | undefined): string {
  const c = currency?.trim();
  if (!c) {
    return "Moneda pendiente";
  }
  return c.toUpperCase();
}

function parseDecimalParts(value: string): { intPart: string; decPart: string | null } | null {
  const normalized = value.trim().replace(/\s/g, "");
  const match = normalized.match(/^(-?\d+)(?:[.,](\d+))?$/);
  if (!match) {
    return null;
  }
  return { intPart: match[1], decPart: match[2] ?? null };
}

function formatThousandsDot(intPart: string): string {
  const negative = intPart.startsWith("-");
  const digits = negative ? intPart.slice(1) : intPart;
  const grouped = digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return negative ? `-${grouped}` : grouped;
}

/** Format catalog money for operator UI (CL locale style). */
export function formatCatalogMoney(
  amount: string | null | undefined,
  currency: string | null | undefined,
): string {
  const raw = amount?.trim();
  if (!raw) {
    return "—";
  }
  const cur = currency?.trim().toUpperCase();
  if (!cur) {
    const parts = parseDecimalParts(raw);
    if (parts) {
      const body =
        parts.decPart != null
          ? `${formatThousandsDot(parts.intPart)},${parts.decPart}`
          : formatThousandsDot(parts.intPart);
      return body;
    }
    return raw;
  }
  if (cur === "CLP") {
    const intOnly = raw.replace(/[.,]\d+$/, "").replace(/\D/g, "");
    if (intOnly) {
      return `$${formatThousandsDot(intOnly)}`;
    }
  }
  const parts = parseDecimalParts(raw);
  if (parts) {
    const body =
      parts.decPart != null
        ? `${formatThousandsDot(parts.intPart)},${parts.decPart}`
        : formatThousandsDot(parts.intPart);
    return `${cur} ${body}`;
  }
  return `${cur} ${raw}`;
}

export function formatCatalogAmount(amount: string | null | undefined, currency: string | null): string {
  return formatCatalogMoney(amount, currency);
}

export function formatCatalogQuantity(
  quantity: string | null | undefined,
  unit: string | null | undefined,
): string {
  const q = quantity?.trim();
  if (!q) {
    return "—";
  }
  const n = Number(q);
  if (!Number.isFinite(n)) {
    return q;
  }
  const unitNorm = (unit ?? "ea").trim().toLowerCase();
  const isUnit = unitNorm === "ea" || unitNorm === "un" || unitNorm === "und" || unitNorm === "u";
  if (n === 1 && isUnit) {
    return "1 unidad";
  }
  if (isUnit) {
    return `${q} unidades`;
  }
  return unit?.trim() ? `${q} ${unit}` : q;
}

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)?$/;

export function formatCatalogDate(value: string | null | undefined): string | null {
  const raw = value?.trim();
  if (!raw) {
    return null;
  }
  if (!ISO_DATE_RE.test(raw)) {
    const daysMatch = raw.match(/^(\d+)\s*days?\s*from\s*quote$/i);
    if (daysMatch) {
      return `Validez: ${daysMatch[1]} días desde la cotización`;
    }
    return raw;
  }
  const d = new Date(raw.includes("T") ? raw : `${raw}T12:00:00Z`);
  if (Number.isNaN(d.getTime())) {
    return raw;
  }
  const day = d.getUTCDate();
  const month = MONTHS_ES[d.getUTCMonth()];
  const year = d.getUTCFullYear();
  return `${day} ${month} ${year}`;
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

export function groupCatalogSpecs(specs: CatalogProductSpecUi[]): { label: string; items: CatalogProductSpecUi[] }[] {
  const buckets = new Map<string, CatalogProductSpecUi[]>();
  for (const spec of specs) {
    const label = catalogSpecGroupLabel(spec.spec_group);
    const list = buckets.get(label) ?? [];
    list.push(spec);
    buckets.set(label, list);
  }
  const order = ["Operación", "Diseño", "Material", "Eléctrico", "Dimensiones / capacidad", "General"];
  const keys = [...buckets.keys()].sort((a, b) => {
    const ai = order.indexOf(a);
    const bi = order.indexOf(b);
    if (ai === -1 && bi === -1) {
      return a.localeCompare(b, "es");
    }
    if (ai === -1) {
      return 1;
    }
    if (bi === -1) {
      return -1;
    }
    return ai - bi;
  });
  return keys.map((label) => ({ label, items: buckets.get(label) ?? [] }));
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
    return `Ficha web`;
  }
  if (link.link_kind === "equipment_opportunity") {
    return `Oportunidad ${ref.replace(/^equipment:/, "")}`;
  }
  return ref || "—";
}

export function summarizeCommercialLinks(links: CatalogCommercialLinkUi[]): string {
  if (!links.length) {
    return "Sin vínculos";
  }
  const parts: string[] = [];
  const deals = links.filter((l) => l.link_kind === "commercial_deal_line").length;
  const cases = links.filter((l) => l.link_kind === "warm_case").length;
  const web = links.filter((l) => l.link_kind === "website_product").length;
  if (web) {
    parts.push("Ficha web");
  }
  if (deals === 1) {
    parts.push("1 negocio");
  } else if (deals > 1) {
    parts.push(`${deals} negocios`);
  }
  if (cases === 1) {
    parts.push("1 caso");
  } else if (cases > 1) {
    parts.push(`${cases} casos`);
  }
  if (!parts.length) {
    return `${links.length} vínculo${links.length === 1 ? "" : "s"}`;
  }
  return parts.join(" · ");
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

export function buildListOfferSummary(detail: CatalogProductDetailUi | null): string {
  if (!detail) {
    return "—";
  }
  const snap = latestPriceSnapshot(detail.price_snapshots);
  const offer = latestSupplierOffer(detail.supplier_offers);
  if (!snap && !offer) {
    return "Sin oferta registrada";
  }

  const key = detail.product_key;
  if (key === "crtop-olt-hp-5l" && snap) {
    const parts = [
      formatCatalogMoney(snap.amount_decimal, snap.currency),
      snap.incoterm ?? offer?.incoterm,
      formatCatalogQuantity(snap.quantity ?? offer?.quantity_offered, snap.unit),
    ].filter(Boolean);
    return parts.join(" · ");
  }
  if (key === "ika-rv10-70-vapor-tube" && snap) {
    const amount = snap.currency
      ? formatCatalogMoney(snap.amount_decimal, snap.currency)
      : formatCatalogMoney(snap.amount_decimal, null);
    const parts = [amount, "Moneda pendiente", "revisar"];
    return parts.join(" · ");
  }

  if (snap?.amount_decimal) {
    const amount = formatCatalogMoney(snap.amount_decimal, snap.currency);
    const amountLabel = snap.currency ? amount : `${amount} · Moneda pendiente`;
    const incoterm = snap.incoterm ?? offer?.incoterm;
    return [amountLabel, incoterm, formatCatalogQuantity(snap.quantity, snap.unit)]
      .filter(Boolean)
      .join(" · ");
  }
  if (offer?.availability_note) {
    const note = offer.availability_note;
    return note.length > 72 ? `${note.slice(0, 72)}…` : note;
  }
  return "Sin oferta registrada";
}

export function buildListLinksSummary(detail: CatalogProductDetailUi | null): string {
  if (!detail) {
    return "—";
  }
  return summarizeCommercialLinks(detail.commercial_links);
}

export function catalogWebsiteHref(slug: string | null | undefined): string | null {
  const s = slug?.trim();
  if (!s) {
    return null;
  }
  if (s.startsWith("http://") || s.startsWith("https://")) {
    return s;
  }
  return `https://origenlab.cl/productos/${encodeURIComponent(s)}`;
}

/** @deprecated use buildListOfferSummary with detail */
export function listOfferHint(_item: CatalogProductListItemUi): string {
  return "Ver detalle";
}

/** @deprecated use buildListLinksSummary with detail */
export function listLinksHint(_item: CatalogProductListItemUi): string {
  return "Ver detalle";
}
