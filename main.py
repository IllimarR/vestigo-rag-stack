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
  4. Construct the `RAGPipelineOrchestrator` (query flow, six contracts)
     and the `IngestPipelineOrchestrator` (ingest flow, seven contracts).
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
from contracts import (
    AuditLogger,
    ChunkConfig,
    Chunker,
    ConfigProvider,
    DocumentConverter,
    EmbeddingConfig,
    EmbeddingProvider,
    GenerationProvider,
    Reranker,
    SourceConnector,
    VectorStoreRepository,
)
from dotenv import load_dotenv

# Concrete implementations — imported only here, nowhere else.
from services.admin.api import create_app as create_admin_app
from services.admin.application.file_config_provider import FileConfigProvider
from services.api_gateway.api import create_app as create_gateway_app
from services.api_gateway.application.rag_pipeline_orchestrator import (
    RAGPipelineOrchestrator,
)
from services.audit.application.file_audit_logger import FileAuditLogger
from services.ingest.api import create_app as create_ingest_app
from services.ingest.application.filesystem_source_connector import (
    FilesystemSourceConnector,
)
from services.ingest.application.ingest_pipeline_orchestrator import (
    IngestPipelineOrchestrator,
)
from services.ingest.application.markitdown_document_converter import (
    MarkitdownDocumentConverter,
)
from services.ingest.application.placeholders import (
    NotImplementedChunker,
    NotImplementedDocumentConverter,
    NotImplementedSourceConnector,
)
from services.ingest.application.recursive_chunker import RecursiveChunker
from services.llm.application.openai_http_embedding_provider import (
    OpenAIHttpEmbeddingProvider,
)
from services.llm.application.placeholders import (
    NotImplementedEmbeddingProvider,
    NotImplementedGenerationProvider,
    NotImplementedReranker,
)
from services.vector_store.application.chromadb_vector_store import (
    ChromaDbVectorStoreRepository,
)
from services.vector_store.application.in_memory_vector_store import (
    InMemoryVectorStoreRepository,
)

DEFAULT_CONFIG_PATH = Path("./config/config.yaml")
DEFAULT_AUDIT_LOG_PATH = Path("./data/audit.log")
DEFAULT_CHROMADB_HOST = "chromadb"
DEFAULT_CHROMADB_PORT = 8500
DEFAULT_INGEST_FILESYSTEM_ROOT = Path("./data/incoming")


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


def _int(env_var: str, default: int) -> int:
    raw = os.getenv(env_var)
    return int(raw) if raw else default


def _bool(env_var: str, default: bool = False) -> bool:
    raw = os.getenv(env_var)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _build_source_connector() -> SourceConnector:
    """Dispatch on `SOURCE_CONNECTORS` env (infrastructure-level binding).

    The env var is comma-separated to leave room for multiple parallel
    connectors per deployment; for now we bind the first registered name
    and ignore the rest until multi-source orchestration arrives.
    """
    raw = os.getenv("SOURCE_CONNECTORS", "filesystem").strip().lower()
    selected = next((name for name in (token.strip() for token in raw.split(",")) if name), "")
    if selected in ("filesystem", ""):
        return FilesystemSourceConnector(
            root=_path("INGEST_FILESYSTEM_ROOT", DEFAULT_INGEST_FILESYSTEM_ROOT),
        )
    if selected in ("placeholder", "none"):
        return NotImplementedSourceConnector()
    raise ValueError(
        f"unsupported SOURCE_CONNECTORS={selected!r}; available: 'filesystem'. "
        "Add a new `SourceConnector` implementation under services/ingest/application/."
    )


def _build_document_converter() -> DocumentConverter:
    """Dispatch on `DOCUMENT_CONVERTER` env (infrastructure-level binding)."""
    backend = os.getenv("DOCUMENT_CONVERTER", "markitdown").strip().lower()
    if backend in ("markitdown", ""):
        return MarkitdownDocumentConverter()
    if backend in ("placeholder", "none"):
        return NotImplementedDocumentConverter()
    raise ValueError(
        f"unsupported DOCUMENT_CONVERTER={backend!r}; available: 'markitdown'. "
        "Add a new `DocumentConverter` implementation under services/ingest/application/."
    )


def _build_vector_store() -> VectorStoreRepository:
    backend = os.getenv("VECTOR_STORE_BACKEND", "in_memory").strip().lower()
    if backend in ("in_memory", "inmemory", ""):
        return InMemoryVectorStoreRepository()
    if backend == "chromadb":
        return ChromaDbVectorStoreRepository(
            host=os.getenv("CHROMADB_HOST", DEFAULT_CHROMADB_HOST),
            port=_int("CHROMADB_PORT", DEFAULT_CHROMADB_PORT),
            ssl=_bool("CHROMADB_SSL"),
        )
    raise ValueError(
        f"unknown VECTOR_STORE_BACKEND={backend!r}; expected 'in_memory' or 'chromadb'."
    )


def _build_chunker(chunk_config: ChunkConfig) -> Chunker:
    """Dispatch on `ChunkConfig.method` per architecture.md §Modularity Proof §4."""
    method = chunk_config.method.strip().lower()
    if method == "recursive":
        return RecursiveChunker()
    if method in ("placeholder", "none", ""):
        return NotImplementedChunker()
    raise ValueError(
        f"unsupported chunking method={method!r}; available: 'recursive'. "
        "Add a new `Chunker` implementation under services/ingest/application/."
    )


def _build_embedding_provider(embedding_config: EmbeddingConfig) -> EmbeddingProvider:
    """Dispatch on `EmbeddingConfig.api_type` per architecture.md §Modularity Proof §4."""
    api_type = embedding_config.api_type.strip().lower()
    if api_type in ("openai", "openai-compatible", "openai_compatible"):
        api_key = None
        params = embedding_config.parameters or {}
        maybe_key = params.get("api_key")
        if isinstance(maybe_key, str) and maybe_key:
            api_key = maybe_key
        return OpenAIHttpEmbeddingProvider(
            endpoint=embedding_config.endpoint,
            model_name=embedding_config.model_name,
            api_key=api_key,
        )
    if api_type in ("placeholder", "none", ""):
        return NotImplementedEmbeddingProvider()
    raise ValueError(
        f"unsupported embedding api_type={api_type!r}; available: 'openai-compatible'. "
        "Add a new `EmbeddingProvider` implementation under services/llm/application/."
    )


def build_container() -> Container:
    """Bind implementations to each contract.

    Application-level contracts (`Chunker`, `EmbeddingProvider`, ...) dispatch
    on values read from `ConfigProvider` per `docs/architecture.md`
    §Modularity Proof §4. Infrastructure-level contracts (vector store
    backend) dispatch on `.env` values.

    Current status:
      ✓ ConfigProvider       — file-based (YAML)
      ✓ AuditLogger          — file-based (JSONL)
      ✓ VectorStoreRepo      — in-memory OR chromadb (env-selected)
      ✓ Chunker              — recursive (ConfigProvider method dispatch)
      ✓ EmbeddingProvider    — OpenAI-compatible HTTP (ConfigProvider api_type dispatch)
      ✓ SourceConnector      — filesystem (env-selected)
      ✓ DocumentConverter    — markitdown (env-selected)
      ✗ Reranker             — placeholder (Phase 3)
      ✗ GenerationProvider   — placeholder (Phase 3)
    """

    config_path = _path("CONFIG_FILE_PATH", DEFAULT_CONFIG_PATH)
    audit_log_path = _path("AUDIT_LOG_FILE", DEFAULT_AUDIT_LOG_PATH)

    config_provider = FileConfigProvider(config_path)
    chunking = config_provider.get_chunking_config()
    embedding = config_provider.get_embedding_config()

    return Container(
        source_connector=_build_source_connector(),
        document_converter=_build_document_converter(),
        chunker=_build_chunker(chunking),
        embedding_provider=_build_embedding_provider(embedding),
        vector_store=_build_vector_store(),
        reranker=NotImplementedReranker(),
        generation_provider=NotImplementedGenerationProvider(),
        audit_logger=FileAuditLogger(audit_log_path),
        config_provider=config_provider,
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


def build_ingest_orchestrator(container: Container) -> IngestPipelineOrchestrator:
    return IngestPipelineOrchestrator(
        source_connector=container.source_connector,
        document_converter=container.document_converter,
        chunker=container.chunker,
        embedding_provider=container.embedding_provider,
        vector_store=container.vector_store,
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
    rag_orchestrator = build_orchestrator(container)
    ingest_orchestrator = build_ingest_orchestrator(container)

    gateway_app = create_gateway_app(rag_orchestrator)
    ingest_app = create_ingest_app(ingest_orchestrator)
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
            port=_port("INGEST_API_PORT", 8002),
            name="Ingest API",
        ),
        _serve(
            admin_app,
            port=_port("ADMIN_API_PORT", 8001),
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
