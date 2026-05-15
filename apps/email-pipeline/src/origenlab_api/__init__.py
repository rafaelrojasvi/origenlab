"""Read-only FastAPI dashboard API (Postgres mirror). Slice 1 — no writes."""

from origenlab_api.main import create_app

__all__ = ["create_app"]
