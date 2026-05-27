/** Secciones principales del panel operador (Phase 7B). */

export type DashboardSection =
  | "today"
  | "inbox"
  | "opportunities"
  | "deals"
  | "prospectos"
  | "catalogo"
  | "suppliers"
  | "tenders"
  | "payments-logistics"
  | "contacts"
  | "system";

export interface DashboardNavItem {
  id: DashboardSection;
  label: string;
  description: string;
}

export const DASHBOARD_NAV_ITEMS: DashboardNavItem[] = [
  { id: "today", label: "Hoy", description: "Resumen del día y conteos" },
  { id: "inbox", label: "Bandeja de revisión", description: "Correos tibios con filtros por rol" },
  { id: "opportunities", label: "Oportunidades", description: "Cola de equipos y señales" },
  { id: "deals", label: "Negocios", description: "Espejo de negocios comerciales" },
  {
    id: "prospectos",
    label: "Prospectos",
    description: "Nuevas oportunidades de clientes (investigación DeepSearch)",
  },
  {
    id: "catalogo",
    label: "Catálogo",
    description: "Productos, reactivos, equipos y repuestos cotizables",
  },
  { id: "suppliers", label: "Proveedores", description: "Cotizaciones y seguimientos de proveedores" },
  { id: "tenders", label: "Licitaciones", description: "Señales de compras públicas" },
  {
    id: "payments-logistics",
    label: "Pagos y logística",
    description: "Banco, transferencias, DHL e importación",
  },
  { id: "contacts", label: "Contactos", description: "Perfiles de contacto en solo lectura" },
  { id: "system", label: "Sistema", description: "Estado del servicio y política de lectura" },
];

export const DEFAULT_DASHBOARD_SECTION: DashboardSection = "today";

export function dashboardSectionLabel(section: DashboardSection): string {
  return DASHBOARD_NAV_ITEMS.find((item) => item.id === section)?.label ?? section;
}
