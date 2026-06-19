import { useCallback, useState } from "react";
import type { EquipmentOpportunityItem } from "../api/commercialTypes";

export const EQUIPMENT_WATCHLIST_STORAGE_KEY = "origenlab.dashboard.equipmentWatchlist.v1";
export const EQUIPMENT_WATCHLIST_MAX_KEYS = 500;

function fallbackEquipmentRowKey(row: EquipmentOpportunityItem): string {
  const code = row.codigo_licitacion?.trim() || row.buyer?.trim() || "row";
  return `eq-${row.priority_rank}-${code}`;
}

export function getEquipmentWatchlistKey(item: EquipmentOpportunityItem): string {
  const opportunityKey = item.opportunity_key?.trim();
  if (opportunityKey) {
    return opportunityKey;
  }
  return fallbackEquipmentRowKey(item);
}

function resolveStorage(storage?: Storage): Storage | undefined {
  if (storage) {
    return storage;
  }
  if (typeof window === "undefined") {
    return undefined;
  }
  return window.localStorage;
}

export function readEquipmentWatchlist(storage?: Storage): Set<string> {
  try {
    const store = resolveStorage(storage);
    if (!store) {
      return new Set();
    }
    const raw = store.getItem(EQUIPMENT_WATCHLIST_STORAGE_KEY);
    if (!raw) {
      return new Set();
    }
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) {
      return new Set();
    }
    const keys = parsed.filter((value): value is string => typeof value === "string" && value.trim().length > 0);
    return new Set(keys.slice(0, EQUIPMENT_WATCHLIST_MAX_KEYS));
  } catch {
    return new Set();
  }
}

export function writeEquipmentWatchlist(keys: Set<string>, storage?: Storage): void {
  try {
    const store = resolveStorage(storage);
    if (!store) {
      return;
    }
    const payload = [...keys].slice(0, EQUIPMENT_WATCHLIST_MAX_KEYS);
    store.setItem(EQUIPMENT_WATCHLIST_STORAGE_KEY, JSON.stringify(payload));
  } catch {
    // localStorage may be unavailable or quota exceeded
  }
}

export function toggleEquipmentWatchlistKey(keys: Set<string>, key: string): Set<string> {
  const trimmed = key.trim();
  if (!trimmed) {
    return keys;
  }
  const next = new Set(keys);
  if (next.has(trimmed)) {
    next.delete(trimmed);
    return next;
  }
  next.add(trimmed);
  if (next.size <= EQUIPMENT_WATCHLIST_MAX_KEYS) {
    return next;
  }
  return new Set([...next].slice(-EQUIPMENT_WATCHLIST_MAX_KEYS));
}

export function useEquipmentWatchlist(storage?: Storage) {
  const [savedKeys, setSavedKeys] = useState<Set<string>>(() => readEquipmentWatchlist(storage));

  const persist = useCallback(
    (keys: Set<string>) => {
      setSavedKeys(keys);
      writeEquipmentWatchlist(keys, storage);
    },
    [storage],
  );

  const isSaved = useCallback(
    (item: EquipmentOpportunityItem) => savedKeys.has(getEquipmentWatchlistKey(item)),
    [savedKeys],
  );

  const toggleSaved = useCallback(
    (item: EquipmentOpportunityItem) => {
      const key = getEquipmentWatchlistKey(item);
      persist(toggleEquipmentWatchlistKey(savedKeys, key));
    },
    [persist, savedKeys],
  );

  const clearSaved = useCallback(() => {
    persist(new Set());
  }, [persist]);

  return {
    savedKeys,
    isSaved,
    toggleSaved,
    clearSaved,
  };
}
