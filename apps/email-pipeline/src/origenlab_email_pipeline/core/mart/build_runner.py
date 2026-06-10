"""Orchestrate business mart build stages (SQLite; CLI/mart scripts only)."""

from __future__ import annotations

import sqlite3
from origenlab_email_pipeline.core.mart.build_options import MartBuildOptions
from origenlab_email_pipeline.core.mart.contact_org_builder import (
    rebuild_contact_master,
    rebuild_organization_master,
    scan_email_contacts,
    scan_email_contacts_from_features,
)
from origenlab_email_pipeline.core.mart.document_master_builder import rebuild_document_master
from origenlab_email_pipeline.core.mart.opportunity_signal_builder import rebuild_opportunity_signals
from origenlab_email_pipeline.pipeline_run_recorder import (
    finish_run,
    get_git_describe,
    set_kv,
)
from origenlab_email_pipeline.business_mart import now_iso


def ensure_fast_indexes(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_emails_source_file ON emails(source_file);
        CREATE INDEX IF NOT EXISTS idx_emails_folder ON emails(folder);
        CREATE INDEX IF NOT EXISTS idx_emails_source_file_date_iso ON emails(source_file, date_iso);
        CREATE INDEX IF NOT EXISTS idx_opportunity_signals_email_id ON opportunity_signals(email_id);
        """
    )
    conn.commit()


def run_business_mart_build(
    conn: sqlite3.Connection,
    run_id: int,
    options: MartBuildOptions,
) -> str:
    """Run mart stages; record pipeline KV; always ``finish_run`` in ``finally``."""
    built_at = ""
    try:
        doc_aggs = rebuild_document_master(
            conn,
            internal_domains=set(options.internal_domains),
            mart_slack=options.mart_date_slack_days,
            skip_if_unchanged=options.skip_document_master_if_unchanged,
        )
        if options.use_email_mart_features:
            contact, n_scanned = scan_email_contacts_from_features(
                conn,
                options=options,
                doc_aggs=doc_aggs,
            )
        else:
            contact, n_scanned = scan_email_contacts(
                conn,
                options=options,
                doc_aggs=doc_aggs,
            )
        rebuild_contact_master(conn, contact)
        org = rebuild_organization_master(conn, contact)
        rebuild_opportunity_signals(conn, contact, org)
        built_at = now_iso()
        set_kv(conn, "mart_built_at", built_at)
        set_kv(conn, "mart_build_git_describe", get_git_describe())
        set_kv(conn, "last_mart_pipeline_run_id", str(run_id))
    finally:
        finish_run(conn, run_id)
    return built_at
