"""Composition root for the vestigo-rag-stack skeleton.

This is the **only place** that imports concrete implementations. Everything
else depends on `contracts` alone.

What this file does, in order:
  1. Load infrastructure-level config from `.env` (ports, backend choices,
     file paths for file-based stubs).
  2. Construct one instance per contract (Phase 1: real file-based
     ConfigProvider + AuditLogger, real in-memory VectorStoreRepository;
     everything else still a NotImplementedError placeholder until its
     phase lands).
  3. The `Container` dataclass is typed against the `Protocol` classes, so
     mypy verifies structurally that every binding satisfies its contract.
  4. Construct the `RAGPipelineOrchestrator` with the six relevant contracts.
  5. Build three FastAPI apps (API Gateway, Ingest API, Admin API).
  6. Run all three Uvicorn servers concurrently with `asyncio.gather`.

Replacing a binding here is the whole swap protocol — no other file needs
to change. That is the modularity guarantee in `docs/architecture.md` §2.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path

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

# Concrete implementations — imported only here, nowhere else.
from services.admin.api import create_app as create_admin_app
from services.admin.application.file_config_provider import FileConfigProvider
from services.api_gateway.api import create_app as create_gateway_app
from services.api_gateway.application.rag_pipeline_orchestrator import (
    RAGPipelineOrchestrator,
)
from services.audit.application.file_audit_logger import FileAuditLogger
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
from services.vector_store.application.in_memory_vector_store import (
    InMemoryVectorStoreRepository,
)

DEFAULT_CONFIG_PATH = Path("./config/config.yaml")
DEFAULT_AUDIT_LOG_PATH = Path("./data/audit.log")


@dataclass(frozen=True)
class Container:
    """Single handle to all nine contract instances.

    Typed against the `Protocol` classes, so mypy verifies that whatever is
    bound here conforms to the contract — swap in any implementation and
    either it satisfies the Protocol structurally or mypy rejects it.
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


def _path(env_var: str, default: Path) -> Path:
    raw = os.getenv(env_var)
    return Path(raw) if raw else default


def build_container() -> Container:
    """Bind implementations to each contract.

    Phase 1 status:
      ✓ ConfigProvider    — file-based (YAML)
      ✓ AuditLogger       — file-based (JSONL)
      ✓ VectorStoreRepo   — in-memory
      ✗ SourceConnector   — placeholder (Phase 2)
      ✗ DocumentConverter — placeholder (Phase 2)
      ✗ Chunker           — placeholder (Phase 2)
      ✗ EmbeddingProvider — placeholder (Phase 2)
      ✗ Reranker          — placeholder (Phase 3)
      ✗ GenerationProvider — placeholder (Phase 3)
    """

    config_path = _path("CONFIG_FILE_PATH", DEFAULT_CONFIG_PATH)
    audit_log_path = _path("AUDIT_LOG_FILE", DEFAULT_AUDIT_LOG_PATH)

    return Container(
        source_connector=NotImplementedSourceConnector(),
        document_converter=NotImplementedDocumentConverter(),
        chunker=NotImplementedChunker(),
        embedding_provider=NotImplementedEmbeddingProvider(),
        vector_store=InMemoryVectorStoreRepository(),
        reranker=NotImplementedReranker(),
        generation_provider=NotImplementedGenerationProvider(),
        audit_logger=FileAuditLogger(audit_log_path),
        config_provider=FileConfigProvider(config_path),
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
