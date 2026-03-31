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

import argparse
import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
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
    GenerationConfig,
    GenerationProvider,
    Reranker,
    RerankerConfig,
    SourceConnector,
    VectorStoreRepository,
)
from dotenv import load_dotenv

# Concrete implementations — imported only here, nowhere else.
from services.admin.api import create_app as create_admin_app
from services.admin.application.api_key_store import ApiKeyStore, EnvApiKeyStore
from services.admin.application.file_config_provider import FileConfigProvider
from services.admin.application.sqlite_api_key_store import SqliteApiKeyStore
from services.admin.application.sqlite_config_provider import SqliteConfigProvider
from services.api_gateway.api import create_app as create_gateway_app
from services.api_gateway.application.auth import ApiKeyVerifier
from services.api_gateway.application.rag_pipeline_orchestrator import (
    RAGPipelineOrchestrator,
)
from services.audit.application.file_audit_logger import FileAuditLogger
from services.audit.application.sqlite_audit_logger import SqliteAuditLogger
from services.ingest.api import create_app as create_ingest_app
from services.ingest.application.api_push_source_connector import (
    ApiPushSourceConnector,
)
from services.ingest.application.filesystem_source_connector import (
    FilesystemSourceConnector,
)
from services.ingest.application.fixed_size_chunker import FixedSizeChunker
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
from services.llm.application.anthropic_generation_provider import (
    AnthropicGenerationProvider,
)
from services.llm.application.cross_encoder_reranker import (
    CrossEncoderReranker,
    sentence_transformers_scorer,
)
from services.llm.application.llm_reranker import LLMReranker
from services.llm.application.openai_http_embedding_provider import (
    OpenAIHttpEmbeddingProvider,
)
from services.llm.application.openai_http_generation_provider import (
    OpenAIHttpGenerationProvider,
)
from services.llm.application.placeholders import (
    NotImplementedEmbeddingProvider,
    NotImplementedGenerationProvider,
    NotImplementedReranker,
)
from services.llm.application.sentence_transformers_embedding_provider import (
    SentenceTransformersEmbeddingProvider,
    sentence_transformers_encoder,
)
from services.vector_store.application.chromadb_vector_store import (
    ChromaDbVectorStoreRepository,
)
from services.vector_store.application.in_memory_vector_store import (
    InMemoryVectorStoreRepository,
)

DEFAULT_CONFIG_PATH = Path("./config/config.yaml")
DEFAULT_AUDIT_LOG_PATH = Path("./data/audit.log")
DEFAULT_CONTROL_PLANE_DB_PATH = Path("./data/control_plane.db")
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


def _csv_env(env_var: str) -> list[str] | None:
    """Parse a comma-separated env var. Empty / unset returns `None` so
    consumers can fall back to their own defaults.
    """
    raw = os.getenv(env_var, "").strip()
    if not raw:
        return None
    return [item.strip() for item in raw.split(",") if item.strip()]


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
    if selected == "api":
        return ApiPushSourceConnector(
            source_id=os.getenv("API_PUSH_SOURCE_ID", "api"),
        )
    if selected in ("placeholder", "none"):
        return NotImplementedSourceConnector()
    raise ValueError(
        f"unsupported SOURCE_CONNECTORS={selected!r}; available: 'filesystem', 'api'. "
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
    if method in ("fixed_size", "fixed-size"):
        return FixedSizeChunker()
    if method in ("placeholder", "none", ""):
        return NotImplementedChunker()
    raise ValueError(
        f"unsupported chunking method={method!r}; available: 'recursive', 'fixed_size'. "
        "Add a new `Chunker` implementation under services/ingest/application/."
    )


def _build_reranker(
    reranker_config: RerankerConfig,
    *,
    generation_provider: GenerationProvider,
) -> Reranker:
    """Dispatch on `RerankerConfig.type` per architecture.md §Modularity Proof §4.

    The `llm` branch borrows the already-bound `GenerationProvider` to act
    as a zero-shot relevance judge — see `LLMReranker`. That is the
    canonical example of one contract composing another at the
    composition root.
    """
    rtype = reranker_config.type.strip().lower()
    if rtype in ("cross_encoder", "cross-encoder"):
        return CrossEncoderReranker(
            scorer=sentence_transformers_scorer(reranker_config.model_name),
            model_name=reranker_config.model_name,
        )
    if rtype == "llm":
        return LLMReranker(
            generation_provider=generation_provider,
            model_name=reranker_config.model_name,
        )
    if rtype in ("placeholder", "none", ""):
        return NotImplementedReranker()
    raise ValueError(
        f"unsupported reranker type={rtype!r}; available: 'cross_encoder', 'llm'. "
        "Add a new `Reranker` implementation under services/llm/application/."
    )


def _build_generation_provider(generation_config: GenerationConfig) -> GenerationProvider:
    """Dispatch on `GenerationConfig.api_type` per architecture.md §Modularity Proof §4."""
    api_type = generation_config.api_type.strip().lower()
    params = generation_config.parameters or {}
    maybe_key = params.get("api_key")
    api_key: str | None = maybe_key if isinstance(maybe_key, str) and maybe_key else None

    if api_type in ("openai", "openai-compatible", "openai_compatible"):
        return OpenAIHttpGenerationProvider(
            endpoint=generation_config.endpoint,
            model_name=generation_config.model_name,
            api_key=api_key,
        )
    if api_type == "anthropic":
        if not api_key:
            raise ValueError(
                "generation.api_type='anthropic' requires "
                "generation.parameters.api_key (Anthropic does not allow "
                "anonymous requests)."
            )
        return AnthropicGenerationProvider(
            endpoint=generation_config.endpoint,
            model_name=generation_config.model_name,
            api_key=api_key,
        )
    if api_type in ("placeholder", "none", ""):
        return NotImplementedGenerationProvider()
    raise ValueError(
        f"unsupported generation api_type={api_type!r}; available: "
        "'openai-compatible', 'anthropic'. "
        "Add a new `GenerationProvider` implementation under services/llm/application/."
    )


def _build_api_key_store() -> ApiKeyStore:
    """Dispatch on `API_KEY_BACKEND` env (infrastructure-level binding).

    `env` (default) — `EnvApiKeyStore` reads `API_KEYS` at boot. Read-only.

    `sqlite` — `SqliteApiKeyStore` reads from the control-plane DB. If
    `API_KEYS` is *also* set, those entries are seeded into the DB (one-shot,
    idempotent) so an operator switching from env to sqlite mid-life doesn't
    lock themselves out.
    """

    backend = os.getenv("API_KEY_BACKEND", "env").strip().lower()
    raw_env_keys = os.getenv("API_KEYS")
    if backend in ("env", ""):
        return EnvApiKeyStore.from_raw(raw_env_keys, now=datetime.now(UTC))
    if backend == "sqlite":
        db_path = _path("CONTROL_PLANE_DB_PATH", DEFAULT_CONTROL_PLANE_DB_PATH)
        store = SqliteApiKeyStore.from_path(db_path)
        store.seed_from_env(raw_env_keys)
        return store
    raise ValueError(
        f"unknown API_KEY_BACKEND={backend!r}; expected 'env' or 'sqlite'."
    )


def _build_api_key_verifier(store: ApiKeyStore) -> ApiKeyVerifier:
    keys = store.list_keys()
    enforce = any(not k.revoked for k in keys)
    if not enforce:
        print(
            "[vestigo] WARNING: no API keys configured; gateway runs in dev mode "
            "and accepts unauthenticated requests."
        )
        return ApiKeyVerifier.disabled()
    return ApiKeyVerifier(resolver=store.as_resolver(), enforce=True)


def _build_audit_logger() -> AuditLogger:
    """Dispatch on `AUDIT_BACKEND` env (infrastructure-level binding).

    `file` (default) — `FileAuditLogger` appends JSONL records at
    `AUDIT_LOG_FILE`. Zero-dep, line-by-line readable in any editor.

    `sqlite` — `SqliteAuditLogger` writes rows to the control-plane DB
    at `CONTROL_PLANE_DB_PATH`. Indexed columns make the audit-log
    viewer filters cheap. Existing JSONL files are *not* migrated;
    `query_logs` against the sqlite backend starts empty.
    """

    backend = os.getenv("AUDIT_BACKEND", "file").strip().lower()
    if backend in ("file", ""):
        audit_log_path = _path("AUDIT_LOG_FILE", DEFAULT_AUDIT_LOG_PATH)
        return FileAuditLogger(audit_log_path)
    if backend == "sqlite":
        db_path = _path("CONTROL_PLANE_DB_PATH", DEFAULT_CONTROL_PLANE_DB_PATH)
        return SqliteAuditLogger.from_path(db_path)
    raise ValueError(
        f"unknown AUDIT_BACKEND={backend!r}; expected 'file' or 'sqlite'."
    )


def _build_config_provider() -> ConfigProvider:
    """Dispatch on `CONFIG_BACKEND` env (infrastructure-level binding).

    `file` (default) — `FileConfigProvider` reads/writes a YAML file at
    `CONFIG_FILE_PATH`. Zero-dep, lives in git for thesis evidence runs.

    `sqlite` — `SqliteConfigProvider` reads/writes the control-plane
    SQLite DB at `CONTROL_PLANE_DB_PATH`. On first run with an empty DB,
    the existing `CONFIG_FILE_PATH` is read for one-shot seeding so an
    operator's tuning survives the file→sqlite hand-off; if no YAML
    exists, the same `DEFAULT_CONFIG` defaults apply.
    """

    backend = os.getenv("CONFIG_BACKEND", "file").strip().lower()
    config_file = _path("CONFIG_FILE_PATH", DEFAULT_CONFIG_PATH)
    if backend in ("file", ""):
        return FileConfigProvider(config_file)
    if backend == "sqlite":
        db_path = _path("CONTROL_PLANE_DB_PATH", DEFAULT_CONTROL_PLANE_DB_PATH)
        return SqliteConfigProvider.from_path(db_path, seed_from_path=config_file)
    raise ValueError(
        f"unknown CONFIG_BACKEND={backend!r}; expected 'file' or 'sqlite'."
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
    if api_type in ("sentence-transformers", "sentence_transformers", "local"):
        # Dimension is discovered lazily via a probe call on first
        # `get_dimension()`; sentence-transformers exposes it directly
        # on the loaded model but reading it requires loading the
        # model — the probe round-trips through `encode()` once and
        # we cache the result.
        return SentenceTransformersEmbeddingProvider(
            encoder=sentence_transformers_encoder(embedding_config.model_name),
            model_name=embedding_config.model_name,
        )
    if api_type in ("placeholder", "none", ""):
        return NotImplementedEmbeddingProvider()
    raise ValueError(
        f"unsupported embedding api_type={api_type!r}; available: "
        "'openai-compatible', 'sentence-transformers'. "
        "Add a new `EmbeddingProvider` implementation under services/llm/application/."
    )


def build_container() -> Container:
    """Bind implementations to each contract.

    Application-level contracts (`Chunker`, `EmbeddingProvider`, ...) dispatch
    on values read from `ConfigProvider` per `docs/architecture.md`
    §Modularity Proof §4. Infrastructure-level contracts (vector store
    backend) dispatch on `.env` values.

    Current status:
      ✓ ConfigProvider       — file (YAML) OR sqlite (env-selected)
      ✓ AuditLogger          — file (JSONL) OR sqlite (env-selected)
      ✓ VectorStoreRepo      — in-memory OR chromadb (env-selected)
      ✓ Chunker              — recursive OR fixed_size (ConfigProvider method dispatch)
      ✓ EmbeddingProvider    — OpenAI HTTP OR sentence-transformers
                                (ConfigProvider api_type dispatch)
      ✓ SourceConnector      — filesystem (env-selected)
      ✓ DocumentConverter    — markitdown (env-selected)
      ✓ Reranker             — cross-encoder OR llm (ConfigProvider type dispatch)
      ✓ GenerationProvider   — OpenAI HTTP OR Anthropic (ConfigProvider api_type dispatch)
    """

    config_provider = _build_config_provider()
    chunking = config_provider.get_chunking_config()
    embedding = config_provider.get_embedding_config()
    reranker_cfg = config_provider.get_reranker_config()
    generation_cfg = config_provider.get_generation_config()

    # Build the generation provider before the reranker so the
    # `LLMReranker` branch can compose it as its judge.
    generation_provider = _build_generation_provider(generation_cfg)

    return Container(
        source_connector=_build_source_connector(),
        document_converter=_build_document_converter(),
        chunker=_build_chunker(chunking),
        embedding_provider=_build_embedding_provider(embedding),
        vector_store=_build_vector_store(),
        reranker=_build_reranker(reranker_cfg, generation_provider=generation_provider),
        generation_provider=generation_provider,
        audit_logger=_build_audit_logger(),
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


SERVICE_CHOICES = ("all", "gateway", "admin", "ingest")


async def serve_all(service: str = "all") -> None:
    """Boot one or all of the three FastAPI services.

    `service` is `all` for the single-process developer workflow
    (`uv run python main.py`) and a specific name when each service
    runs in its own container under Docker Compose. The Container is
    built either way so every service sees a consistent set of bindings.
    """
    load_dotenv()

    container = build_container()
    rag_orchestrator = build_orchestrator(container)
    ingest_orchestrator = build_ingest_orchestrator(container)
    api_key_store = _build_api_key_store()
    api_key_verifier = _build_api_key_verifier(api_key_store)

    apps: dict[str, tuple[object, int, str]] = {
        "gateway": (
            create_gateway_app(rag_orchestrator, api_key_verifier=api_key_verifier),
            _port("API_GATEWAY_PORT", 8000),
            "API Gateway",
        ),
        "ingest": (
            create_ingest_app(
                ingest_orchestrator,
                source_connector=container.source_connector,
                config_provider=container.config_provider,
            ),
            _port("INGEST_API_PORT", 8002),
            "Ingest API",
        ),
        "admin": (
            create_admin_app(
                config_provider=container.config_provider,
                audit_logger=container.audit_logger,
                api_key_store=api_key_store,
                cors_origins=_csv_env("ADMIN_CORS_ORIGINS"),
            ),
            _port("ADMIN_API_PORT", 8001),
            "Admin API",
        ),
    }

    if service == "all":
        await asyncio.gather(
            *(_serve(app, port=port, name=name) for app, port, name in apps.values())
        )
        return

    if service not in apps:
        raise ValueError(
            f"unknown --service {service!r}; expected one of {SERVICE_CHOICES}."
        )
    app, port, name = apps[service]
    await _serve(app, port=port, name=name)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="vestigo-rag-stack composition root.",
    )
    parser.add_argument(
        "--service",
        choices=SERVICE_CHOICES,
        default="all",
        help=(
            "Which FastAPI service to run. `all` (default) boots gateway, "
            "admin, and ingest in one process — the developer workflow. "
            "The Docker Compose containers each pass a specific service "
            "name so each container hosts exactly one service."
        ),
    )
    args = parser.parse_args()

    try:
        asyncio.run(serve_all(service=args.service))
    except KeyboardInterrupt:
        print("[vestigo] shutting down")


if __name__ == "__main__":
    main()
