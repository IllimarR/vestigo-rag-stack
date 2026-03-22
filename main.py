"""Composition root for the vestigo-rag-stack skeleton.

This is the **only place** that imports concrete implementations. Everything
else depends on `contracts` alone.

What this file does, in order:
  1. Load infrastructure-level config from `.env` (ports, backend choices).
  2. Construct one placeholder instance per contract (Phase 1: all placeholders).
  3. Type-check that each placeholder satisfies the corresponding `Protocol`
     — mypy does this at check-time; a runtime `Container` dataclass gives
     downstream wiring a single handle to pass around.
  4. Construct the `RAGPipelineOrchestrator` with the six relevant contracts.
  5. Build three FastAPI apps (API Gateway, Ingest API, Admin API).
  6. Run all three Uvicorn servers concurrently with `asyncio.gather`.

Phase 2+ will replace placeholder bindings with real adapters — no other file
needs to change.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

import uvicorn
from dotenv import load_dotenv

from contracts import (
    AuditLogger,
    Chunker,
    ConfigProvider,
    DocumentConverter,
    EmbeddingProvider,
    GenerationProvider,
    Reranker,
    SourceConnector,
    VectorStoreRepository,
)

# Concrete (placeholder) implementations — imported only here, nowhere else.
from services.admin.api import create_app as create_admin_app
from services.api_gateway.api import create_app as create_gateway_app
from services.api_gateway.application.rag_pipeline_orchestrator import (
    RAGPipelineOrchestrator,
)
from services.admin.application.placeholders import NotImplementedConfigProvider
from services.audit.application.placeholders import NotImplementedAuditLogger
from services.ingest.api import create_app as create_ingest_app
from services.ingest.application.placeholders import (
    NotImplementedChunker,
    NotImplementedDocumentConverter,
    NotImplementedSourceConnector,
)
from services.llm.application.placeholders import (
    NotImplementedEmbeddingProvider,
    NotImplementedGenerationProvider,
    NotImplementedReranker,
)
from services.vector_store.application.placeholders import (
    NotImplementedVectorStoreRepository,
)


@dataclass(frozen=True)
class Container:
    """Single handle to all nine contract instances.

    Typed against the `Protocol` classes, so mypy verifies that whatever is
    bound here (placeholder or real) conforms to the contract.
    """

    source_connector: SourceConnector
    document_converter: DocumentConverter
    chunker: Chunker
    embedding_provider: EmbeddingProvider
    vector_store: VectorStoreRepository
    reranker: Reranker
    generation_provider: GenerationProvider
    audit_logger: AuditLogger
    config_provider: ConfigProvider


def build_container() -> Container:
    """Bind concrete implementations to each contract.

    In Phase 1 every binding is a `NotImplementedError`-raising placeholder.
    Replacing one binding here swaps one implementation — no other file changes.
    """

    return Container(
        source_connector=NotImplementedSourceConnector(),
        document_converter=NotImplementedDocumentConverter(),
        chunker=NotImplementedChunker(),
        embedding_provider=NotImplementedEmbeddingProvider(),
        vector_store=NotImplementedVectorStoreRepository(),
        reranker=NotImplementedReranker(),
        generation_provider=NotImplementedGenerationProvider(),
        audit_logger=NotImplementedAuditLogger(),
        config_provider=NotImplementedConfigProvider(),
    )


def build_orchestrator(container: Container) -> RAGPipelineOrchestrator:
    return RAGPipelineOrchestrator(
        embedding_provider=container.embedding_provider,
        vector_store=container.vector_store,
        reranker=container.reranker,
        generation_provider=container.generation_provider,
        config_provider=container.config_provider,
        audit_logger=container.audit_logger,
    )


def _port(env_var: str, default: int) -> int:
    raw = os.getenv(env_var)
    return int(raw) if raw else default


async def _serve(
    app: object,
    *,
    port: int,
    name: str,
) -> None:
    config = uvicorn.Config(
        app,  # type: ignore[arg-type]
        host="0.0.0.0",  # noqa: S104 — local prototype
        port=port,
        log_level="info",
        access_log=False,
        server_header=False,
    )
    server = uvicorn.Server(config)
    print(f"[vestigo] {name} listening on http://localhost:{port}")
    await server.serve()


async def serve_all() -> None:
    load_dotenv()

    container = build_container()
    orchestrator = build_orchestrator(container)

    gateway_app = create_gateway_app(orchestrator)
    ingest_app = create_ingest_app()
    admin_app = create_admin_app(
        config_provider=container.config_provider,
        audit_logger=container.audit_logger,
    )

    await asyncio.gather(
        _serve(
            gateway_app,
            port=_port("API_GATEWAY_PORT", 8000),
            name="API Gateway",
        ),
        _serve(
            ingest_app,
            port=_port("INGEST_API_PORT", 8001),
            name="Ingest API",
        ),
        _serve(
            admin_app,
            port=_port("ADMIN_API_PORT", 8002),
            name="Admin API",
        ),
    )


def main() -> None:
    try:
        asyncio.run(serve_all())
    except KeyboardInterrupt:
        print("[vestigo] shutting down")


if __name__ == "__main__":
    main()
