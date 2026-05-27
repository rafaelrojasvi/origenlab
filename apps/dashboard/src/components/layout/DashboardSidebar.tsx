import { OrigenLabStaticLogo } from "../brand/OrigenLabStaticLogo";
import { DASHBOARD_NAV_ITEMS, type DashboardSection } from "../../lib/dashboardNav";

export function DashboardSidebar({
  active,
  onNavigate,
}: {
  active: DashboardSection;
  onNavigate: (section: DashboardSection) => void;
}) {
  return (
    <aside className="flex w-60 shrink-0 flex-col border-r border-brand-900/30 bg-brand-950 text-brand-50 shadow-lg">
      <div className="border-b border-brand-900/40 px-4 py-5">
        <OrigenLabStaticLogo />
        <p className="mt-3 text-[11px] uppercase tracking-wide text-teal-200/70">
          Solo lectura · no envía correos
        </p>
      </div>
      <nav className="flex-1 overflow-y-auto px-2 py-4" aria-label="Navegación del panel">
        <ul className="space-y-1">
          {DASHBOARD_NAV_ITEMS.map((item) => {
            const isActive = item.id === active;
            return (
              <li key={item.id}>
                <a
                  href={item.id === "today" ? "#/" : `#/${item.id}`}
                  onClick={(e) => {
                    e.preventDefault();
                    onNavigate(item.id);
                  }}
                  aria-current={isActive ? "page" : undefined}
                  title={item.description}
                  className={`block rounded-lg px-3 py-2.5 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-brand-600 text-white shadow-sm ring-1 ring-brand-700/50"
                      : "text-teal-100/90 hover:bg-brand-900/80 hover:text-white"
                  }`}
                >
                  {item.label}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
      <footer className="border-t border-brand-900/40 px-4 py-3 text-[11px] text-teal-200/60">
        OrigenLab · Chile · equipos de laboratorio
      </footer>
    </aside>
  );
}
