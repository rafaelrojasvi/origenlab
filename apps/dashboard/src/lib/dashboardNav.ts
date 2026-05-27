/** Top-level dashboard sections (Phase 7B.1). */

export type DashboardSection =
  | "today"
  | "inbox"
  | "opportunities"
  | "deals"
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
  { id: "today", label: "Today", description: "Operator verdict and summary counts" },
  { id: "inbox", label: "Inbox triage", description: "Warm cases with role filters" },
  { id: "opportunities", label: "Opportunities", description: "Equipment opportunity queue" },
  { id: "deals", label: "Deals", description: "Commercial deals mirror" },
  { id: "suppliers", label: "Suppliers", description: "Supplier quotes and follow-ups" },
  { id: "tenders", label: "Tenders", description: "Public procurement signals" },
  { id: "payments-logistics", label: "Payments & logistics", description: "Bank, Wise, DHL, import admin" },
  { id: "contacts", label: "Contacts", description: "Read-only contact profiles" },
  { id: "system", label: "System", description: "API health and read-only policy" },
];

export const DEFAULT_DASHBOARD_SECTION: DashboardSection = "today";

export function dashboardSectionLabel(section: DashboardSection): string {
  return DASHBOARD_NAV_ITEMS.find((item) => item.id === section)?.label ?? section;
}
