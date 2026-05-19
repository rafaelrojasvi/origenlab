"""API read-model views for apps/api Postgres backend (DB-1).

Revision ID: 20260519_0014
Revises: 20260519_0013
Create Date: 2026-05-19

See reports/out/active/current/db1_api_read_model_ddl_spec_20260519.md
Views expose no email body columns. DDL only; no data migration.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "20260519_0014"
down_revision: Union[str, Sequence[str], None] = "20260519_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE VIEW api.v_operator_status AS
        WITH last_sync AS (
          SELECT *
          FROM reporting.dashboard_sync_run
          WHERE status = 'success'
          ORDER BY finished_at DESC NULLS LAST, id DESC
          LIMIT 1
        ),
        cls AS (
          SELECT
            COUNT(*)::INTEGER AS classification_row_count,
            MAX(date_iso) FILTER (WHERE date_iso >= '2026-01-01') AS emails_2026_max_date_iso
          FROM reporting.email_classification_canonical
          WHERE source_scope = 'canonical'
        ),
        outreach AS (
          SELECT
            COUNT(*) FILTER (WHERE state = 'contacted')::INTEGER AS outreach_contacted_count,
            COUNT(*) FILTER (WHERE state = 'replied')::INTEGER AS outreach_replied_count,
            COUNT(*) FILTER (WHERE state = 'snoozed')::INTEGER AS outreach_snoozed_count
          FROM outbound.outreach_contact_state
        )
        SELECT
          CASE
            WHEN ls.id IS NULL THEN 'BLOCKED'
            WHEN ls.finished_at IS NULL OR ls.finished_at < (now() - INTERVAL '24 hours') THEN 'CAUTION'
            ELSE 'READY'
          END AS verdict,
          now() AS generated_at,
          ls.id AS sync_run_id,
          ls.finished_at AS mirror_synced_at,
          CASE
            WHEN ls.finished_at IS NULL THEN NULL
            ELSE EXTRACT(EPOCH FROM (now() - ls.finished_at))::BIGINT
          END AS staleness_seconds,
          COALESCE(ls.sqlite_path, '') AS sqlite_path_redacted,
          ls.canonical_contact_count,
          ls.canonical_organization_count,
          ls.outreach_state_count,
          ls.email_suppression_count,
          ls.domain_suppression_count,
          c.classification_row_count,
          c.emails_2026_max_date_iso,
          o.outreach_contacted_count,
          o.outreach_replied_count,
          o.outreach_snoozed_count,
          ls.details_json->>'campaign_mode' AS campaign_mode,
          (
            SELECT COALESCE(jsonb_agg(w), '[]'::jsonb)
            FROM (
              SELECT 'Postgres mirror: no successful dashboard_sync_run' AS w
              WHERE ls.id IS NULL
              UNION ALL
              SELECT 'Postgres mirror last sync older than 24h'
              WHERE ls.finished_at IS NOT NULL
                AND ls.finished_at < (now() - INTERVAL '24 hours')
              UNION ALL
              SELECT 'classification mirror empty'
              WHERE c.classification_row_count = 0
            ) t(w)
          ) AS warnings_json,
          jsonb_build_object(
            'verdict',
              CASE
                WHEN ls.id IS NULL THEN 'mirror_blocked'
                WHEN ls.finished_at IS NULL
                  OR ls.finished_at < (now() - INTERVAL '24 hours') THEN 'mirror_stale'
                ELSE 'mirror_ok'
              END,
            'sync_run_id', ls.id,
            'note', 'SQLite remains authoritative for send/outbound gate until DB-5'
          ) AS outbound_readiness_json
        FROM cls c
        CROSS JOIN outreach o
        LEFT JOIN last_sync ls ON TRUE
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW api.v_recent_email AS
        SELECT
          ec.email_id,
          ec.date_iso,
          LEFT(COALESCE(ec.subject, ''), 200) AS subject_preview,
          LEFT(COALESCE(ec.from_addr, ''), 160) AS sender_preview,
          NULL::TEXT AS source_file,
          ec.folder AS folder_hint,
          (
            ec.predicted_label IN ('customer', 'business_core')
            OR ec.categories_json ?| ARRAY['quote', 'purchase', 'invoice', 'equipment']
            OR (ec.categories_json::text ILIKE '%quote%')
          ) AS has_positive_signal,
          EXISTS (
            SELECT 1
            FROM outbound.contact_email_suppression ces
            WHERE lower(trim(ces.email)) = lower(trim(ec.from_addr))
          ) AS has_suppression_signal,
          ec.predicted_label,
          ec.recommended_action,
          ec.etiqueta_ui,
          ec.sync_run_id
        FROM reporting.email_classification_canonical ec
        WHERE ec.source_scope = 'canonical'
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW api.v_outreach_safety AS
        WITH last_sync AS (
          SELECT id FROM reporting.dashboard_sync_run
          WHERE status = 'success'
          ORDER BY finished_at DESC NULLS LAST
          LIMIT 1
        ),
        batch AS (
          SELECT
            b.id,
            b.lane,
            b.created_at,
            (
              SELECT COUNT(*)::INTEGER
              FROM outbound.outbound_batch_recipient r
              WHERE r.batch_id = b.id
            ) AS recipient_count,
            (
              SELECT COUNT(*)::INTEGER
              FROM outbound.outbound_batch_recipient r
              WHERE r.batch_id = b.id AND r.eligibility_result <> 'pass'
            ) AS excluded_count
          FROM outbound.outbound_batch b
          ORDER BY b.created_at DESC
          LIMIT 1
        )
        SELECT
          now() AS generated_at,
          ls.id AS sync_run_id,
          (SELECT COUNT(*)::INTEGER FROM outbound.contact_email_suppression) AS suppressed_email_count,
          (SELECT COUNT(*)::INTEGER FROM outbound.contact_domain_suppression) AS suppressed_domain_count,
          (SELECT COUNT(*)::INTEGER FROM outbound.outreach_contact_state WHERE state = 'contacted') AS outreach_contacted_count,
          (SELECT COUNT(*)::INTEGER FROM outbound.outreach_contact_state WHERE state = 'replied') AS outreach_replied_count,
          (SELECT COUNT(*)::INTEGER FROM outbound.outreach_contact_state WHERE state = 'snoozed') AS outreach_snoozed_count,
          b.id AS latest_batch_id,
          b.lane AS latest_batch_lane,
          b.created_at AS latest_batch_created_at,
          b.recipient_count AS latest_batch_recipient_count,
          b.excluded_count AS latest_batch_excluded_count
        FROM last_sync ls
        LEFT JOIN batch b ON TRUE
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW api.v_equipment_opportunity AS
        WITH latest_source AS (
          SELECT id, manifest_path, csv_path, date_suffix, campaign_mode, synced_at
          FROM commercial.equipment_opportunity_source
          WHERE is_canonical = TRUE
          ORDER BY synced_at DESC, id DESC
          LIMIT 1
        )
        SELECT
          eo.id AS opportunity_id,
          eo.source_id,
          eo.priority_rank,
          eo.codigo_licitacion,
          eo.buyer,
          eo.region,
          eo.close_date,
          eo.close_at,
          eo.equipment_category,
          eo.item_description,
          eo.next_action,
          eo.safe_channel,
          eo.supplier_needed,
          eo.contact_status,
          eo.operator_note,
          ls.csv_path AS source_path,
          ls.campaign_mode,
          ls.synced_at,
          (eo.source_id = ls.id) AS is_canonical_source
        FROM commercial.equipment_opportunity eo
        JOIN commercial.equipment_opportunity_source src ON src.id = eo.source_id
        JOIN latest_source ls ON src.id = ls.id
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW api.v_warm_case AS
        SELECT
          ('case:' || c.id::text) AS case_id,
          c.last_email_id,
          c.last_activity_at AS last_seen_at,
          COALESCE(c.account_name, '') AS account_name,
          c.primary_contact_email AS contact_email,
          c.title AS subject,
          c.category,
          c.status,
          COALESCE(c.next_action, '') AS next_action,
          COALESCE(es.equipment_category, c.equipment_signal, '') AS equipment_signal,
          LEFT(COALESCE(c.title, ''), 280) AS snippet,
          NULL::TEXT AS gmail_url
        FROM commercial.warm_case c
        LEFT JOIN commercial.warm_case_equipment_signal es ON es.case_id = c.id
        WHERE c.status IN ('new', 'open', 'waiting', 'quoted')
          AND c.closed_at IS NULL
        """
    )

    op.execute(
        """
        CREATE OR REPLACE VIEW api.v_contact_profile AS
        SELECT
          lower(trim(c.email)) AS email_norm,
          lower(trim(c.email)) AS email_display,
          COALESCE(c.contact_name_best, '') AS contact_name,
          COALESCE(c.domain, split_part(lower(trim(c.email)), '@', 2)) AS domain,
          COALESCE(c.organization_name_guess, o.organization_name_guess, '') AS organization_name,
          COALESCE(c.domain, o.domain, split_part(lower(trim(c.email)), '@', 2)) AS organization_domain,
          c.first_seen_at,
          c.last_seen_at,
          COALESCE(c.total_emails, 0) AS message_count,
          os.state AS outreach_state,
          os.last_contacted_at,
          os.source AS outreach_source,
          os.updated_by AS outreach_updated_by,
          os.notes AS outreach_notes,
          (ces.email IS NOT NULL) AS suppressed_email,
          (
            cds.domain_norm IS NOT NULL
            OR EXISTS (
              SELECT 1 FROM outbound.contact_domain_suppression d2
              WHERE lower(trim(c.domain)) = d2.domain_norm
                 OR lower(trim(c.domain)) LIKE ('%.' || d2.domain_norm)
            )
          ) AS suppressed_domain,
          (
            os.state IN ('contacted', 'replied', 'snoozed')
            OR COALESCE(sent.sent_count, 0) > 0
          ) AS do_not_repeat,
          COALESCE(sent.sent_count, 0) AS sent_count,
          sent.latest_sent_at,
          LEFT(COALESCE(sent.latest_subject, ''), 200) AS latest_subject,
          (c.email IS NOT NULL) AS mart_present,
          c_sync.sync_run_id
        FROM mart.contact_master_canonical c
        LEFT JOIN mart.organization_master_canonical o
          ON lower(trim(o.domain)) = lower(trim(c.domain))
        LEFT JOIN outbound.outreach_contact_state os
          ON os.contact_email_norm = lower(trim(c.email))
        LEFT JOIN outbound.contact_email_suppression ces
          ON lower(trim(ces.email)) = lower(trim(c.email))
        LEFT JOIN outbound.contact_domain_suppression cds
          ON cds.domain_norm = lower(trim(c.domain))
        LEFT JOIN LATERAL (
          SELECT
            COUNT(*)::INTEGER AS sent_count,
            MAX(e.date_iso) AS latest_sent_at,
            (ARRAY_AGG(e.subject ORDER BY e.date_iso DESC NULLS LAST))[1] AS latest_subject
          FROM archive.emails e
          WHERE lower(e.source_file) LIKE 'gmail:contacto@origenlab.cl/%'
            AND e.folder IN ('[Gmail]/Enviados', '[Gmail]/Sent Mail')
            AND lower(COALESCE(e.recipients, '')) LIKE ('%' || lower(trim(c.email)) || '%')
        ) sent ON TRUE
        LEFT JOIN LATERAL (
          SELECT id AS sync_run_id
          FROM reporting.dashboard_sync_run
          WHERE status = 'success'
          ORDER BY finished_at DESC NULLS LAST
          LIMIT 1
        ) c_sync ON TRUE
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS api.v_contact_profile")
    op.execute("DROP VIEW IF EXISTS api.v_warm_case")
    op.execute("DROP VIEW IF EXISTS api.v_equipment_opportunity")
    op.execute("DROP VIEW IF EXISTS api.v_outreach_safety")
    op.execute("DROP VIEW IF EXISTS api.v_recent_email")
    op.execute("DROP VIEW IF EXISTS api.v_operator_status")
