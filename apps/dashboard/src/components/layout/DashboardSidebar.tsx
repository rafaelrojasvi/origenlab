import { OrigenLabStaticLogo } from "../brand/OrigenLabStaticLogo";
import {
  DASHBOARD_NAV_GROUPS,
  type DashboardNavItem,
  type DashboardSection,
} from "../../lib/dashboardNav";
import { NavIcon } from "./NavIcon";

function navHref(section: DashboardSection): string {
  return section === "today" ? "#/" : `#/${section}`;
}

function NavLink({
  item,
  isActive,
  collapsed,
  onNavigate,
}: {
  item: DashboardNavItem;
  isActive: boolean;
  collapsed: boolean;
  onNavigate: (section: DashboardSection) => void;
}) {
  return (
    <a
      href={navHref(item.id)}
      onClick={(e) => {
        e.preventDefault();
        onNavigate(item.id);
      }}
      aria-current={isActive ? "page" : undefined}
      aria-label={item.label}
      title={collapsed ? item.label : item.description}
      className={`group flex items-center gap-3 rounded-lg text-sm font-medium transition-colors motion-reduce:transition-none ${
        collapsed ? "justify-center px-2 py-2.5" : "px-3 py-2"
      } ${
        isActive
          ? "bg-brand-600 text-white shadow-sm ring-1 ring-brand-700/50"
          : "text-teal-100/90 hover:bg-brand-900/80 hover:text-white"
      }`}
    >
      <NavIcon
        name={item.iconName}
        className={`h-5 w-5 shrink-0 ${isActive ? "text-white" : "text-teal-200/90 group-hover:text-white"}`}
      />
      {!collapsed ? <span className="truncate">{item.label}</span> : null}
    </a>
  );
}

export function DashboardSidebar({
  active,
  collapsed,
  onNavigate,
  onToggleCollapsed,
}: {
  active: DashboardSection;
  collapsed: boolean;
  onNavigate: (section: DashboardSection) => void;
  onToggleCollapsed: () => void;
}) {
  return (
    <aside
      id="dashboard-sidebar"
      className={`flex shrink-0 flex-col border-r border-brand-900/30 bg-brand-950 text-brand-50 shadow-lg transition-[width] duration-200 ease-in-out motion-reduce:transition-none ${
        collapsed ? "w-16" : "w-64"
      }`}
      data-testid="dashboard-sidebar"
      data-collapsed={collapsed ? "true" : "false"}
    >
      <div
        className={`border-b border-brand-900/40 ${collapsed ? "px-2 py-3" : "px-4 py-4"}`}
      >
        {collapsed ? (
          <div className="flex justify-center" data-testid="origenlab-logo-static">
            <img
              src="/logo/origenlab-mark-static.svg"
              alt="OrigenLab"
              className="h-9 w-9 rounded-lg ring-1 ring-brand-700/40"
              width={36}
              height={36}
            />
          </div>
        ) : (
          <OrigenLabStaticLogo />
        )}
        {!collapsed ? (
          <p className="mt-2 text-[10px] uppercase tracking-wide text-teal-200/60">
            Solo lectura
          </p>
        ) : null}
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-3" aria-label="Navegación del panel">
        {DASHBOARD_NAV_GROUPS.map((group) => (
          <div key={group.id} className={collapsed ? "mb-2" : "mb-4"}>
            {!collapsed ? (
              <p
                className="mb-1.5 px-3 text-[10px] font-semibold uppercase tracking-wider text-teal-200/50"
                data-testid={`nav-group-${group.id}`}
              >
                {group.label}
              </p>
            ) : (
              <div
                className="mx-auto mb-1.5 h-px w-8 bg-brand-800/80"
                aria-hidden
                data-testid={`nav-group-${group.id}`}
              />
            )}
            <ul className="space-y-0.5">
              {group.items.map((item) => (
                <li key={item.id}>
                  <NavLink
                    item={item}
                    isActive={item.id === active}
                    collapsed={collapsed}
                    onNavigate={onNavigate}
                  />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-brand-900/40 p-2">
        <button
          type="button"
          onClick={onToggleCollapsed}
          className={`flex w-full items-center rounded-lg text-xs font-medium text-teal-200/80 transition-colors hover:bg-brand-900/80 hover:text-white motion-reduce:transition-none ${
            collapsed ? "justify-center px-2 py-2" : "gap-2 px-3 py-2"
          }`}
          aria-expanded={!collapsed}
          aria-controls="dashboard-sidebar"
          aria-label={collapsed ? "Expandir navegación" : "Contraer navegación"}
          data-testid="sidebar-collapse-toggle"
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
            className={`h-4 w-4 shrink-0 transition-transform duration-200 motion-reduce:transition-none ${
              collapsed ? "rotate-180" : ""
            }`}
            aria-hidden
          >
            <path d="M15 6l-6 6 6 6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {!collapsed ? <span>Contraer navegación</span> : null}
        </button>
        {!collapsed ? (
          <p className="mt-2 px-1 text-center text-[10px] text-teal-200/45">
            OrigenLab · Chile
          </p>
        ) : null}
      </div>
    </aside>
  );
}
