import type { EquipmentOpportunityItem } from "../../api/commercialTypes";
import {
  EQUIPMENT_TRIAGE_TONE_CLASS,
  getEquipmentTriageBadges,
} from "../../lib/equipmentTriage";

export function EquipmentTriageBadges({ item }: { item: EquipmentOpportunityItem }) {
  const badges = getEquipmentTriageBadges(item);
  if (!badges.length) return null;

  return (
    <div className="mt-1 flex flex-wrap gap-1" data-testid="equipment-triage-badges">
      {badges.map((badge) => (
        <span
          key={badge.key}
          title={badge.reason}
          data-testid="equipment-triage-badge"
          className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] font-medium leading-tight ${EQUIPMENT_TRIAGE_TONE_CLASS[badge.tone]}`}
        >
          {badge.label}
        </span>
      ))}
    </div>
  );
}
