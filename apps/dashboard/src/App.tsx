import { PrivateDashboardPlaceholder } from "./components/PrivateDashboardPlaceholder";
import { isDashboardHostAllowed } from "./lib/dashboardHostGuard";
import { DashboardApp } from "./pages/DashboardApp";

function readBrowserHostname(): string {
  if (typeof window === "undefined") {
    return "";
  }
  return window.location.hostname;
}

/** Dashboard v0: operator Today page (apps/api read-only). */
export default function App() {
  if (!isDashboardHostAllowed(readBrowserHostname())) {
    return <PrivateDashboardPlaceholder />;
  }
  return <DashboardApp />;
}
