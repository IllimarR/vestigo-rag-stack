"""Public HTTP surface for the Admin API.

`/health`, OpenAPI docs, and the Phase 4 control-plane routes (API
key management, model configuration, chunk settings, default
collection, RAG prompt template, audit log querying). The
`ConfigProvider`, `AuditLogger`, and `ApiKeyStore` are bound on
`app.state` so the routes can drive them without rewiring the
composition root.

CORS is on because the admin-ui (`admin-ui/`, port 3000) runs in a
browser and the same-origin policy blocks cross-port fetches by
default. The allowed origins list is taken from the `cors_origins`
constructor argument so the composition root can drive it from an
env var (`ADMIN_CORS_ORIGINS`) — operators running the SPA from a
non-default host can override without code changes.
"""

from __future__ import annotations

from collections.abc import Sequence

from contracts import AuditLogger, ConfigProvider
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from services.admin.application.api_key_store import ApiKeyStore
from services.admin.application.routes import build_router

__all__ = ["DEFAULT_CORS_ORIGINS", "create_app"]


# The dev workflow runs admin-ui on :3000 (Vite default) and the
# Compose stack maps the nginx container to the same host port. Both
# resolve to this origin from the browser's perspective.
DEFAULT_CORS_ORIGINS: tuple[str, ...] = ("http://localhost:3000",)


def create_app(
    *,
    config_provider: ConfigProvider,
    audit_logger: AuditLogger,
    api_key_store: ApiKeyStore,
    cors_origins: Sequence[str] | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Vestigo Admin API",
        version="0.1.0",
        description=(
            "Admin control plane: API keys, model configuration, chunking, "
            "RAG prompt template, default collection, and audit log access."
        ),
    )

    origins = list(cors_origins) if cors_origins is not None else list(DEFAULT_CORS_ORIGINS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        # The SPA only ever sends GET / POST / PUT / DELETE plus an
        # OPTIONS preflight, but the wildcard keeps the door open for
        # future routes without another middleware edit.
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.config_provider = config_provider
    app.state.audit_logger = audit_logger
    app.state.api_key_store = api_key_store

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "admin"}

    app.include_router(build_router())

    return app
