"""Equipment-first opportunity queue from ChileCompra Licitacion_Publicada.csv."""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

# User-requested deprioritization (consumables / reagents; not equipment-first).
STOP_CONSUMABLES_OUTREACH_CODES: frozenset[str] = frozenset(
    {
        "1497-6-LE26",
        "1497-3-LE26",
        "1657-8-LE26",
        "1511-30-LP26",
    }
)

CSV_HEADER_MARKER = "Textbox36"
CSV_COLUMNS = (
    "codigo",
    "tipo_licitacion",
    "title",
    "descripcion",
    "buyer",
    "region",
    "fecha_publicacion",
    "close_date",
    "line_description",
    "unspsc_code",
    "unidad",
    "cantidad",
    "producto",
    "nivel_1",
    "nivel_2",
    "nivel_3",
)

EQUIPMENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "centrifuge",
        re.compile(
            r"centr[ií]fug|microcentr[ií]fug|citocentr[ií]fug|"
            r"centr[ií]fuga\s+refrigerad|refrigerated\s+centrif",
            re.I,
        ),
    ),
    ("balance", re.compile(r"\bbalanza\b", re.I)),
    (
        "sonicator",
        re.compile(
            r"\b(sonicador|sonificador|lavadora\s+ultras[oó]nic)\b",
            re.I,
        ),
    ),
    (
        "homogenizer",
        re.compile(
            r"homogeneizador|dispersor|ultra\s*turrax|turax|"
            r"\bagitador\b|\bvortex\b",
            re.I,
        ),
    ),
    (
        "incubator",
        re.compile(r"\bincubadora\b|ba[nñ]o\s+termorregulad", re.I),
    ),
    ("osmometer", re.compile(r"osm[oó]metr", re.I)),
    # lab_ultrasonic_processor detected via LAB_ULTRASONIC_RE in detect_equipment_categories
)

EXCLUDE_CONSUMABLES_RE = re.compile(
    r"reactivos?|insumos?\s+microbiol[oó]gic|placas?\s+petri|"
    r"\bguantes\b|detergentes?|est[aá]ndares?|medios?\s+de\s+cultivo|"
    r"\batcc\b|\bvidas\b|\bapi\s+\d|colilert|"
    r"\b[aá]cidos?\b|solventes?|material\s+de\s+referencia|"
    r"\btubos?\b|\bbolsas?\b|\bfiltros?\b|consumibles?",
    re.I,
)

NON_LAB_CENTRIFUGE_RE = re.compile(
    r"\b(pozo|sumergible|sala\s+de\s+bombas|fluidos|industrial)\b",
    re.I,
)
CONSUMABLE_CENTRIFUGE_TUBE_RE = re.compile(
    r"\btubos?\s+(de\s+|para\s+)?(micro)?centr[ií]fug|"
    r"\btubos?\s+conic[oa]s?\s+para\s+centr[ií]fug|"
    r"\btubos?\s+centr[ií]fug|"
    r"centr[ií]fug.*\btubos?\b",
    re.I,
)
CONSUMABLE_AGITATOR_RE = re.compile(
    r"agitador.*\breactivo\b|\breactivo\b.*agitador|"
    r"agitador\s+magn[eé]tic",
    re.I,
)
REAL_CENTRIFUGE_EQUIPMENT_RE = re.compile(
    r"centr[ií]fug(a|adora|adoras|as)\s+(para|de\s+laboratorio|\bcl[ií]nic|"
    r"refrigerad|umt)|manten(ci|ció)n.*centr[ií]fug|"
    r"adquisici[oó]n\s+de\s+centr[ií]fug|equipos?\s+umt|"
    r"bombas?\s+centr[ií]fugas?\s+de\s+laboratorio",
    re.I,
)
CLINICAL_ULTRASOUND_RE = re.compile(
    r"ec[oó]graf|ultrasonograf|gel\s+ultrasonido|eco\s*fundas?|"
    r"punta\s+ultrasonido|cat[eé]ter.*ultrasonido|paqu[ií]metr|"
    r"examen(es)?\s+de\s+ecograf",
    re.I,
)
LAB_ULTRASONIC_RE = re.compile(
    r"sonicador|sonificador|lavadora\s+ultras[oó]nic|"
    r"procesador\s+ultras[oó]nic|homogenizador\s+ultras[oó]nic",
    re.I,
)
NON_LAB_BALANCE_RE = re.compile(
    r"parvulario|did[aá]ctic|3\s+toneladas?|peso\s+control|"
    r"vehiculos?\s+equipamiento|hidrolavadora",
    re.I,
)
LAB_BALANCE_RE = re.compile(
    r"balanza\s+anal[ií]tic|balanza\s+de\s+precisi[oó]n|balanza\s+electr[oó]nic|"
    r"0[,.]0+\s*mg|laboratorio.*balanza|balanza.*laboratorio|"
    r"manten(ci|ció)n.*balanza|certificaci[oó]n.*balanza",
    re.I,
)
CONSUMABLE_INCUBATOR_RE = re.compile(
    r"regilla\s+para\s+incubadora|cubre\s+incubadora|"
    r"indicador\s+biol[oó]gico.*incubadora|manga.*incubadora|"
    r"compatible\s+con\s+incubadora\s+attest",
    re.I,
)
NEONATAL_INCUBATOR_RE = re.compile(
    r"incubadora\s+de\s+transporte|neonatolog|modelo\s+giraffe|"
    r"giraffe\.|incubadora\s*,\s*refrigerador",
    re.I,
)
LAB_INCUBATOR_RE = re.compile(
    r"incubadora(?!\s+de\s+transporte)|estufa\s+de\s+incubaci[oó]n",
    re.I,
)
LAB_CONTEXT_RE = re.compile(
    r"\blaboratorio\b|\blaborator\b|\bcl[ií]nica\b|\bcl[ií]nico\b|"
    r"hematolog|microbiol|bioqu[ií]mic|anal[ií]t|diagn[oó]st",
    re.I,
)
MAINTENANCE_RE = re.compile(r"manten(ci|ció)n|mantencion", re.I)
ARRIENDO_RE = re.compile(r"\barriendo\b", re.I)
CONVENIO_REACTIVOS_RE = re.compile(
    r"convenio.*reactivo|reactivo.*comodato|insumos.*comodato",
    re.I,
)


def _strip_accents(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def line_blob(row: dict[str, str]) -> str:
    parts = [
        row.get("title", ""),
        row.get("descripcion", ""),
        row.get("line_description", ""),
        row.get("producto", ""),
        row.get("nivel_1", ""),
        row.get("nivel_2", ""),
        row.get("nivel_3", ""),
    ]
    return " | ".join(p for p in parts if p.strip())


def detect_equipment_categories(blob: str) -> list[tuple[str, str]]:
    """Return (category, matched_span) for equipment hits in blob."""
    text = blob
    hits: list[tuple[str, str]] = []
    for category, pattern in EQUIPMENT_RULES:
        m = pattern.search(text)
        if not m:
            continue
        if category == "centrifuge":
            if NON_LAB_CENTRIFUGE_RE.search(text) and not LAB_CONTEXT_RE.search(text):
                continue
            if CONSUMABLE_CENTRIFUGE_TUBE_RE.search(text) and not REAL_CENTRIFUGE_EQUIPMENT_RE.search(
                text
            ):
                continue
        if category == "balance":
            if NON_LAB_BALANCE_RE.search(text):
                continue
            if not (LAB_BALANCE_RE.search(text) or LAB_CONTEXT_RE.search(text)):
                continue
        if category == "homogenizer" and CONSUMABLE_AGITATOR_RE.search(text):
            continue
        if category == "incubator":
            if CONSUMABLE_INCUBATOR_RE.search(text) and not re.search(
                r"estufa\s+de\s+incubaci[oó]n",
                text,
                re.I,
            ):
                continue
            if NEONATAL_INCUBATOR_RE.search(text):
                continue
        hits.append((category, m.group(0)[:80]))

    if LAB_ULTRASONIC_RE.search(text) and not CLINICAL_ULTRASOUND_RE.search(text):
        m = LAB_ULTRASONIC_RE.search(text)
        if m:
            hits.append(("lab_ultrasonic_processor", m.group(0)[:80]))
    return hits


def consumables_exclusion_reason(blob: str) -> str | None:
    m = EXCLUDE_CONSUMABLES_RE.search(blob)
    return m.group(0) if m else None


def parse_close_date(raw: str) -> datetime | None:
    raw = (raw or "").strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None


@dataclass
class TenderAccumulator:
    codigo: str
    buyer: str = ""
    region: str = ""
    close_date: str = ""
    title: str = ""
    categories: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    has_equipment_line: bool = False
    has_consumable_line: bool = False
    maintenance_signal: bool = False
    arriendo_signal: bool = False
    convenio_reactivos: bool = False

    def add_line(self, row: dict[str, str], blob: str) -> None:
        if not self.buyer:
            self.buyer = row.get("buyer", "")
            self.region = row.get("region", "")
            self.close_date = row.get("close_date", "")
            self.title = row.get("title", "")
        elif not self.close_date and (row.get("close_date") or "").strip():
            self.close_date = row.get("close_date", "")
        for cat, span in detect_equipment_categories(blob):
            self.has_equipment_line = True
            desc = row.get("line_description") or row.get("producto") or span
            if desc and desc not in self.categories[cat]:
                self.categories[cat].append(desc[:240])
        if consumables_exclusion_reason(blob):
            self.has_consumable_line = True
        if MAINTENANCE_RE.search(blob):
            self.maintenance_signal = True
        if ARRIENDO_RE.search(blob):
            self.arriendo_signal = True
        if CONVENIO_REACTIVOS_RE.search(blob):
            self.convenio_reactivos = True


def iter_licitacion_publicada_rows(csv_path: Path) -> Iterator[dict[str, str]]:
    with csv_path.open(newline="", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.reader(f)
        header: list[str] | None = None
        for raw in reader:
            if not raw:
                continue
            if raw[0] == CSV_HEADER_MARKER:
                header = raw
                continue
            if header is None or raw[0] == "Textbox69":
                continue
            if len(raw) < len(CSV_COLUMNS):
                raw = raw + [""] * (len(CSV_COLUMNS) - len(raw))
            data = dict(zip(CSV_COLUMNS, raw[: len(CSV_COLUMNS)], strict=False))
            yield data


def _fit_score(
    *,
    codigo: str,
    category: str,
    close_dt: datetime | None,
    maintenance: bool,
    arriendo: bool,
    convenio_reactivos: bool,
    now: datetime,
) -> int:
    score = 50
    if codigo in STOP_CONSUMABLES_OUTREACH_CODES:
        return 5
    high_ticket = {
        "centrifuge",
        "balance",
        "sonicator",
        "homogenizer",
        "osmometer",
        "lab_ultrasonic_processor",
    }
    if category in high_ticket:
        score += 25
    if maintenance and category == "centrifuge":
        score += 15
    if close_dt:
        days = (close_dt - now).days
        if days < 0:
            score -= 20
        elif days <= 7:
            score += 20
        elif days <= 21:
            score += 10
    if arriendo:
        score -= 15
    if convenio_reactivos:
        score -= 25
    return max(0, min(100, score))


def classify_next_action(
    *,
    codigo: str,
    category: str,
    close_dt: datetime | None,
    maintenance: bool,
    arriendo: bool,
    convenio_reactivos: bool,
    now: datetime,
) -> str:
    if codigo in STOP_CONSUMABLES_OUTREACH_CODES:
        return "skip_consumables"
    if close_dt and (close_dt - now).days < 0:
        return "contact_after_close"
    if convenio_reactivos and category not in ("centrifuge", "balance", "sonicator"):
        return "account_intelligence_only"
    if arriendo:
        return "account_intelligence_only"
    if maintenance:
        return "needs_supplier_quote"
    if category in ("centrifuge", "balance", "sonicator", "osmometer", "homogenizer"):
        if close_dt and (close_dt - now).days <= 21:
            return "quote_now"
        return "needs_supplier_quote"
    if close_dt and (close_dt - now).days <= 14:
        return "needs_supplier_quote"
    return "account_intelligence_only"


def build_equipment_queue_rows_from_normalized_rows(
    rows: Iterable[dict[str, str]],
    *,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    """Build equipment queue rows from normalized licitación line dicts (CSV or API)."""
    now = now or datetime.now()
    tenders: dict[str, TenderAccumulator] = {}

    for row in rows:
        codigo = (row.get("codigo") or "").strip()
        if not codigo:
            continue
        blob = line_blob(row)
        acc = tenders.get(codigo)
        if acc is None:
            acc = TenderAccumulator(codigo=codigo)
            tenders[codigo] = acc
        acc.add_line(row, blob)

    out: list[dict[str, str]] = []
    for acc in tenders.values():
        if not acc.has_equipment_line:
            continue
        if acc.codigo in STOP_CONSUMABLES_OUTREACH_CODES:
            tender_blob = f"{acc.title} {' '.join(sum(acc.categories.values(), []))}"
            if not REAL_CENTRIFUGE_EQUIPMENT_RE.search(tender_blob) and not re.search(
                r"\b(sonicador|sonificador|osm[oó]metr|ultra\s*turrax)\b",
                tender_blob,
                re.I,
            ):
                continue
        close_dt = parse_close_date(acc.close_date)
        for category, descriptions in sorted(acc.categories.items()):
            item_desc = " ; ".join(descriptions[:4])
            if len(descriptions) > 4:
                item_desc += f" (+{len(descriptions) - 4} líneas)"
            reason_parts = [f"equipment:{category}"]
            if acc.has_consumable_line:
                reason_parts.append("also_has_consumable_lines")
            if acc.maintenance_signal:
                reason_parts.append("maintenance_context")
            if acc.convenio_reactivos:
                reason_parts.append("convenio_reactivos_context")
            if acc.codigo in STOP_CONSUMABLES_OUTREACH_CODES:
                reason_parts.append("deprioritized_consumables_tender")

            next_action = classify_next_action(
                codigo=acc.codigo,
                category=category,
                close_dt=close_dt,
                maintenance=acc.maintenance_signal,
                arriendo=acc.arriendo_signal,
                convenio_reactivos=acc.convenio_reactivos,
                now=now,
            )
            score = _fit_score(
                codigo=acc.codigo,
                category=category,
                close_dt=close_dt,
                maintenance=acc.maintenance_signal,
                arriendo=acc.arriendo_signal,
                convenio_reactivos=acc.convenio_reactivos,
                now=now,
            )
            out.append(
                {
                    "codigo_licitacion": acc.codigo,
                    "buyer": acc.buyer,
                    "region": acc.region.strip(),
                    "close_date": acc.close_date,
                    "title": acc.title[:300],
                    "item_description": item_desc[:500],
                    "equipment_category": category,
                    "fit_score": str(score),
                    "reason": "; ".join(reason_parts),
                    "next_action": next_action,
                }
            )

    out.sort(
        key=lambda r: (
            r["next_action"] == "skip_consumables",
            -int(r["fit_score"]),
            r["close_date"],
        )
    )
    return out


def build_equipment_queue_rows(
    csv_path: Path,
    *,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    return build_equipment_queue_rows_from_normalized_rows(
        iter_licitacion_publicada_rows(csv_path),
        now=now,
    )


def write_equipment_queue_csv(rows: list[dict[str, str]], out_path: Path) -> None:
    fieldnames = [
        "codigo_licitacion",
        "buyer",
        "region",
        "close_date",
        "title",
        "item_description",
        "equipment_category",
        "fit_score",
        "reason",
        "next_action",
    ]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)


def build_from_csv(csv_path: Path, out_path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    rows = build_equipment_queue_rows(csv_path, now=now)
    write_equipment_queue_csv(rows, out_path)
    actions: dict[str, int] = defaultdict(int)
    for r in rows:
        actions[r["next_action"]] += 1
    return {
        "rows": len(rows),
        "tenders": len({r["codigo_licitacion"] for r in rows}),
        "by_next_action": dict(actions),
    }
