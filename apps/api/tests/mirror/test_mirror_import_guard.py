"""Mirror routes must use shared postgres_dashboard_api, not legacy email-pipeline origenlab_api."""

from __future__ import annotations

from pathlib import Path

_MIRROR_SRC = Path(__file__).resolve().parents[2] / "src" / "origenlab_api" / "mirror"

_FORBIDDEN_IMPORT_FRAGMENTS = (
    "origenlab_api.config",
    "origenlab_api.deps",
    "origenlab_api.services",
    "origenlab_api.routers",
    "email-pipeline/src/origenlab_api",
)


def test_mirror_source_does_not_import_legacy_origenlab_api_modules() -> None:
    hits: list[str] = []
    for path in _MIRROR_SRC.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for needle in _FORBIDDEN_IMPORT_FRAGMENTS:
            if needle in text:
                hits.append(f"{path.name}: {needle}")
    assert hits == [], "legacy origenlab_api imports in mirror:\n" + "\n".join(hits)


def test_mirror_imports_shared_postgres_dashboard_api() -> None:
    texts = [p.read_text(encoding="utf-8") for p in _MIRROR_SRC.rglob("*.py")]
    combined = "\n".join(texts)
    assert "origenlab_email_pipeline.postgres_dashboard_api" in combined
