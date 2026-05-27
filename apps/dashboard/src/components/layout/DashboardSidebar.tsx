import { DASHBOARD_NAV_ITEMS, type DashboardSection } from "../../lib/dashboardNav";

export function DashboardSidebar({
  active,
  onNavigate,
}: {
  active: DashboardSection;
  onNavigate: (section: DashboardSection) => void;
}) {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-[var(--color-border)] bg-[var(--color-card)]">
      <div className="border-b border-[var(--color-border)] px-4 py-5">
        <p className="text-xs font-semibold uppercase tracking-wide text-brand-600">OrigenLab</p>
        <p className="mt-1 text-sm font-semibold text-brand-900">Operator dashboard</p>
        <p className="mt-1 text-xs text-[var(--color-muted)]">Read-only · GET only</p>
      </div>
      <nav
        className="flex-1 overflow-y-auto px-2 py-3"
        aria-label="Dashboard navigation"
      >
        <ul className="space-y-0.5">
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
                  className={`block rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-brand-600 text-white"
                      : "text-slate-700 hover:bg-slate-100"
                  }`}
                >
                  {item.label}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
    </aside>
  );
}
