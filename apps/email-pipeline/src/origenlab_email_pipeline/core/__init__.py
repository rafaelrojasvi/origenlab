"""Stable **core** import surface for `origenlab_email_pipeline` (re-exports only).

This package is a *compatibility re-export layer*: implementation remains in the existing
top-level modules under `origenlab_email_pipeline/` (e.g. `config`, `db`, `candidate_export_gate`).

- Use ``from origenlab_email_pipeline.core import config, db, sqlite_migrate`` for
  infrastructure entrypoints re-exported from the parent package.
- Use subpackages: ``core.outbound``, ``core.gmail``, ``core.mart``, ``core.suppliers``,
  and (later) ``core.leads``.

**No runtime logic lives here yet.** Do not add business logic in this tree until a
dedicated migration phase. Existing ``from origenlab_email_pipeline.…`` imports stay valid.

Submodules are exposed so ``import origenlab_email_pipeline.core.config`` resolves to
``core/config.py`` re-exporting ``origenlab_email_pipeline.config``.
"""

from . import config as config
from . import db as db
from . import sqlite_migrate as sqlite_migrate

__all__ = ["config", "db", "sqlite_migrate"]
