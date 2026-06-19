import { useCallback, useState } from "react";
import type { WarmCaseItem } from "../api/commercialTypes";

export const WARM_CASE_REVIEW_LABELS_STORAGE_KEY = "origenlab.dashboard.warmCaseReviewLabels.v1";
export const WARM_CASE_REVIEW_LABELS_MAX_ENTRIES = 500;

/** Blank means “Sin revisar”. */
export type WarmCaseReviewLabel =
  | ""
  | "util"
  | "no_util"
  | "mal_clasificado"
  | "ya_gestionado"
  | "necesita_seguimiento";

export type WarmCaseReviewFilter = "all" | "unreviewed" | WarmCaseReviewLabel;

export const WARM_CASE_REVIEW_LABEL_OPTIONS: {
  value: Exclude<WarmCaseReviewLabel, "">;
  label: string;
}[] = [
  { value: "util", label: "Útil" },
  { value: "no_util", label: "No útil" },
  { value: "mal_clasificado", label: "Mal clasificado" },
  { value: "ya_gestionado", label: "Ya gestionado" },
  { value: "necesita_seguimiento", label: "Necesita seguimiento" },
];

export const WARM_CASE_REVIEW_FILTER_OPTIONS: { value: WarmCaseReviewFilter; label: string }[] = [
  { value: "all", label: "Todas" },
  { value: "unreviewed", label: "Sin revisar" },
  ...WARM_CASE_REVIEW_LABEL_OPTIONS,
];

const VALID_LABELS = new Set<string>(WARM_CASE_REVIEW_LABEL_OPTIONS.map((option) => option.value));

export function isWarmCaseReviewLabel(value: string): value is Exclude<WarmCaseReviewLabel, ""> {
  return VALID_LABELS.has(value);
}

export function warmCaseReviewLabelText(label: WarmCaseReviewLabel): string {
  if (!label) {
    return "Sin revisar";
  }
  return WARM_CASE_REVIEW_LABEL_OPTIONS.find((option) => option.value === label)?.label ?? label;
}

function fallbackWarmCaseRowKey(row: WarmCaseItem): string {
  const email = row.contact_email?.trim() || "contact";
  const subject = row.subject?.trim() || "";
  const grouped = String(row.grouped_email_count ?? 1);
  const lastSeen = row.last_seen_at?.trim() || "";
  return `warm-fb-${email}|${subject}|${grouped}|${lastSeen}`;
}

export function getWarmCaseReviewKey(item: WarmCaseItem): string {
  const caseId = item.case_id?.trim();
  if (caseId) {
    return caseId;
  }
  return fallbackWarmCaseRowKey(item);
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

function normalizeLabelMap(raw: unknown): Record<string, WarmCaseReviewLabel> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    return {};
  }
  const entries: [string, WarmCaseReviewLabel][] = [];
  for (const [key, value] of Object.entries(raw)) {
    const trimmedKey = key.trim();
    if (!trimmedKey || typeof value !== "string") {
      continue;
    }
    if (value === "" || isWarmCaseReviewLabel(value)) {
      entries.push([trimmedKey, value]);
    }
  }
  return Object.fromEntries(entries.slice(0, WARM_CASE_REVIEW_LABELS_MAX_ENTRIES));
}

export function readWarmCaseReviewLabels(storage?: Storage): Record<string, WarmCaseReviewLabel> {
  try {
    const store = resolveStorage(storage);
    if (!store) {
      return {};
    }
    const raw = store.getItem(WARM_CASE_REVIEW_LABELS_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    return normalizeLabelMap(JSON.parse(raw));
  } catch {
    return {};
  }
}

export function writeWarmCaseReviewLabels(
  labels: Record<string, WarmCaseReviewLabel>,
  storage?: Storage,
): void {
  try {
    const store = resolveStorage(storage);
    if (!store) {
      return;
    }
    const capped = normalizeLabelMap(labels);
    store.setItem(WARM_CASE_REVIEW_LABELS_STORAGE_KEY, JSON.stringify(capped));
  } catch {
    // localStorage may be unavailable or quota exceeded
  }
}

export function setWarmCaseReviewLabel(
  labels: Record<string, WarmCaseReviewLabel>,
  key: string,
  label: WarmCaseReviewLabel,
): Record<string, WarmCaseReviewLabel> {
  const trimmedKey = key.trim();
  if (!trimmedKey) {
    return labels;
  }
  const next = { ...labels };
  if (!label) {
    delete next[trimmedKey];
    return next;
  }
  next[trimmedKey] = label;
  const entries = Object.entries(next);
  if (entries.length <= WARM_CASE_REVIEW_LABELS_MAX_ENTRIES) {
    return next;
  }
  return Object.fromEntries(entries.slice(-WARM_CASE_REVIEW_LABELS_MAX_ENTRIES));
}

export function countReviewedWarmCases(labels: Record<string, WarmCaseReviewLabel>): number {
  return Object.values(labels).filter((label) => Boolean(label)).length;
}

export function useWarmCaseReviewLabels(storage?: Storage) {
  const [labels, setLabels] = useState<Record<string, WarmCaseReviewLabel>>(() =>
    readWarmCaseReviewLabels(storage),
  );

  const persist = useCallback(
    (next: Record<string, WarmCaseReviewLabel>) => {
      setLabels(next);
      writeWarmCaseReviewLabels(next, storage);
    },
    [storage],
  );

  const getLabel = useCallback(
    (item: WarmCaseItem): WarmCaseReviewLabel => labels[getWarmCaseReviewKey(item)] ?? "",
    [labels],
  );

  const setLabel = useCallback(
    (item: WarmCaseItem, label: WarmCaseReviewLabel) => {
      const key = getWarmCaseReviewKey(item);
      persist(setWarmCaseReviewLabel(labels, key, label));
    },
    [labels, persist],
  );

  const clearLabels = useCallback(() => {
    persist({});
  }, [persist]);

  const reviewedCount = countReviewedWarmCases(labels);

  return {
    labels,
    reviewedCount,
    getLabel,
    setLabel,
    clearLabels,
  };
}
