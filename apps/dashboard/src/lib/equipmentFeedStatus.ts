/** Equipment / licitaciones feed availability (read-only dashboard). */

export type EquipmentFeedMeta = {
  reduced_mode: boolean;
  note?: string;
  count?: number;
};

export function isEquipmentFeedUnavailable(meta: EquipmentFeedMeta | null | undefined): boolean {
  return Boolean(meta?.reduced_mode);
}

export const EQUIPMENT_FEED_UNAVAILABLE_TITLE = "Fuente de licitaciones no disponible";

export const EQUIPMENT_FEED_UNAVAILABLE_LINES = [
  "No significa que no existan oportunidades.",
  "Revisar generación de equipment_first_operator_queue.",
] as const;
