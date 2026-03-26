"""Public HTTP surface for the Ingest Service.

The Ingest API is itself modeled as an `ApiPushSourceConnector` — see
`docs/architecture.md` §1 — so receiving documents over HTTP will in a later
phase translate into `ChangeEvent` flow through the `SourceConnector` contract.
Phase 2 exposes only `/health`; the `IngestPipelineOrchestrator` is bound
to `app.state.ingest_orchestrator` so Phase 4 routes can drive a real
ingest run without rewiring the composition root.
"""

from __future__ import annotations

from fastapi import FastAPI

from services.ingest.application.ingest_pipeline_orchestrator import (
    IngestPipelineOrchestrator,
)

__all__ = ["create_app"]


def create_app(ingest_orchestrator: IngestPipelineOrchestrator) -> FastAPI:
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

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "ingest"}

    return app
