"""Public HTTP surface for the API Gateway.

Exposes `/health`, OpenAPI docs, and the OpenAI Responses-compatible
endpoint (`POST /v1/responses`) covering both non-streaming JSON
responses and SSE streaming. Authentication is a simple Bearer-token
allow-list bound at the composition root via `ApiKeyVerifier`; when
the allow-list is empty the gateway runs in dev mode and labels every
request as anonymous in audit logs.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from services.api_gateway.application.auth import ApiKeyVerifier, AuthError
from services.api_gateway.application.rag_pipeline_orchestrator import (
    RAGPipelineOrchestrator,
)
from services.api_gateway.application.responses_api import (
    make_response_id,
    non_streaming_response_body,
    parse_responses_request,
    sse_stream,
)

__all__ = ["create_app"]


def create_app(
    orchestrator: RAGPipelineOrchestrator,
    *,
    api_key_verifier: ApiKeyVerifier | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Vestigo API Gateway",
        version="0.1.0",
        description=(
            "OpenAI Responses-compatible endpoint. Routes requests through "
            "the RAGPipelineOrchestrator: embed -> retrieve -> rerank -> "
            "generate. Phase 1 exposed /health only; Phase 3 adds "
            "POST /v1/responses with both non-streaming JSON and SSE "
            "streaming responses, plus Bearer-token auth."
        ),
    )
    verifier = api_key_verifier or ApiKeyVerifier(allowed={})

    app.state.orchestrator = orchestrator
    app.state.api_key_verifier = verifier

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "api_gateway"}

    @app.post("/v1/responses")
    async def responses(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> Any:
        try:
            api_key_id = verifier.verify(authorization)
        except AuthError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(status_code=400, detail="request body must be a JSON object")
        try:
            parsed = parse_responses_request(body)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        response_id = make_response_id()

        if parsed.stream:
            chunks = orchestrator.run_stream(
                parsed.messages,
                api_key_id=api_key_id,
                collection=parsed.collection,
            )
            return StreamingResponse(
                sse_stream(response_id=response_id, chunks=chunks),
                media_type="text/event-stream",
                headers={"X-Vestigo-Response-Id": response_id},
            )

        result = orchestrator.run(
            parsed.messages,
            api_key_id=api_key_id,
            collection=parsed.collection,
        )
        return non_streaming_response_body(response_id=response_id, response=result)

    return app
