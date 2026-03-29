"""Public HTTP surface for the Ingest Service.

The Ingest API is itself modeled as an `ApiPushSourceConnector` — see
`docs/architecture.md` §1 — so the HTTP request body is staged on the
connector, drained as a `ChangeEvent`, and processed through the
standard pipeline. This preserves contract isolation at the external
boundary: nothing about the ingest pipeline knows it's being driven by
HTTP rather than a filesystem scan.

Push routes are only valid when `SOURCE_CONNECTORS=api`; the router
checks the connector type and returns 409 on mismatch so the failure
mode is obvious instead of silently swallowing uploads.
"""

from __future__ import annotations

from contracts import ConfigProvider, SourceConnector
from fastapi import FastAPI

from services.ingest.application.ingest_pipeline_orchestrator import (
    IngestPipelineOrchestrator,
)
from services.ingest.application.routes import build_router

__all__ = ["create_app"]


def create_app(
    ingest_orchestrator: IngestPipelineOrchestrator,
    *,
    source_connector: SourceConnector | None = None,
    config_provider: ConfigProvider | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Vestigo Ingest API",
        version="0.1.0",
        description=(
            "Push-based document ingestion surface. Implemented as the "
            "ApiPushSourceConnector — documents submitted here are translated "
            "into ChangeEvents and flow through the standard ingest pipeline."
        ),
    )
    app.state.ingest_orchestrator = ingest_orchestrator
    app.state.source_connector = source_connector
    app.state.config_provider = config_provider

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "ingest"}

    app.include_router(build_router())

    return app
