import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type {
  EquipmentOpportunitiesUiResponse,
  WarmCasesResponse,
} from "../api/commercialTypes";
import {
  OperatorApiError,
  DASHBOARD_WARM_CASES_QUERY,
  fetchEquipmentOpportunities,
  fetchTodayPanel,
  fetchWarmCases,
} from "../api/operatorClient";
import type { TodayPanelData } from "../api/operatorTypes";
import type { CatalogProductsListUi } from "../api/catalogTypes";
import type { CommercialDealsListUi } from "../api/commercialDealsTypes";
import { fetchCatalogProductsMirror } from "../api/mirrorCatalogClient";
import { fetchCommercialDealsMirror } from "../api/mirrorCommercialClient";
import {
  getLegacyDevPortWarning,
  logLegacyDevPortWarningIfNeeded,
} from "../lib/devApiConfig";

function formatLoadError(label: string, e: unknown): string {
  if (e instanceof OperatorApiError) {
    return `${label} (API ${e.status}): ${e.message}`;
  }
  if (e instanceof Error) {
    return `${label}: ${e.message}`;
  }
  return `${label}: unknown error`;
}

export interface DashboardDataState {
  data: TodayPanelData | null;
  panelLoading: boolean;
  panelError: string | null;
  warm: WarmCasesResponse | null;
  warmLoading: boolean;
  warmError: string | null;
  equipment: EquipmentOpportunitiesUiResponse | null;
  equipmentLoading: boolean;
  equipmentError: string | null;
  commercialDeals: CommercialDealsListUi | null;
  commercialDealsLoading: boolean;
  commercialDealsError: string | null;
  catalogProducts: CatalogProductsListUi | null;
  catalogProductsLoading: boolean;
  catalogProductsError: string | null;
  contactEmail: string | null;
  setContactEmail: (email: string | null) => void;
  loadAll: () => void;
  loadPanel: () => Promise<void>;
  loadWarm: () => Promise<void>;
  loadEquipment: () => Promise<void>;
  loadCommercialDeals: () => Promise<void>;
  loadCatalogProducts: () => Promise<void>;
  refreshing: boolean;
  mirrorBackend: boolean;
  backend: TodayPanelData["health"]["backend"] | "sqlite";
  devConfigWarning: string | null;
}

const DashboardDataContext = createContext<DashboardDataState | null>(null);

export function DashboardDataProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<TodayPanelData | null>(null);
  const [panelLoading, setPanelLoading] = useState(true);
  const [panelError, setPanelError] = useState<string | null>(null);

  const [warm, setWarm] = useState<WarmCasesResponse | null>(null);
  const [warmLoading, setWarmLoading] = useState(true);
  const [warmError, setWarmError] = useState<string | null>(null);

  const [equipment, setEquipment] = useState<EquipmentOpportunitiesUiResponse | null>(null);
  const [equipmentLoading, setEquipmentLoading] = useState(true);
  const [equipmentError, setEquipmentError] = useState<string | null>(null);

  const [commercialDeals, setCommercialDeals] = useState<CommercialDealsListUi | null>(null);
  const [commercialDealsLoading, setCommercialDealsLoading] = useState(true);
  const [commercialDealsError, setCommercialDealsError] = useState<string | null>(null);

  const [catalogProducts, setCatalogProducts] = useState<CatalogProductsListUi | null>(null);
  const [catalogProductsLoading, setCatalogProductsLoading] = useState(true);
  const [catalogProductsError, setCatalogProductsError] = useState<string | null>(null);

  const [contactEmail, setContactEmail] = useState<string | null>(null);

  const loadPanel = useCallback(async () => {
    setPanelLoading(true);
    setPanelError(null);
    try {
      setData(await fetchTodayPanel());
    } catch (e) {
      setPanelError(formatLoadError("Operator status", e));
      setData(null);
    } finally {
      setPanelLoading(false);
    }
  }, []);

  const loadWarm = useCallback(async () => {
    setWarmLoading(true);
    setWarmError(null);
    try {
      setWarm(await fetchWarmCases(DASHBOARD_WARM_CASES_QUERY));
    } catch (e) {
      setWarmError(formatLoadError("Warm cases", e));
      setWarm(null);
    } finally {
      setWarmLoading(false);
    }
  }, []);

  const loadEquipment = useCallback(async () => {
    setEquipmentLoading(true);
    setEquipmentError(null);
    try {
      setEquipment(await fetchEquipmentOpportunities());
    } catch (e) {
      setEquipmentError(formatLoadError("Equipment opportunities", e));
      setEquipment(null);
    } finally {
      setEquipmentLoading(false);
    }
  }, []);

  const loadCommercialDeals = useCallback(async () => {
    setCommercialDealsLoading(true);
    setCommercialDealsError(null);
    try {
      setCommercialDeals(await fetchCommercialDealsMirror());
    } catch (e) {
      setCommercialDealsError(formatLoadError("Commercial deals mirror", e));
      setCommercialDeals(null);
    } finally {
      setCommercialDealsLoading(false);
    }
  }, []);

  const loadCatalogProducts = useCallback(async () => {
    setCatalogProductsLoading(true);
    setCatalogProductsError(null);
    try {
      setCatalogProducts(await fetchCatalogProductsMirror({ limit: 100 }));
    } catch (e) {
      setCatalogProductsError(formatLoadError("Catálogo", e));
      setCatalogProducts(null);
    } finally {
      setCatalogProductsLoading(false);
    }
  }, []);

  const loadAll = useCallback(() => {
    void Promise.all([
      loadPanel(),
      loadWarm(),
      loadEquipment(),
      loadCommercialDeals(),
      loadCatalogProducts(),
    ]);
  }, [loadPanel, loadWarm, loadEquipment, loadCommercialDeals, loadCatalogProducts]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const devConfigWarning = useMemo(() => getLegacyDevPortWarning(), []);

  useEffect(() => {
    logLegacyDevPortWarningIfNeeded();
  }, [devConfigWarning]);

  const mirrorBackend = data?.health.backend === "postgres";
  const backend = data?.health.backend ?? "sqlite";
  const refreshing =
    panelLoading ||
    warmLoading ||
    equipmentLoading ||
    commercialDealsLoading ||
    catalogProductsLoading;

  const value = useMemo<DashboardDataState>(
    () => ({
      data,
      panelLoading,
      panelError,
      warm,
      warmLoading,
      warmError,
      equipment,
      equipmentLoading,
      equipmentError,
      commercialDeals,
      commercialDealsLoading,
      commercialDealsError,
      catalogProducts,
      catalogProductsLoading,
      catalogProductsError,
      contactEmail,
      setContactEmail,
      loadAll,
      loadPanel,
      loadWarm,
      loadEquipment,
      loadCommercialDeals,
      loadCatalogProducts,
      refreshing,
      mirrorBackend,
      backend,
      devConfigWarning,
    }),
    [
      data,
      panelLoading,
      panelError,
      warm,
      warmLoading,
      warmError,
      equipment,
      equipmentLoading,
      equipmentError,
      commercialDeals,
      commercialDealsLoading,
      commercialDealsError,
      catalogProducts,
      catalogProductsLoading,
      catalogProductsError,
      contactEmail,
      loadAll,
      loadPanel,
      loadWarm,
      loadEquipment,
      loadCommercialDeals,
      loadCatalogProducts,
      refreshing,
      mirrorBackend,
      backend,
      devConfigWarning,
    ],
  );

  return <DashboardDataContext.Provider value={value}>{children}</DashboardDataContext.Provider>;
}

export function useDashboardData(): DashboardDataState {
  const ctx = useContext(DashboardDataContext);
  if (!ctx) {
    throw new Error("useDashboardData must be used within DashboardDataProvider");
  }
  return ctx;
}
