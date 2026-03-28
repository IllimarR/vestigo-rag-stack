"""Public HTTP surface for the Admin API.

Today only `/health` and OpenAPI docs are exposed; the
`ConfigProvider` and `AuditLogger` are bound on `app.state` so Phase 4
routes (API key management, model configuration, chunk settings,
default collection, RAG prompt template management, and audit log
querying) can drive them without rewiring the composition root.
"""

from __future__ import annotations

from contracts import AuditLogger, ConfigProvider
from fastapi import FastAPI

__all__ = ["create_app"]


def create_app(
    *,
    config_provider: ConfigProvider,
    audit_logger: AuditLogger,
) -> FastAPI:
    app = FastAPI(
        title="Vestigo Admin API",
        version="0.1.0",
        description=(
            "Admin control plane: API keys, model configuration, chunking, "
            "RAG prompt template, default collection, and audit log access. "
            "Today exposes /health only; full surface arrives in Phase 4."
        ),
    )

    app.state.config_provider = config_provider
    app.state.audit_logger = audit_logger

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "admin"}

    return app
