"""Public HTTP surface for the API Gateway.

Phase 1 exposes `/health` and OpenAPI docs. Phase 3 will add the OpenAI
Chat Completions-compatible endpoint (`POST /v1/chat/completions`) with
both non-streaming and SSE streaming responses, plus API key auth.
"""

from __future__ import annotations

from fastapi import FastAPI

from services.api_gateway.application.rag_pipeline_orchestrator import (
    RAGPipelineOrchestrator,
)

__all__ = ["create_app"]


def create_app(orchestrator: RAGPipelineOrchestrator) -> FastAPI:
    app = FastAPI(
        title="Vestigo API Gateway",
        version="0.1.0",
        description=(
            "OpenAI Chat Completions-compatible endpoint. Routes requests "
            "through the RAGPipelineOrchestrator: embed → retrieve → rerank "
            "→ generate. Phase 1 exposes /health only."
        ),
    )

    # Attach orchestrator for later routes; keep a reference so the compose
    # root proves wiring without calling it at import time.
    app.state.orchestrator = orchestrator

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "api_gateway"}

    return app
