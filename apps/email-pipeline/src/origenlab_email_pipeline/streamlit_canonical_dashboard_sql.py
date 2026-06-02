"""Deprecated compatibility shim — import from ``canonical_operational_sql`` instead.

Streamlit retirement S1: non-UI canonical Gmail SQL lives in
``origenlab_email_pipeline.canonical_operational_sql``. This module re-exports the
same symbols for ``business_mart_app`` and legacy tests; new production code must
not depend on the ``streamlit_`` name.
"""

from __future__ import annotations

from origenlab_email_pipeline.canonical_operational_sql import (
    canonical_emails_where,
    count_archive_mart_table,
    count_canonical_attachments,
    count_canonical_duplicate_message_id_groups,
    count_canonical_empty_body,
    count_canonical_missing_date_iso,
    count_canonical_missing_message_id,
    count_canonical_operational_contacts,
    count_canonical_operational_opportunity_signals,
    count_canonical_operational_organizations,
    count_canonical_sent_inbox,
    count_canonical_unique_external_senders,
    direction_label_for_folder,
    folder_kind_label,
    fmt_short_date,
    load_canonical_gmail_classification_sample,
    load_inicio_recent_canonical_rows,
)

__all__ = [
    "canonical_emails_where",
    "count_archive_mart_table",
    "count_canonical_attachments",
    "count_canonical_duplicate_message_id_groups",
    "count_canonical_empty_body",
    "count_canonical_missing_date_iso",
    "count_canonical_missing_message_id",
    "count_canonical_operational_contacts",
    "count_canonical_operational_opportunity_signals",
    "count_canonical_operational_organizations",
    "count_canonical_sent_inbox",
    "count_canonical_unique_external_senders",
    "direction_label_for_folder",
    "folder_kind_label",
    "fmt_short_date",
    "load_inicio_recent_canonical_rows",
    "load_canonical_gmail_classification_sample",
]
