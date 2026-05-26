"""Operator-confirmed CLP margin costs and margin computation for commercial deals."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from origenlab_email_pipeline.commercial.commercial_deal_promotion import (
    connect_sqlite_rw,
    validate_sqlite_apply_target,
)
from origenlab_email_pipeline.commercial.commercial_deal_schema import (
    table_column_names,
)
from origenlab_email_pipeline.timeutil import now_iso

# CLI input slot -> commercial_deal_cost.cost_kind
COST_SLOT_TO_KIND: dict[str, str] = {
    "wise_clp_debit": "fx_spread",
    "dhl_cost_clp": "logistics_dhl",
    "import_cost_clp": "logistics_import",
    "bank_fee_clp": "bank_fee",
}

REQUIRED_MARGIN_SLOTS: tuple[str, ...] = (
    "wise_clp_debit",
    "dhl_cost_clp",
    "import_cost_clp",
)

MARGIN_CLP_COST_KINDS: frozenset[str] = frozenset(COST_SLOT_TO_KIND.values())

_SLOT_DESCRIPTIONS: dict[str, str] = {
    "wise_clp_debit": "Wise CLP debit (card settlement)",
    "dhl_cost_clp": "DHL / logistics CLP cost",
    "import_cost_clp": "Import / customs CLP cost",
    "bank_fee_clp": "Bank fee CLP",
}


@dataclass(frozen=True)
class MarginCostInputs:
    wise_clp_debit: int | None = None
    dhl_cost_clp: int | None = None
    import_cost_clp: int | None = None
    bank_fee_clp: int | None = None
    note: str | None = None

    def provided_slots(self) -> dict[str, int]:
        out: dict[str, int] = {}
        if self.wise_clp_debit is not None:
            out["wise_clp_debit"] = self.wise_clp_debit
        if self.dhl_cost_clp is not None:
            out["dhl_cost_clp"] = self.dhl_cost_clp
        if self.import_cost_clp is not None:
            out["import_cost_clp"] = self.import_cost_clp
        if self.bank_fee_clp is not None:
            out["bank_fee_clp"] = self.bank_fee_clp
        return out


@dataclass
class MarginUpdatePlan:
    deal_key: str
    deal_id: int
    mode: str
    client_sale_net_clp: int | None
    cost_rows: list[dict[str, Any]] = field(default_factory=list)
    margin_status: str = "needs_review"
    margin_net_clp: int | None = None
    margin_pct: float | None = None
    clp_cost_total: int | None = None
    remaining_blockers: list[str] = field(default_factory=list)
    ready_to_compute: bool = False
    operator_note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "deal_key": self.deal_key,
            "deal_id": self.deal_id,
            "mode": self.mode,
            "client_sale_net_clp": self.client_sale_net_clp,
            "cost_rows": self.cost_rows,
            "margin_status": self.margin_status,
            "margin_net_clp": self.margin_net_clp,
            "margin_pct": self.margin_pct,
            "clp_cost_total": self.clp_cost_total,
            "remaining_blockers": self.remaining_blockers,
            "ready_to_compute": self.ready_to_compute,
            "operator_note": self.operator_note,
        }


def validate_apply_args(
    *,
    apply: bool,
    sqlite_db: Path | None,
    deal_key: str | None,
    understand_writes: bool,
) -> str | None:
    if not apply:
        return None
    if sqlite_db is None:
        return "--apply requires --sqlite-db PATH"
    if not deal_key:
        return "--apply requires --deal-key"
    if not understand_writes:
        return "--apply requires --i-understand-this-writes-sqlite"
    return None


def parse_margin_notes(margin_notes: str | None) -> dict[str, Any]:
    if not margin_notes:
        return {}
    try:
        parsed = json.loads(margin_notes)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def margin_pct_from_notes(margin_notes: str | None) -> float | None:
    meta = parse_margin_notes(margin_notes)
    pct = meta.get("margin_pct")
    return float(pct) if pct is not None else None


def _row_dict(cursor: sqlite3.Cursor, row: sqlite3.Row | tuple[Any, ...] | None) -> dict[str, Any]:
    if row is None:
        raise ValueError("row is None")
    if isinstance(row, sqlite3.Row):
        return dict(row)
    names = [d[0] for d in cursor.description or []]
    return dict(zip(names, row))


def _fetch_deal(conn: sqlite3.Connection, deal_key: str) -> dict[str, Any]:
    cur = conn.execute(
        """
        SELECT id, deal_key, client_sale_net_clp, margin_status,
               margin_net_clp, margin_notes, margin_computed_at
        FROM commercial_deal
        WHERE deal_key = ?
        LIMIT 1
        """,
        (deal_key,),
    )
    row = cur.fetchone()
    if row is None:
        raise KeyError(f"deal not found: {deal_key!r}")
    return _row_dict(cur, row)


def _fetch_margin_clp_costs(conn: sqlite3.Connection, deal_id: int) -> dict[str, dict[str, Any]]:
    cur = conn.execute(
        """
        SELECT cost_kind, currency, amount_integer, description, confidence
        FROM commercial_deal_cost
        WHERE deal_id = ? AND currency = 'CLP' AND cost_kind IN (
          'fx_spread', 'logistics_dhl', 'logistics_import', 'bank_fee'
        )
        """,
        (deal_id,),
    )
    by_kind: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        d = _row_dict(cur, row)
        by_kind[str(d["cost_kind"])] = d
    return by_kind


def _kind_to_slot(cost_kind: str) -> str | None:
    for slot, kind in COST_SLOT_TO_KIND.items():
        if kind == cost_kind:
            return slot
    return None


def _slot_values_from_db(
    costs_by_kind: dict[str, dict[str, Any]],
) -> dict[str, int | None]:
    slots: dict[str, int | None] = {slot: None for slot in COST_SLOT_TO_KIND}
    for kind, row in costs_by_kind.items():
        slot = _kind_to_slot(kind)
        if slot is None:
            continue
        amt = row.get("amount_integer")
        if amt is not None and row.get("confidence") == "operator_confirmed":
            slots[slot] = int(amt)
    return slots


def _validate_zero_requires_note(slot: str, amount: int, note: str | None) -> str | None:
    if amount != 0:
        return None
    if note and note.strip():
        return None
    return (
        f"{slot}: amount 0 requires --note explaining why "
        "(e.g. DHL account / no import duty)"
    )


def _build_cost_row(
    *,
    deal_key: str,
    slot: str,
    amount: int,
    note: str | None,
    ts: str,
) -> dict[str, Any]:
    kind = COST_SLOT_TO_KIND[slot]
    desc = _SLOT_DESCRIPTIONS[slot]
    if amount == 0 and note:
        desc = f"{desc} — zero confirmed. {note.strip()}"
    elif note and note.strip():
        desc = f"{desc}. {note.strip()}"
    return {
        "deal_key": deal_key,
        "cost_kind": kind,
        "description": desc,
        "currency": "CLP",
        "amount_integer": amount,
        "confidence": "operator_confirmed",
        "is_estimated": 0,
        "excluded_from_supplier_wire": 0,
        "created_at": ts,
        "updated_at": ts,
    }


def _merged_slot_values(
    db_slots: dict[str, int | None],
    inputs: MarginCostInputs,
) -> dict[str, int | None]:
    merged = dict(db_slots)
    for slot, value in inputs.provided_slots().items():
        merged[slot] = value
    return merged


def remaining_margin_blockers(
    merged_slots: dict[str, int | None],
    *,
    note: str | None = None,
) -> list[str]:
    blockers: list[str] = []
    for slot in REQUIRED_MARGIN_SLOTS:
        value = merged_slots.get(slot)
        if value is None:
            blockers.append(f"Missing confirmed {slot} ({_SLOT_DESCRIPTIONS[slot]})")
            continue
        err = _validate_zero_requires_note(slot, value, note)
        if err:
            blockers.append(err)
    return blockers


def compute_margin(
    client_sale_net_clp: int | None,
    merged_slots: dict[str, int | None],
    *,
    note: str | None = None,
) -> tuple[str, int | None, float | None, int | None, list[str]]:
    """Return (margin_status, margin_net_clp, margin_pct, clp_cost_total, blockers)."""
    blockers = remaining_margin_blockers(merged_slots, note=note)
    if blockers:
        return "needs_review", None, None, None, blockers
    if client_sale_net_clp is None or client_sale_net_clp <= 0:
        return "needs_review", None, None, None, ["client_sale_net_clp missing or zero"]

    clp_total = sum(
        int(merged_slots[slot])
        for slot in COST_SLOT_TO_KIND
        if merged_slots.get(slot) is not None
    )
    margin_net = client_sale_net_clp - clp_total
    margin_pct = float(
        (Decimal(margin_net) / Decimal(client_sale_net_clp)).quantize(
            Decimal("0.0001"), rounding=ROUND_HALF_UP
        )
    )
    return "computed", margin_net, margin_pct, clp_total, []


def build_margin_update_plan(
    conn: sqlite3.Connection,
    deal_key: str,
    inputs: MarginCostInputs,
    *,
    mode: str = "dry_run",
) -> MarginUpdatePlan:
    deal = _fetch_deal(conn, deal_key)
    deal_id = int(deal["id"])
    costs_by_kind = _fetch_margin_clp_costs(conn, deal_id)
    db_slots = _slot_values_from_db(costs_by_kind)
    merged = _merged_slot_values(db_slots, inputs)
    ts = now_iso()

    cost_rows: list[dict[str, Any]] = []
    for slot, amount in inputs.provided_slots().items():
        err = _validate_zero_requires_note(slot, amount, inputs.note)
        if err:
            raise ValueError(err)
        cost_rows.append(
            _build_cost_row(
                deal_key=deal_key,
                slot=slot,
                amount=amount,
                note=inputs.note,
                ts=ts,
            )
        )

    blockers = remaining_margin_blockers(merged, note=inputs.note)
    ready = len(blockers) == 0
    status, margin_net, margin_pct, clp_total, compute_blockers = compute_margin(
        deal.get("client_sale_net_clp"),
        merged,
        note=inputs.note,
    )
    if compute_blockers:
        blockers = compute_blockers
        ready = False

    return MarginUpdatePlan(
        deal_key=deal_key,
        deal_id=deal_id,
        mode=mode,
        client_sale_net_clp=deal.get("client_sale_net_clp"),
        cost_rows=cost_rows,
        margin_status=status,
        margin_net_clp=margin_net,
        margin_pct=margin_pct,
        clp_cost_total=clp_total,
        remaining_blockers=blockers,
        ready_to_compute=ready,
        operator_note=inputs.note,
    )


def _upsert_margin_cost(conn: sqlite3.Connection, deal_id: int, row: dict[str, Any]) -> str:
    allowed = set(table_column_names(conn, "commercial_deal_cost"))
    cols = {k: v for k, v in row.items() if k in allowed and k != "deal_key"}
    cols["deal_id"] = deal_id
    existing = conn.execute(
        """
        SELECT id FROM commercial_deal_cost
        WHERE deal_id = ? AND cost_kind = ?
        LIMIT 1
        """,
        (deal_id, cols["cost_kind"]),
    ).fetchone()
    if existing is None:
        keys = list(cols.keys())
        conn.execute(
            f"INSERT INTO commercial_deal_cost ({', '.join(keys)}) VALUES ({', '.join('?' * len(keys))})",
            tuple(cols[k] for k in keys),
        )
        return "insert"
    upd = {k: v for k, v in cols.items() if k not in ("deal_id", "cost_kind", "created_at")}
    set_clause = ", ".join(f"{k}=?" for k in upd)
    conn.execute(
        f"UPDATE commercial_deal_cost SET {set_clause} WHERE id=?",
        (*upd.values(), int(existing[0])),
    )
    return "update"


def apply_margin_update_plan(conn: sqlite3.Connection, plan: MarginUpdatePlan) -> dict[str, Any]:
    """Apply cost upserts and margin fields in one transaction."""
    ts = now_iso()
    cost_actions: dict[str, str] = {}
    try:
        conn.execute("BEGIN IMMEDIATE")
        for row in plan.cost_rows:
            action = _upsert_margin_cost(conn, plan.deal_id, row)
            cost_actions[row["cost_kind"]] = action

        margin_notes: str | None = None
        if plan.margin_status == "computed" and plan.margin_net_clp is not None:
            margin_notes = json.dumps(
                {
                    "margin_pct": plan.margin_pct,
                    "clp_cost_total": plan.clp_cost_total,
                    "basis": "client_sale_net_clp",
                    "operator_note": plan.operator_note,
                },
                ensure_ascii=False,
            )
            conn.execute(
                """
                UPDATE commercial_deal SET
                  margin_status = ?,
                  margin_net_clp = ?,
                  margin_computed_at = ?,
                  margin_notes = ?,
                  updated_at = ?
                WHERE id = ?
                """,
                (
                    "computed",
                    plan.margin_net_clp,
                    ts,
                    margin_notes,
                    ts,
                    plan.deal_id,
                ),
            )
        else:
            conn.execute(
                """
                UPDATE commercial_deal SET
                  margin_status = ?,
                  margin_net_clp = NULL,
                  margin_computed_at = NULL,
                  updated_at = ?
                WHERE id = ?
                """,
                ("needs_review", ts, plan.deal_id),
            )

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return {
        "deal_key": plan.deal_key,
        "deal_id": plan.deal_id,
        "margin_status": plan.margin_status,
        "margin_net_clp": plan.margin_net_clp,
        "margin_pct": plan.margin_pct,
        "clp_cost_total": plan.clp_cost_total,
        "cost_actions": cost_actions,
        "remaining_blockers": plan.remaining_blockers,
    }


def margin_blockers_for_deal(conn: sqlite3.Connection, deal_key: str) -> list[str]:
    deal = _fetch_deal(conn, deal_key)
    costs_by_kind = _fetch_margin_clp_costs(conn, int(deal["id"]))
    merged = _slot_values_from_db(costs_by_kind)
    return remaining_margin_blockers(merged)


def build_and_apply_margin_update(
    db_path: Path,
    deal_key: str,
    inputs: MarginCostInputs,
) -> dict[str, Any]:
    path_err = validate_sqlite_apply_target(db_path)
    if path_err:
        raise ValueError(path_err)
    conn = connect_sqlite_rw(db_path)
    try:
        plan = build_margin_update_plan(conn, deal_key, inputs, mode="apply")
        return apply_margin_update_plan(conn, plan)
    finally:
        conn.close()
