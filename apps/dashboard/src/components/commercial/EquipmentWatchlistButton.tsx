import type { EquipmentOpportunityItem } from "../../api/commercialTypes";

export function EquipmentWatchlistButton({
  item,
  saved,
  onToggle,
}: {
  item: EquipmentOpportunityItem;
  saved: boolean;
  onToggle: () => void;
}) {
  const label = item.buyer?.trim() || item.codigo_licitacion?.trim() || "oportunidad";

  return (
    <button
      type="button"
      data-testid="equipment-watchlist-button"
      aria-label={saved ? `Quitar de guardadas: ${label}` : `Guardar oportunidad: ${label}`}
      className={`mt-1 inline-flex rounded-md border px-2 py-0.5 text-[11px] font-medium ${
        saved
          ? "border-amber-200 bg-amber-50 text-amber-900"
          : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50"
      }`}
      onClick={(event) => {
        event.stopPropagation();
        onToggle();
      }}
    >
      {saved ? "Guardada" : "Guardar"}
    </button>
  );
}
