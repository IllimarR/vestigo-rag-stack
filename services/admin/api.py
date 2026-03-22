"""Public HTTP surface for the Admin API.

Phase 1 exposes `/health` and OpenAPI docs. Phase 4 will add endpoints for
API key management, model configuration, chunk settings, default collection,
RAG prompt template management, and audit log querying.
"""

from __future__ import annotations

from fastapi import FastAPI

from contracts import AuditLogger, ConfigProvider

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
            "Phase 1 exposes /health only."
        ),
    )

    app.state.config_provider = config_provider
    app.state.audit_logger = audit_logger

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "admin"}

    return app
