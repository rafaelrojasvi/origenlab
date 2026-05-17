import { useEffect, useState } from "react";
import { ApiError, fetchCommercialPurchaseEvents } from "../api/client";
import type { ClassificationRecent, CommercialPurchaseEventsList } from "../api/types";
import { ConfirmedPurchaseEventsSection } from "./ConfirmedPurchaseEventsSection";
import { PurchaseSignalsSection } from "./PurchaseSignalsSection";

interface Props {
  purchaseSignals: ClassificationRecent | null;
}

type ConfirmedLoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; data: CommercialPurchaseEventsList };

export function ComprasTab({ purchaseSignals }: Props) {
  const [confirmed, setConfirmed] = useState<ConfirmedLoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setConfirmed({ status: "loading" });
      try {
        const data = await fetchCommercialPurchaseEvents(20);
        if (!cancelled) {
          setConfirmed({ status: "ready", data });
        }
      } catch (e) {
        if (!cancelled) {
          const message =
            e instanceof ApiError
              ? `API (${e.status}): ${e.message}`
              : e instanceof Error
                ? e.message
                : "Error desconocido";
          setConfirmed({ status: "error", message });
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="space-y-8">
      <header>
        <h2 className="text-lg font-semibold text-brand-900">Compras / clientes recientes</h2>
        <p className="text-sm text-[var(--color-muted)]">
          Órdenes de compra confirmadas (promovidas desde Gmail/SQLite) y, debajo, señales
          heurísticas que requieren revisión.
        </p>
      </header>

      <ConfirmedPurchaseEventsSection confirmed={confirmed} />

      <PurchaseSignalsSection purchases={purchaseSignals} nested />
    </div>
  );
}
