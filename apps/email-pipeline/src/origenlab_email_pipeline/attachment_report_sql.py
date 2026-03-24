"""Shared SQL fragments for attachment reporting (Phase 2.3).

Used by client report metrics and ``validate_attachments.py`` so business-doc
and delivery-noise heuristics stay in one place.
"""

from __future__ import annotations


def _qual(table_alias: str, column: str) -> str:
    if table_alias:
        return f"{table_alias}.{column}"
    return column


def attachment_delivery_noise_predicate_sql(table_alias: str = "a") -> str:
    """True when content_type is delivery-status / multipart noise (not business content)."""
    ct = _qual(table_alias, "content_type")
    return (
        f"LOWER(COALESCE({ct},'')) IN "
        "('message/delivery-status','multipart/report','text/rfc822-headers')"
    )


def attachment_business_doc_predicate_sql(table_alias: str = "a") -> str:
    """PDF/Office/zip/xml business attachments; excludes images and delivery-noise types."""
    fn = _qual(table_alias, "filename")
    ct = _qual(table_alias, "content_type")
    noise = attachment_delivery_noise_predicate_sql(table_alias)
    return f"""(
        (LOWER(COALESCE({ct},'')) LIKE 'application/pdf%' OR LOWER(COALESCE({fn},'')) LIKE '%.pdf')
        OR (LOWER(COALESCE({fn},'')) GLOB '*.doc' OR LOWER(COALESCE({fn},'')) GLOB '*.docx'
            OR LOWER(COALESCE({ct},'')) LIKE '%msword%' OR LOWER(COALESCE({ct},'')) LIKE '%wordprocessing%')
        OR (LOWER(COALESCE({fn},'')) GLOB '*.xls' OR LOWER(COALESCE({fn},'')) GLOB '*.xlsx' OR LOWER(COALESCE({fn},'')) GLOB '*.csv'
            OR LOWER(COALESCE({ct},'')) LIKE '%spreadsheet%' OR LOWER(COALESCE({ct},'')) LIKE '%ms-excel%')
        OR (LOWER(COALESCE({fn},'')) GLOB '*.zip' OR LOWER(COALESCE({ct},'')) LIKE '%zip%' OR LOWER(COALESCE({ct},'')) LIKE '%x-zip%')
        OR (LOWER(COALESCE({fn},'')) GLOB '*.xml' OR LOWER(COALESCE({ct},'')) LIKE '%/xml' OR LOWER(COALESCE({ct},'')) = 'application/xml')
    ) AND LOWER(COALESCE({ct},'')) NOT LIKE 'image/%' AND NOT ({noise})"""


def attachment_business_doc_filename_extension_expr_sql(table_alias: str = "a") -> str:
    """SQLite expression: lowercased extension from filename (handles multiple dots)."""
    fn = _qual(table_alias, "filename")
    return f"""
        LOWER(CASE
            WHEN instr(substr({fn}, instr({fn}, '.') + 1), '.') = 0 THEN substr({fn}, instr({fn}, '.') + 1)
            WHEN instr(substr(substr({fn}, instr({fn}, '.') + 1), instr(substr({fn}, instr({fn}, '.') + 1), '.') + 1), '.') = 0
            THEN substr(substr({fn}, instr({fn}, '.') + 1), instr(substr({fn}, instr({fn}, '.') + 1), '.') + 1)
            ELSE substr(substr(substr({fn}, instr({fn}, '.') + 1), instr(substr({fn}, instr({fn}, '.') + 1), '.') + 1), instr(substr(substr({fn}, instr({fn}, '.') + 1), instr(substr({fn}, instr({fn}, '.') + 1), '.') + 1), '.') + 1)
        END)
    """.strip()
