"""Smoke test — Phase 1 framework skeleton + three real adapters.

Covers:
  1. All nine contract `Protocol` classes import.
  2. DTOs are frozen.
  3. Six contracts still have NotImplementedError-raising placeholders.
  4. Three contracts now have functional file/in-memory implementations:
     ConfigProvider (YAML), AuditLogger (JSONL), VectorStoreRepository
     (in-memory cosine).
  5. `Container` composes cleanly and `RAGPipelineOrchestrator` constructs.
  6. All three FastAPI apps return 200 on `/health`.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from contracts import (
    AuditLogger,
    ChunkConfig,
    Chunker,
    ConfigProvider,
    DocumentConverter,
    DocumentReference,
    EmbeddingConfig,
    EmbeddingProvider,
    GenerationConfig,
    GenerationProvider,
    IngestEventType,
    QueryStatus,
    Reranker,
    RerankerConfig,
    SourceConnector,
    TokenUsage,
    VectorStoreRepository,
)
from fastapi.testclient import TestClient
from pydantic import ValidationError

from main import (
    Container,
    build_container,
    build_ingest_orchestrator,
    build_orchestrator,
)
from services.admin.api import create_app as create_admin_app
from services.admin.application.api_key_store import EnvApiKeyStore
from services.admin.application.file_config_provider import (
    DEFAULT_CONFIG,
    FileConfigProvider,
)
from services.api_gateway.api import create_app as create_gateway_app
from services.audit.application.file_audit_logger import FileAuditLogger
from services.ingest.api import create_app as create_ingest_app
from services.ingest.application.filesystem_source_connector import (
    FilesystemSourceConnector,
)
from services.ingest.application.markitdown_document_converter import (
    MarkitdownDocumentConverter,
)
from services.ingest.application.recursive_chunker import RecursiveChunker
from services.llm.application.cross_encoder_reranker import CrossEncoderReranker
from services.llm.application.openai_http_embedding_provider import (
    OpenAIHttpEmbeddingProvider,
)
from services.llm.application.openai_http_generation_provider import (
    OpenAIHttpGenerationProvider,
)
from services.vector_store.application.in_memory_vector_store import (
    InMemoryVectorStoreRepository,
)

# --- Contract + DTO smoke ----------------------------------------------------


def test_all_nine_contracts_importable() -> None:
    contracts = [
        SourceConnector,
        DocumentConverter,
        Chunker,
        EmbeddingProvider,
        VectorStoreRepository,
        Reranker,
        GenerationProvider,
        AuditLogger,
        ConfigProvider,
    ]
    assert len(contracts) == 9


def test_dtos_are_frozen() -> None:
    ref = DocumentReference(
        source_id="s", document_id="d", filename="f.md", last_modified=datetime.now()
    )
    with pytest.raises(ValidationError):
        ref.filename = "other.md"


# --- Placeholders still in force for the six Phase 2/3 contracts ------------


# Every contract now has a real binding; the historical "placeholders
# still raise" smoke test is gone. Per-contract behaviour lives in the
# parameterized suites under `tests/test_*_contracts.py`.


# --- FileConfigProvider ------------------------------------------------------


def test_file_config_provider_bootstraps_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    provider = FileConfigProvider(path)
    assert path.exists()

    chunking = provider.get_chunking_config()
    assert chunking.method == DEFAULT_CONFIG["chunking"]["method"]
    assert chunking.size == DEFAULT_CONFIG["chunking"]["size"]

    assert provider.get_default_collection() == "default"
    assert "helpful assistant" in provider.get_rag_prompt_template()


def test_file_config_provider_write_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    provider = FileConfigProvider(path)

    provider.set_default_collection("corporate-docs")
    provider.set_chunking_config(
        ChunkConfig(method="semantic", size=800, overlap=100)
    )
    provider.set_rag_prompt_template("NEW TEMPLATE: {question}")
    provider.set_embedding_config(
        EmbeddingConfig(
            endpoint="http://example/e",
            api_type="openai-compatible",
            model_name="e5-base",
        )
    )
    provider.set_reranker_config(
        RerankerConfig(type="cross_encoder", endpoint=None, model_name="bge")
    )
    provider.set_generation_config(
        GenerationConfig(
            endpoint="http://example/g",
            api_type="anthropic",
            model_name="claude",
        )
    )

    # Fresh reader sees the persisted state (no cache).
    fresh = FileConfigProvider(path)
    assert fresh.get_default_collection() == "corporate-docs"
    assert fresh.get_chunking_config().method == "semantic"
    assert fresh.get_rag_prompt_template() == "NEW TEMPLATE: {question}"
    assert fresh.get_embedding_config().model_name == "e5-base"
    assert fresh.get_reranker_config().model_name == "bge"
    assert fresh.get_generation_config().api_type == "anthropic"


# --- FileAuditLogger ---------------------------------------------------------


def test_file_audit_logger_roundtrip(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.log"
    logger = FileAuditLogger(log_path)

    now = datetime(2026, 4, 25, 10, 0, 0)
    logger.log_admin_event(action="api_key.create", actor="admin", timestamp=now)
    logger.log_ingest_event(
        reference=DocumentReference(
            source_id="fs", document_id="1", filename="a.md", last_modified=now
        ),
        event_type=IngestEventType.INGESTED,
        chunk_count=5,
        timestamp=now,
    )
    logger.log_query(
        query="what",
        retrieved=[],
        response_text="a response",
        usage=TokenUsage(prompt_tokens=10, completion_tokens=20),
        timestamp=now,
        api_key_id="key-1",
        status=QueryStatus.SUCCESS,
    )

    all_entries = logger.query_logs(filters={})
    assert len(all_entries) == 3

    queries_only = logger.query_logs(filters={"type": "query"})
    assert len(queries_only) == 1
    assert queries_only[0]["api_key_id"] == "key-1"

    key_filter = logger.query_logs(filters={"api_key_id": "key-1"})
    assert len(key_filter) == 1


# Per-backend `VectorStoreRepository` behavior is covered in
# `tests/test_vector_store_contracts.py` (parameterized over every backend).


# --- Container + orchestrator ------------------------------------------------


def _container_in(tmp_path: Path) -> Container:
    # Build a container rooted at a temporary directory so tests don't touch
    # the repo's ./config and ./data paths.
    import os as _os

    _os.environ["CONFIG_FILE_PATH"] = str(tmp_path / "config.yaml")
    _os.environ["AUDIT_LOG_FILE"] = str(tmp_path / "audit.log")
    # Smoke tests assert the default (in-memory) binding. Contract tests in
    # tests/test_vector_store_contracts.py cover chromadb explicitly.
    _os.environ["VECTOR_STORE_BACKEND"] = "in_memory"
    incoming = tmp_path / "incoming"
    incoming.mkdir(parents=True, exist_ok=True)
    _os.environ["INGEST_FILESYSTEM_ROOT"] = str(incoming)
    return build_container()


def test_container_builds_with_real_bindings(tmp_path: Path) -> None:
    container = _container_in(tmp_path)
    # Phase 1 bindings.
    assert isinstance(container.config_provider, FileConfigProvider)
    assert isinstance(container.audit_logger, FileAuditLogger)
    assert isinstance(container.vector_store, InMemoryVectorStoreRepository)
    # Phase 2 bindings (dispatch from the seeded default config).
    assert isinstance(container.chunker, RecursiveChunker)
    assert isinstance(container.embedding_provider, OpenAIHttpEmbeddingProvider)
    assert isinstance(container.source_connector, FilesystemSourceConnector)
    assert isinstance(container.document_converter, MarkitdownDocumentConverter)
    # Phase 3 bindings.
    assert isinstance(container.reranker, CrossEncoderReranker)
    assert isinstance(container.generation_provider, OpenAIHttpGenerationProvider)


# Orchestrator behaviour is covered in detail by
# `tests/test_rag_pipeline_orchestrator.py` with in-test fakes; the smoke
# test layer no longer asserts NotImplementedError on it because the
# orchestrator is no longer a stub.


# --- FastAPI health + OpenAPI -----------------------------------------------


def test_api_gateway_health(tmp_path: Path) -> None:
    container = _container_in(tmp_path)
    app = create_gateway_app(build_orchestrator(container))
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "api_gateway"


def test_ingest_api_health(tmp_path: Path) -> None:
    container = _container_in(tmp_path)
    app = create_ingest_app(build_ingest_orchestrator(container))
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "ingest"


def _empty_api_key_store() -> EnvApiKeyStore:
    return EnvApiKeyStore.from_raw(None, now=datetime(2026, 4, 25, 10, 0, 0))


def test_admin_api_health(tmp_path: Path) -> None:
    container = _container_in(tmp_path)
    app = create_admin_app(
        config_provider=container.config_provider,
        audit_logger=container.audit_logger,
        api_key_store=_empty_api_key_store(),
    )
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "admin"


def test_openapi_docs_available(tmp_path: Path) -> None:
    container = _container_in(tmp_path)
    apps = [
        create_gateway_app(build_orchestrator(container)),
        create_ingest_app(build_ingest_orchestrator(container)),
        create_admin_app(
            config_provider=container.config_provider,
            audit_logger=container.audit_logger,
            api_key_store=_empty_api_key_store(),
        ),
    ]
    for app in apps:
        with TestClient(app) as client:
            assert client.get("/openapi.json").status_code == 200
            assert client.get("/docs").status_code == 200
