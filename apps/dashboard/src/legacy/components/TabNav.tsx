export type DashboardTab =
  | "resumen"
  | "clasificacion"
  | "compras"
  | "contactos"
  | "archivo";

const TABS: { id: DashboardTab; label: string }[] = [
  { id: "resumen", label: "Resumen" },
  { id: "clasificacion", label: "Clasificación comercial" },
  { id: "compras", label: "Compras / clientes recientes" },
  { id: "contactos", label: "Contactos y organizaciones" },
  { id: "archivo", label: "Archivo histórico" },
];

interface Props {
  active: DashboardTab;
  onChange: (tab: DashboardTab) => void;
}

export function TabNav({ active, onChange }: Props) {
  return (
    <nav className="flex flex-wrap gap-2 border-b border-[var(--color-border)] pb-2" aria-label="Secciones">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          className={`rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
            active === tab.id
              ? "bg-brand-700 text-white shadow-sm"
              : "bg-[var(--color-card)] text-slate-700 hover:bg-brand-50"
          }`}
          aria-current={active === tab.id ? "page" : undefined}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
