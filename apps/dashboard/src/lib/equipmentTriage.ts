import type { EquipmentOpportunityItem } from "../api/commercialTypes";
import { parseSortableTimestamp } from "./clientTableView";

export type EquipmentTriageTone = "urgent" | "warning" | "info" | "ok" | "muted";

export type EquipmentTriageBadge = {
  label: string;
  tone: EquipmentTriageTone;
  reason: string;
};

export const EQUIPMENT_TRIAGE_TONE_CLASS: Record<EquipmentTriageTone, string> = {
  urgent: "border-rose-200 bg-rose-50 text-rose-900",
  warning: "border-amber-200 bg-amber-50 text-amber-950",
  info: "border-sky-200 bg-sky-50 text-sky-900",
  ok: "border-emerald-200 bg-emerald-50 text-emerald-900",
  muted: "border-slate-200 bg-slate-50 text-slate-600",
};

const MAX_TRIAGE_BADGES = 3;
const CLOSING_SOON_DAYS = 3;
const MS_PER_DAY = 24 * 60 * 60 * 1000;

function normalizeToken(value: string | null | undefined): string {
  return (value ?? "").trim().toLowerCase();
}

function parseEquipmentCloseTimestamp(
  item: EquipmentOpportunityItem,
): number | null {
  const closeAt = item.close_at?.trim();
  if (closeAt) {
    const ts = parseSortableTimestamp(closeAt);
    if (ts > 0) return ts;
  }
  const closeDate = item.close_date?.trim();
  if (!closeDate) return null;
  const ts = parseSortableTimestamp(closeDate);
  return ts > 0 ? ts : null;
}

function isQuoteNow(item: EquipmentOpportunityItem): boolean {
  return normalizeToken(item.next_action) === "quote_now";
}

function isClosingSoon(item: EquipmentOpportunityItem, now: Date): boolean {
  const closeTs = parseEquipmentCloseTimestamp(item);
  if (closeTs == null) return false;
  const nowTs = now.getTime();
  const daysUntil = (closeTs - nowTs) / MS_PER_DAY;
  return daysUntil >= 0 && daysUntil <= CLOSING_SOON_DAYS;
}

function hasContactEmail(item: EquipmentOpportunityItem): boolean {
  return Boolean(item.contact_email?.trim());
}

function suggestsNoVerifiedBuyerEmail(contactStatus: string): boolean {
  const status = normalizeToken(contactStatus);
  if (!status) return true;
  return (
    status === "no_verified_buyer_email" ||
    status.includes("no_verified") ||
    status.includes("sin_correo") ||
    status.includes("sin correo")
  );
}

function isSupplierNeeded(value: string): boolean {
  const token = normalizeToken(value);
  if (!token) return false;
  return (
    token === "yes" ||
    token === "si" ||
    token === "sí" ||
    token === "true" ||
    token === "1" ||
    token.startsWith("yes")
  );
}

function isMercadoPublicoOnly(item: EquipmentOpportunityItem): boolean {
  return normalizeToken(item.safe_channel) === "mercado_publico_only";
}

export function getEquipmentTriageBadges(
  item: EquipmentOpportunityItem,
  options?: { now?: Date },
): EquipmentTriageBadge[] {
  const now = options?.now ?? new Date();
  const badges: EquipmentTriageBadge[] = [];

  if (isQuoteNow(item)) {
    badges.push({
      label: "Cotizar ahora",
      tone: "urgent",
      reason: "La acción recomendada es cotizar de inmediato.",
    });
  }

  if (isClosingSoon(item, now)) {
    badges.push({
      label: "Cierre pronto",
      tone: "warning",
      reason: "La fecha de cierre está dentro de los próximos 3 días.",
    });
  }

  if (!hasContactEmail(item) && suggestsNoVerifiedBuyerEmail(item.contact_status)) {
    badges.push({
      label: "Sin contacto",
      tone: "warning",
      reason: "No hay correo de contacto verificado para el comprador.",
    });
  }

  if (isSupplierNeeded(item.supplier_needed)) {
    badges.push({
      label: "Requiere proveedor",
      tone: "info",
      reason: "La oportunidad indica que se necesita proveedor.",
    });
  }

  if (isMercadoPublicoOnly(item)) {
    badges.push({
      label: "Solo Mercado Público",
      tone: "muted",
      reason: "El canal seguro permite solo Mercado Público.",
    });
  }

  return badges.slice(0, MAX_TRIAGE_BADGES);
}
