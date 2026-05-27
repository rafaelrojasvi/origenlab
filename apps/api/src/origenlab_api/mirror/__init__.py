"""Postgres mirror API routes under /mirror (API-3 relocation, read-only)."""

from __future__ import annotations

from fastapi import APIRouter

from origenlab_api.mirror.routes import (
    catalog,
    classification,
    commercial,
    contacts,
    dashboard,
    health,
    meta,
    organizations,
    outbound,
)

router = APIRouter(
    prefix="/mirror",
    tags=["postgres-mirror"],
)

router.include_router(health.router, prefix="/health")
router.include_router(meta.router, prefix="/meta")
router.include_router(dashboard.router, prefix="/dashboard")
router.include_router(classification.router, prefix="/classification")
router.include_router(commercial.router, prefix="/commercial")
router.include_router(catalog.router, prefix="/catalog")
router.include_router(contacts.router, prefix="/contacts")
router.include_router(organizations.router, prefix="/organizations")
router.include_router(outbound.router, prefix="/outbound")
