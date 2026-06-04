"""Characterization tests for legacy 2016–2019 contact workbook review pipeline."""

from __future__ import annotations

import ast
import csv
import inspect
import json
import sqlite3
from pathlib import Path

import pytest

from origenlab_email_pipeline.contact_domain_suppression import ensure_contact_domain_suppression_table
from origenlab_email_pipeline.contact_email_suppression import ensure_contact_email_suppression_table
from origenlab_email_pipeline.lead_research import legacy_contacts_2016_2019 as legacy_mod
from origenlab_email_pipeline.lead_research.legacy_contacts_2016_2019 import (
    BATCH_KEY_LEGACY,
    CLASSIFICATION_LEGACY,
    DATASET_LABEL_LEGACY,
    DEFAULT_SUGGESTED_ACTION,
    REVIEW_OUTPUT_COLUMNS,
    SOURCE_NAME_LEGACY,
    SOURCE_TYPE_LEGACY,
    STATUS_ALREADY_CONTACTED_EXACT,
    STATUS_BOUNCED_SUPPRESSED,
    STATUS_DOMAIN_HAS_HISTORY,
    STATUS_DUP_DOMAIN_SECONDARY,
    STATUS_DUP_EMAIL,
    STATUS_GENERIC_ORG,
    STATUS_INVALID_EMAIL,
    STATUS_LIKELY_PERSONAL,
    STATUS_NO_EMAIL,
    STATUS_POSSIBLE_BUYER,
    STATUS_REVIEW_LEGACY,
    STATUS_SUPPLIER_VENDOR,
    LegacyNormalizedRow,
    LegacyRawRow,
    LegacyReviewBuildResult,
    LegacySafetyContext,
    WorkbookInspection,
    apply_duplicate_labels,
    bucket_legacy_rows,
    build_summary,
    classify_legacy_rows,
    legacy_row_to_lead_research_payload,
    load_legacy_safety_context,
    merge_legacy_possible_buyers_to_lead_research,
    normalize_legacy_raw_rows,
    split_emails_from_cell,
    summary_markdown,
    write_legacy_review_outputs,
)
from origenlab_email_pipeline.lead_research.lead_research_schema import ensure_lead_research_tables
from origenlab_email_pipeline.leads.new_customer_research import load_exclusion_lists

_MODULE_PATH = Path(inspect.getfile(legacy_mod))
_EXPECTED_REVIEW_COLUMNS: tuple[str, ...] = (
    "email",
    "domain",
    "organization",
    "contact_name",
    "phone",
    "region",
    "source_sheet",
    "source_row",
    "original_notes",
    "normalized_status",
    "safety_reason",
    "suggested_action",
    "product_angle",
    "confidence",
)


def _excl_dir(tmp_path: Path, *, extra_domain_lines: str = "") -> Path:
    d = tmp_path / "excl"
    d.mkdir()
    (d / "contacted_exact_emails_for_exclusion.csv").write_text(
        "normalized_email\nknown@labcliente.cl\n",
        encoding="utf-8",
    )
    domain_body = (
        "domain,sent_count,recommended_status,supplier_bool,internal_bool,reason_codes\n"
        "historico.cl,2,already_contacted,false,false,\n"
        f"{extra_domain_lines}"
    )
    (d / "contacted_domains_for_exclusion.csv").write_text(domain_body, encoding="utf-8")
    (d / "bounced_emails_for_exclusion.csv").write_text(
        "normalized_email\nbounced@rebote.cl\n",
        encoding="utf-8",
    )
    (d / "suppressed_contacts_for_exclusion.csv").write_text(
        "normalized_email\nsuppressed@hold.cl\n",
        encoding="utf-8",
    )
    return d


def _ctx_from_excl_dir(tmp_path: Path, *, extra_domain_lines: str = "") -> LegacySafetyContext:
    excl = load_exclusion_lists(_excl_dir(tmp_path, extra_domain_lines=extra_domain_lines))
    return LegacySafetyContext(
        exclusion=excl,
        sqlite_suppressed_emails=frozenset(),
        sqlite_suppressed_domains=frozenset(),
        gmail_sent_emails=frozenset(),
        lead_research_emails=frozenset(),
        lead_research_domains=frozenset(),
        supplier_domains_sqlite=frozenset(),
    )


def _norm_row(
    email: str,
    *,
    domain: str = "",
    organization: str = "Org",
    normalized_status: str = "",
) -> LegacyNormalizedRow:
    dom = domain or (email.split("@", 1)[-1] if "@" in email else "")
    return LegacyNormalizedRow(
        email=email,
        domain=dom,
        organization=organization,
        contact_name="",
        phone="",
        region="",
        source_sheet="S",
        source_row=1,
        original_notes="",
        product_angle="",
        category="",
        normalized_status=normalized_status,
    )


def _classify_emails(tmp_path: Path, emails: list[str], **excl_kw: str) -> dict[str, str]:
    raw = [LegacyRawRow("S", i + 2, {"Correo": em, "Empresa ": "L"}) for i, em in enumerate(emails)]
    rows = normalize_legacy_raw_rows(raw)
    classify_legacy_rows(rows, _ctx_from_excl_dir(tmp_path, **excl_kw))
    return {r.email: r.normalized_status for r in rows}


def _sqlite_safety_db(tmp_path: Path) -> sqlite3.Connection:
    db = tmp_path / "safety.sqlite"
    conn = sqlite3.connect(db)
    ensure_contact_email_suppression_table(conn)
    ensure_contact_domain_suppression_table(conn)
    ensure_lead_research_tables(conn)
    conn.execute(
        "INSERT INTO contact_email_suppression (email, suppression_reason_code, updated_at) VALUES (?,?,?)",
        ("sqlite@sup.cl", "bounce", "2026-01-01T00:00:00"),
    )
    conn.execute(
        """
        INSERT INTO contact_domain_suppression (domain_norm, suppression_reason_text, updated_at)
        VALUES (?,?,?)
        """,
        ("suppressed-dom.cl", "operator", "2026-01-01T00:00:00"),
    )
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS supplier_master (
          domain_norm TEXT PRIMARY KEY
        );
        INSERT INTO supplier_master (domain_norm) VALUES ('sqlite-supplier.cl');
        """
    )
    conn.execute(
        """
        INSERT INTO lead_research_batch (batch_key, source_name, row_count, created_at)
        VALUES (?,?,?,?)
        """,
        ("other_batch", "test", 0, "2026-01-01T00:00:00"),
    )
    batch_id = conn.execute("SELECT id FROM lead_research_batch").fetchone()[0]
    conn.execute(
        """
        INSERT INTO lead_research_prospect (
          batch_id, prospect_key, organization_name, email, domain,
          classification, status, source_type, dataset_label, is_active, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            batch_id,
            "existing|lr@known.cl|known.cl",
            "Known Org",
            "lr@known.cl",
            "known.cl",
            "legacy_contact_review",
            "review_legacy_contact",
            "legacy_2016_2019",
            DATASET_LABEL_LEGACY,
            1,
            "2026-01-01T00:00:00",
        ),
    )
    conn.commit()
    return conn


# --- 1. Public constants / column contract ---


def test_review_output_columns_exact_order() -> None:
    assert REVIEW_OUTPUT_COLUMNS == _EXPECTED_REVIEW_COLUMNS
    assert tuple(REVIEW_OUTPUT_COLUMNS) is REVIEW_OUTPUT_COLUMNS


def test_legacy_source_constants_stable() -> None:
    assert SOURCE_TYPE_LEGACY == "legacy_2016_2019"
    assert BATCH_KEY_LEGACY == "legacy_contacts_2016_2019"
    assert SOURCE_NAME_LEGACY == "legacy_contacts_2016_2019_import"
    assert DATASET_LABEL_LEGACY == "Base de datos 2016–2019"
    assert STATUS_REVIEW_LEGACY == "review_legacy_contact"
    assert CLASSIFICATION_LEGACY == "legacy_contact_review"
    assert DEFAULT_SUGGESTED_ACTION == "review_legacy_contact"


def test_status_constants_stable_and_never_net_new_safe() -> None:
    status_names = [
        name
        for name, value in vars(legacy_mod).items()
        if name.startswith("STATUS_") and isinstance(value, str)
    ]
    assert len(status_names) >= 10
    values = {getattr(legacy_mod, name) for name in status_names}
    for value in values:
        assert "net_new_safe" not in value
        assert value != "net_new_safe_review"
    assert CLASSIFICATION_LEGACY not in values
    assert "net_new_safe" not in CLASSIFICATION_LEGACY


# --- 2. Dataclass defaults / markdown summary ---


def test_legacy_normalized_row_defaults() -> None:
    row = LegacyNormalizedRow(
        email="x@y.cl",
        domain="y.cl",
        organization="O",
        contact_name="",
        phone="",
        region="",
        source_sheet="S",
        source_row=1,
        original_notes="",
        product_angle="",
        category="",
    )
    assert row.source_type == SOURCE_TYPE_LEGACY
    assert row.dataset_label == DATASET_LABEL_LEGACY
    assert row.suggested_action == DEFAULT_SUGGESTED_ACTION
    assert row.confidence == "baja"


def test_workbook_inspection_markdown_empty() -> None:
    md = WorkbookInspection(path="fixture.xls").to_markdown()
    assert md.startswith("# Legacy contacts 2016–2019 — workbook inspection")
    assert "**Path:** `fixture.xls`" in md
    assert "**Sheets:** 0" in md
    assert "Inferred mapping" not in md


def test_workbook_inspection_markdown_includes_inferred_mapping() -> None:
    inspection = WorkbookInspection(
        path="workbook.xls",
        sheets=[
            {
                "name": "Hoja1",
                "row_count": 3,
                "columns": ["Correo", "Empresa"],
                "inferred_mapping": {"email": "Correo", "organization": "Empresa"},
                "sample_rows": [],
            }
        ],
    )
    md = inspection.to_markdown()
    assert "## Hoja1" in md
    assert "Inferred mapping:" in md
    assert "`email` ← `Correo`" in md
    assert "`organization` ← `Empresa`" in md


# --- 3. Header / alias normalization ---


def test_normalize_spanish_headers() -> None:
    raw = [
        LegacyRawRow(
            "Hoja1",
            2,
            {
                "Correo": "lab@empresa.cl",
                "Empresa": "Laboratorio Norte",
                "Contacto": "María",
                "Teléfono": "+56 9 1111 2222",
                "Dirección": "Región Metropolitana",
                "Observación": "Cliente antiguo",
                "Producto": "termobalanza",
            },
        )
    ]
    rows = normalize_legacy_raw_rows(raw)
    assert len(rows) == 1
    row = rows[0]
    assert row.email == "lab@empresa.cl"
    assert row.organization == "Laboratorio Norte"
    assert row.contact_name == "María"
    assert row.phone == "+56 9 1111 2222"
    assert row.region == "Región Metropolitana"
    assert "Cliente antiguo" in row.original_notes
    assert row.product_angle == "termobalanza"


def test_normalize_header_alias_variants() -> None:
    raw = [
        LegacyRawRow(
            "Aliases",
            3,
            {
                "e-mail": "alias@institucion.cl",
                "organización": "Instituto Alias",
                "institucion": "ignored-if-org-mapped",
                "Contacto": "Pedro",
                "celular": "2222",
                "interés": "microscopio",
            },
        )
    ]
    rows = normalize_legacy_raw_rows(raw)
    assert rows[0].email == "alias@institucion.cl"
    assert rows[0].organization == "Instituto Alias"
    assert rows[0].contact_name == "Pedro"
    assert rows[0].phone == "2222"
    assert rows[0].product_angle == "microscopio"


# --- 4. Email parsing edges ---


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("a@x.cl; ventas@y.cl / info@z.com", ["a@x.cl", "ventas@y.cl", "info@z.com"]),
        ("A@X.CL, b@y.cl", ["a@x.cl", "b@y.cl"]),
        ("one@a.cl|two@b.cl", ["one@a.cl", "two@b.cl"]),
        ("dup@z.cl dup@z.cl", ["dup@z.cl"]),
        ("  spaced@a.cl   more@b.cl  ", ["spaced@a.cl", "more@b.cl"]),
    ],
)
def test_split_emails_from_cell_delimiters_and_case(cell: str, expected: list[str]) -> None:
    assert split_emails_from_cell(cell) == expected


def test_normalize_expands_multiple_emails_per_row() -> None:
    raw = [LegacyRawRow("S", 2, {"Correo": "a@x.cl; b@y.cl", "Empresa": "L"})]
    rows = normalize_legacy_raw_rows(raw)
    assert [r.email for r in rows] == ["a@x.cl", "b@y.cl"]


def test_empty_email_cell_classified_no_email(tmp_path: Path) -> None:
    raw = [LegacyRawRow("S", 2, {"Correo": "", "Empresa": "Sin correo"})]
    rows = normalize_legacy_raw_rows(raw)
    assert rows[0].normalized_status == STATUS_NO_EMAIL
    classify_legacy_rows(rows, _ctx_from_excl_dir(tmp_path))
    assert rows[0].normalized_status == STATUS_NO_EMAIL


def test_invalid_email_classified(tmp_path: Path) -> None:
    rows = [_norm_row("notld@nodomain", domain="nodomain")]
    classify_legacy_rows(rows, _ctx_from_excl_dir(tmp_path))
    assert rows[0].normalized_status == STATUS_INVALID_EMAIL


# --- 5. Classification precedence ---


def test_contacted_exact_beats_possible_buyer(tmp_path: Path) -> None:
    by = _classify_emails(tmp_path, ["known@labcliente.cl", "fresh@nuevo-lab.cl"])
    assert by["known@labcliente.cl"] == STATUS_ALREADY_CONTACTED_EXACT
    assert by["fresh@nuevo-lab.cl"] == STATUS_POSSIBLE_BUYER


def test_bounced_suppressed_beats_possible_buyer(tmp_path: Path) -> None:
    by = _classify_emails(tmp_path, ["bounced@rebote.cl", "fresh@nuevo-lab.cl"])
    assert by["bounced@rebote.cl"] == STATUS_BOUNCED_SUPPRESSED
    assert by["fresh@nuevo-lab.cl"] == STATUS_POSSIBLE_BUYER


def test_supplier_vendor_domain_classification(tmp_path: Path) -> None:
    extra = "proveedor.cl,0,,true,false,\n"
    by = _classify_emails(tmp_path, ["ventas@proveedor.cl"], extra_domain_lines=extra)
    assert by["ventas@proveedor.cl"] == STATUS_SUPPLIER_VENDOR


def test_internal_domain_origenlab_is_supplier_vendor(tmp_path: Path) -> None:
    by = _classify_emails(tmp_path, ["ops@origenlab.cl"])
    assert by["ops@origenlab.cl"] == STATUS_SUPPLIER_VENDOR


def test_likely_personal_email_domain(tmp_path: Path) -> None:
    by = _classify_emails(tmp_path, ["ana.personal@gmail.com"])
    assert by["ana.personal@gmail.com"] == STATUS_LIKELY_PERSONAL


def test_generic_org_mailbox(tmp_path: Path) -> None:
    by = _classify_emails(tmp_path, ["info@unico-lab-2026.cl"])
    assert by["info@unico-lab-2026.cl"] == STATUS_GENERIC_ORG


def test_domain_has_history_from_exclusion_csv(tmp_path: Path) -> None:
    by = _classify_emails(tmp_path, ["persona@historico.cl"])
    assert by["persona@historico.cl"] == STATUS_DOMAIN_HAS_HISTORY


def test_duplicate_labels_after_possible_buyer_classification() -> None:
    rows = [
        _norm_row("a@dup.cl", normalized_status=STATUS_POSSIBLE_BUYER),
        _norm_row("b@dup.cl", normalized_status=STATUS_POSSIBLE_BUYER),
        _norm_row("a@dup.cl", normalized_status=STATUS_POSSIBLE_BUYER, organization="C"),
    ]
    apply_duplicate_labels(rows)
    assert rows[0].normalized_status == STATUS_POSSIBLE_BUYER
    assert rows[1].normalized_status == STATUS_DUP_DOMAIN_SECONDARY
    assert rows[2].normalized_status == STATUS_DUP_EMAIL


def test_suppression_and_contacted_matching(tmp_path: Path) -> None:
    raw = [
        LegacyRawRow("S", 2, {"Correo": "known@labcliente.cl", "Empresa ": "L"}),
        LegacyRawRow("S", 3, {"Correo": "bounced@rebote.cl", "Empresa ": "L"}),
        LegacyRawRow("S", 4, {"Correo": "suppressed@hold.cl", "Empresa ": "L"}),
        LegacyRawRow("S", 5, {"Correo": "nuevo@historico.cl", "Empresa ": "L"}),
        LegacyRawRow("S", 6, {"Correo": "fresh@nuevo-lab.cl", "Empresa ": "L", "Contacto": "Ana"}),
    ]
    rows = normalize_legacy_raw_rows(raw)
    classify_legacy_rows(rows, _ctx_from_excl_dir(tmp_path))
    by_email = {r.email: r.normalized_status for r in rows}
    assert by_email["known@labcliente.cl"] == STATUS_ALREADY_CONTACTED_EXACT
    assert by_email["bounced@rebote.cl"] == STATUS_BOUNCED_SUPPRESSED
    assert by_email["suppressed@hold.cl"] == STATUS_BOUNCED_SUPPRESSED
    assert by_email["nuevo@historico.cl"] == STATUS_DOMAIN_HAS_HISTORY
    assert by_email["fresh@nuevo-lab.cl"] == STATUS_POSSIBLE_BUYER


# --- 6. Safety context loading (in-memory SQLite) ---


def test_load_legacy_safety_context_sqlite_suppression(tmp_path: Path) -> None:
    conn = _sqlite_safety_db(tmp_path)
    ctx = load_legacy_safety_context(conn, _excl_dir(tmp_path))
    assert "sqlite@sup.cl" in ctx.sqlite_suppressed_emails
    assert "suppressed-dom.cl" in ctx.sqlite_suppressed_domains
    assert "sqlite-supplier.cl" in ctx.supplier_domains_sqlite
    assert "lr@known.cl" in ctx.lead_research_emails
    assert "known.cl" in ctx.lead_research_domains

    rows = normalize_legacy_raw_rows(
        [
            LegacyRawRow("S", 2, {"Correo": "sqlite@sup.cl", "Empresa ": "L"}),
            LegacyRawRow("S", 3, {"Correo": "x@suppressed-dom.cl", "Empresa ": "L"}),
            LegacyRawRow("S", 4, {"Correo": "buy@sqlite-supplier.cl", "Empresa ": "L"}),
            LegacyRawRow("S", 5, {"Correo": "lr@known.cl", "Empresa ": "L"}),
            LegacyRawRow("S", 6, {"Correo": "other@known.cl", "Empresa ": "L"}),
        ]
    )
    classify_legacy_rows(rows, ctx)
    by = {r.email: r.normalized_status for r in rows}
    assert by["sqlite@sup.cl"] == STATUS_BOUNCED_SUPPRESSED
    assert by["x@suppressed-dom.cl"] == STATUS_DOMAIN_HAS_HISTORY
    assert by["buy@sqlite-supplier.cl"] == STATUS_SUPPLIER_VENDOR
    assert by["lr@known.cl"] == STATUS_ALREADY_CONTACTED_EXACT
    assert by["other@known.cl"] == STATUS_DOMAIN_HAS_HISTORY
    conn.close()


# --- 7. Output CSV contract ---


def _sample_review_result() -> LegacyReviewBuildResult:
    rows = [
        LegacyNormalizedRow(
            email="ok@fresh.cl",
            domain="fresh.cl",
            organization="O",
            contact_name="",
            phone="",
            region="",
            source_sheet="S",
            source_row=1,
            original_notes="",
            product_angle="",
            category="",
            normalized_status=STATUS_POSSIBLE_BUYER,
        ),
        LegacyNormalizedRow(
            email="known@labcliente.cl",
            domain="labcliente.cl",
            organization="K",
            contact_name="",
            phone="",
            region="",
            source_sheet="S",
            source_row=2,
            original_notes="",
            product_angle="",
            category="",
            normalized_status=STATUS_ALREADY_CONTACTED_EXACT,
        ),
        LegacyNormalizedRow(
            email="bounced@rebote.cl",
            domain="rebote.cl",
            organization="B",
            contact_name="",
            phone="",
            region="",
            source_sheet="S",
            source_row=3,
            original_notes="",
            product_angle="",
            category="",
            normalized_status=STATUS_BOUNCED_SUPPRESSED,
        ),
        LegacyNormalizedRow(
            email="",
            domain="",
            organization="X",
            contact_name="",
            phone="",
            region="",
            source_sheet="S",
            source_row=4,
            original_notes="",
            product_angle="",
            category="",
            normalized_status=STATUS_NO_EMAIL,
        ),
    ]
    inspection = WorkbookInspection(path="test.xls", sheets=[])
    buckets = bucket_legacy_rows(rows)
    return LegacyReviewBuildResult(
        inspection=inspection,
        normalized_rows=rows,
        summary=build_summary(inspection, rows, buckets),
        buckets=buckets,
    )


def test_write_legacy_review_outputs_contract(tmp_path: Path) -> None:
    result = _sample_review_result()
    paths = write_legacy_review_outputs(result, tmp_path / "out")
    expected_keys = {
        "all",
        "possible_buyers",
        "already_contacted",
        "bounced_suppressed",
        "invalid_incomplete",
        "domain_duplicates",
        "inspection",
        "summary_md",
        "summary_json",
    }
    assert set(paths) == expected_keys
    for p in paths.values():
        assert p.is_file()

    with paths["all"].open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == list(REVIEW_OUTPUT_COLUMNS)

    with paths["possible_buyers"].open(encoding="utf-8") as f:
        buyers = list(csv.DictReader(f))
    assert {r["email"] for r in buyers} == {"ok@fresh.cl"}
    for row in buyers:
        assert row["normalized_status"] == STATUS_POSSIBLE_BUYER

    summary = json.loads(paths["summary_json"].read_text(encoding="utf-8"))
    assert summary["dataset_label"] == DATASET_LABEL_LEGACY
    assert summary["never_net_new_safe"] is True
    md = paths["summary_md"].read_text(encoding="utf-8")
    assert "2016" in md or DATASET_LABEL_LEGACY in md
    assert "Not send-ready" in md
    assert "Never classified as `net_new_safe`" in md


def test_possible_buyers_csv_excludes_bounced(tmp_path: Path) -> None:
    result = _sample_review_result()
    paths = write_legacy_review_outputs(result, tmp_path / "buyers_only")
    with paths["possible_buyers"].open(encoding="utf-8") as f:
        emails = {r["email"] for r in csv.DictReader(f)}
    assert "ok@fresh.cl" in emails
    assert "bounced@rebote.cl" not in emails


def test_summary_markdown_review_only_disclaimer() -> None:
    result = _sample_review_result()
    md = summary_markdown(result.summary)
    assert "Review-only" in md
    assert "Not send-ready" in md
    assert "`net_new_safe`" in md


# --- 8. Merge dry-run / idempotency ---


def test_merge_dry_run_does_not_insert(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "merge.sqlite")
    ensure_lead_research_tables(conn)
    rows = [_norm_row("merge@fresh.cl", normalized_status=STATUS_POSSIBLE_BUYER)]
    stats = merge_legacy_possible_buyers_to_lead_research(conn, rows, dry_run=True)
    assert stats["dry_run"] is True
    assert stats["inserted"] == 0
    assert stats["candidates"] == 1
    assert conn.execute("SELECT COUNT(*) FROM lead_research_prospect").fetchone()[0] == 0
    conn.close()


def test_merge_skips_non_buyers_and_sets_source_type(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "t.sqlite")
    ensure_lead_research_tables(conn)
    rows = [
        _norm_row("merge@fresh.cl", normalized_status=STATUS_POSSIBLE_BUYER),
        _norm_row("bounced@rebote.cl", normalized_status=STATUS_BOUNCED_SUPPRESSED),
    ]
    stats = merge_legacy_possible_buyers_to_lead_research(conn, rows, dry_run=False)
    assert stats["inserted"] == 1
    row = conn.execute(
        "SELECT source_type, classification, status FROM lead_research_prospect WHERE email = ?",
        ("merge@fresh.cl",),
    ).fetchone()
    assert row[0] == SOURCE_TYPE_LEGACY
    assert row[1] == CLASSIFICATION_LEGACY
    assert row[2] == STATUS_REVIEW_LEGACY
    assert (
        conn.execute(
            "SELECT COUNT(*) FROM lead_research_prospect WHERE classification = 'net_new_safe_review'"
        ).fetchone()[0]
        == 0
    )
    conn.close()


def test_merge_second_run_is_idempotent_by_prospect_key(tmp_path: Path) -> None:
    conn = sqlite3.connect(tmp_path / "idem.sqlite")
    ensure_lead_research_tables(conn)
    rows = [_norm_row("idem@fresh.cl", normalized_status=STATUS_POSSIBLE_BUYER)]
    first = merge_legacy_possible_buyers_to_lead_research(conn, rows, dry_run=False)
    second = merge_legacy_possible_buyers_to_lead_research(conn, rows, dry_run=False)
    assert first["inserted"] == 1
    assert second["inserted"] == 0
    assert second["skipped_existing"] == 1
    assert (
        conn.execute("SELECT COUNT(*) FROM lead_research_prospect WHERE email = ?", ("idem@fresh.cl",)).fetchone()[
            0
        ]
        == 1
    )
    conn.close()


def test_legacy_payload_not_net_new_safe() -> None:
    row = LegacyNormalizedRow(
        email="buyer@fresh-lab.cl",
        domain="fresh-lab.cl",
        organization="Fresh Lab",
        contact_name="Pat",
        phone="",
        region="RM",
        source_sheet="Sheet1",
        source_row=10,
        original_notes="",
        product_angle="termobalanza",
        category="",
        normalized_status=STATUS_POSSIBLE_BUYER,
    )
    payload = legacy_row_to_lead_research_payload(row)
    assert payload is not None
    assert payload["classification"] == CLASSIFICATION_LEGACY
    assert payload["classification"] != "net_new_safe_review"
    assert payload["status"] == STATUS_REVIEW_LEGACY
    assert payload["source_type"] == SOURCE_TYPE_LEGACY
    assert payload["dataset_label"] == DATASET_LABEL_LEGACY
    assert payload["is_blocked"] == 0


# --- 9. Import boundary ---


def test_legacy_module_has_no_streamlit_imports() -> None:
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "streamlit" not in alias.name
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            assert "streamlit" not in mod


def test_legacy_module_has_no_postgres_or_gmail_send_imports() -> None:
    text = _MODULE_PATH.read_text(encoding="utf-8").lower()
    forbidden_substrings = (
        "postgres",
        "psycopg",
        "sqlalchemy",
        "gmail_send",
        "send_email",
        "archive_send_batch_builder",
        "archive_outreach_queue",
    )
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith(("import ", "from ")):
            continue
        lower = stripped.lower()
        for bad in forbidden_substrings:
            assert bad not in lower, f"unexpected import line: {stripped}"


def test_legacy_module_docstring_manual_review_only() -> None:
    doc = legacy_mod.__doc__ or ""
    assert "net_new_safe" in doc or "Never classifies" in doc
    assert "manual" in doc.lower() or "review" in doc.lower()


# --- Optional real workbook (skipped when absent) ---


@pytest.mark.skipif(
    not __import__("importlib").util.find_spec("xlrd"),
    reason="xlrd not installed",
)
def test_read_real_workbook_schema_if_present() -> None:
    path = Path.home() / "data/origenlab-local-assets/legacy-contacts/Base de datos 2016-2019.xls"
    if not path.is_file():
        pytest.skip("legacy workbook not on this machine")
    from origenlab_email_pipeline.lead_research.legacy_contacts_2016_2019 import (
        read_legacy_workbook_xls,
    )

    raw, inspection = read_legacy_workbook_xls(path)
    assert inspection.sheets[0]["row_count"] > 1000
    assert len(raw) > 1000
