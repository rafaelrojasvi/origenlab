"""Alembic environment for PostgreSQL-only migrations.

Database URL (first match wins):

1. ``ALEMBIC_DATABASE_URL``
2. ``ORIGENLAB_POSTGRES_URL``

Example: ``postgresql+psycopg://user:pass@host:5432/dbname``

If neither is set, migration commands fail with a clear error. The operational app uses
SQLite; Alembic does not use the SQLite path.
"""

from __future__ import annotations

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

_MISSING_URL_MSG = """\
Set ALEMBIC_DATABASE_URL or ORIGENLAB_POSTGRES_URL to run Postgres migrations.
SQLite runtime is not used by Alembic.
"""


def _resolve_database_url() -> str:
    url = os.environ.get("ALEMBIC_DATABASE_URL") or os.environ.get("ORIGENLAB_POSTGRES_URL")
    if not url or not str(url).strip():
        raise RuntimeError(_MISSING_URL_MSG.strip())
    return str(url).strip()


def run_migrations_offline() -> None:
    url = _resolve_database_url()
    context.configure(
        url=url,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    config.set_main_option("sqlalchemy.url", _resolve_database_url())
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
