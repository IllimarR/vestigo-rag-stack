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
from fastapi.testclient import TestClient

from contracts import (
    AuditLogger,
    ChatMessage,
    Chunk,
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
    MetadataFilter,
    QueryStatus,
    Reranker,
    RerankerConfig,
    Role,
    SourceConnector,
    TokenUsage,
    VectorStoreRepository,
)
from main import Container, build_container, build_orchestrator
from services.admin.api import create_app as create_admin_app
from services.admin.application.file_config_provider import (
    DEFAULT_CONFIG,
    FileConfigProvider,
)
from services.api_gateway.api import create_app as create_gateway_app
from services.audit.application.file_audit_logger import FileAuditLogger
from services.ingest.api import create_app as create_ingest_app
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
    with pytest.raises(Exception):
        ref.filename = "other.md"


# --- Placeholders still in force for the six Phase 2/3 contracts ------------


def test_placeholders_raise_not_implemented(tmp_path: Path) -> None:
    container = _container_in(tmp_path)

    with pytest.raises(NotImplementedError, match="SourceConnector"):
        container.source_connector.get_source_id()
    with pytest.raises(NotImplementedError, match="DocumentConverter"):
        container.document_converter.supported_types()
    with pytest.raises(NotImplementedError, match="Chunker"):
        container.chunker.chunk(
            "x",
            DocumentReference(
                source_id="s",
                document_id="d",
                filename="f",
                last_modified=datetime.now(),
            ),
            ChunkConfig(method="recursive", size=1, overlap=0),
        )
    with pytest.raises(NotImplementedError, match="EmbeddingProvider"):
        container.embedding_provider.get_dimension()
    with pytest.raises(NotImplementedError, match="Reranker"):
        container.reranker.get_model_id()
    with pytest.raises(NotImplementedError, match="GenerationProvider"):
        container.generation_provider.get_model_id()


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


# --- InMemoryVectorStoreRepository ------------------------------------------


def _chunk(doc_id: str, source_id: str = "src", **metadata: object) -> Chunk:
    return Chunk(
        text=f"chunk for {doc_id}",
        index=0,
        start=0,
        end=10,
        parent=DocumentReference(
            source_id=source_id,
            document_id=doc_id,
            filename=f"{doc_id}.md",
            last_modified=datetime.now(),
        ),
        metadata=dict(metadata),
    )


def test_in_memory_vector_store_create_store_query() -> None:
    store = InMemoryVectorStoreRepository()
    store.create_collection("kb", dimension=3)

    store.store_chunks(
        [
            (_chunk("A", tag="x"), [1.0, 0.0, 0.0]),
            (_chunk("B", tag="y"), [0.9, 0.1, 0.0]),
            (_chunk("C", tag="x"), [0.0, 1.0, 0.0]),
        ],
        collection="kb",
    )

    results = store.query_similar([1.0, 0.0, 0.0], top_k=2, collection="kb")
    assert [r.chunk.parent.document_id for r in results] == ["A", "B"]
    assert results[0].similarity_score == pytest.approx(1.0)


def test_in_memory_vector_store_metadata_filter() -> None:
    store = InMemoryVectorStoreRepository()
    store.create_collection("kb", dimension=3)
    store.store_chunks(
        [
            (_chunk("A", tag="x"), [1.0, 0.0, 0.0]),
            (_chunk("B", tag="y"), [0.9, 0.1, 0.0]),
        ],
        collection="kb",
    )

    results = store.query_similar(
        [1.0, 0.0, 0.0],
        top_k=5,
        collection="kb",
        filters=[MetadataFilter(field="tag", op="eq", value="y")],
    )
    assert [r.chunk.parent.document_id for r in results] == ["B"]


def test_in_memory_vector_store_delete_by_document() -> None:
    store = InMemoryVectorStoreRepository()
    store.create_collection("kb", dimension=2)
    store.store_chunks(
        [
            (_chunk("A"), [1.0, 0.0]),
            (_chunk("B"), [0.0, 1.0]),
        ],
        collection="kb",
    )
    removed = store.delete_by_document("A", "kb")
    assert removed == 1
    assert len(store.query_similar([1.0, 0.0], top_k=5, collection="kb")) == 1


def test_in_memory_vector_store_delete_by_source() -> None:
    store = InMemoryVectorStoreRepository()
    store.create_collection("kb", dimension=2)
    store.store_chunks(
        [
            (_chunk("A", source_id="fs"), [1.0, 0.0]),
            (_chunk("B", source_id="api"), [0.0, 1.0]),
        ],
        collection="kb",
    )
    assert store.delete_by_source("fs", "kb") == 1
    remaining = store.query_similar([0.0, 1.0], top_k=5, collection="kb")
    assert [r.chunk.parent.source_id for r in remaining] == ["api"]


def test_in_memory_vector_store_health_is_healthy() -> None:
    store = InMemoryVectorStoreRepository()
    assert store.health_check().healthy is True


def test_in_memory_vector_store_rejects_dimension_mismatch() -> None:
    store = InMemoryVectorStoreRepository()
    store.create_collection("kb", dimension=3)
    with pytest.raises(ValueError, match="dimension"):
        store.store_chunks([(_chunk("A"), [1.0, 2.0])], collection="kb")


# --- Container + orchestrator ------------------------------------------------


def _container_in(tmp_path: Path) -> Container:
    # Build a container rooted at a temporary directory so tests don't touch
    # the repo's ./config and ./data paths.
    import os as _os

    _os.environ["CONFIG_FILE_PATH"] = str(tmp_path / "config.yaml")
    _os.environ["AUDIT_LOG_FILE"] = str(tmp_path / "audit.log")
    return build_container()


def test_container_builds_with_real_phase_1_bindings(tmp_path: Path) -> None:
    container = _container_in(tmp_path)
    # Real implementations where Phase 1 delivered them.
    assert isinstance(container.config_provider, FileConfigProvider)
    assert isinstance(container.audit_logger, FileAuditLogger)
    assert isinstance(container.vector_store, InMemoryVectorStoreRepository)


def test_orchestrator_still_stub(tmp_path: Path) -> None:
    container = _container_in(tmp_path)
    orchestrator = build_orchestrator(container)
    with pytest.raises(NotImplementedError, match="RAGPipelineOrchestrator"):
        orchestrator.run(
            [ChatMessage(role=Role.USER, content="hi")], api_key_id="test"
        )


# --- FastAPI health + OpenAPI -----------------------------------------------


def test_api_gateway_health(tmp_path: Path) -> None:
    container = _container_in(tmp_path)
    app = create_gateway_app(build_orchestrator(container))
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "api_gateway"


def test_ingest_api_health() -> None:
    with TestClient(create_ingest_app()) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "ingest"


def test_admin_api_health(tmp_path: Path) -> None:
    container = _container_in(tmp_path)
    app = create_admin_app(
        config_provider=container.config_provider,
        audit_logger=container.audit_logger,
    )
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "admin"


def test_openapi_docs_available(tmp_path: Path) -> None:
    container = _container_in(tmp_path)
    apps = [
        create_gateway_app(build_orchestrator(container)),
        create_ingest_app(),
        create_admin_app(
            config_provider=container.config_provider,
            audit_logger=container.audit_logger,
        ),
    ]
    for app in apps:
        with TestClient(app) as client:
            assert client.get("/openapi.json").status_code == 200
            assert client.get("/docs").status_code == 200
