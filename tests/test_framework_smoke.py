"""Smoke test — proves the Phase 1 framework skeleton wires up.

Specifically verifies:
  1. All nine contract `Protocol` classes import.
  2. All DTOs import and are frozen (mutation raises).
  3. Each placeholder class satisfies its contract via `isinstance` check
     against a runtime-checkable Protocol pattern — we do this by calling a
     method and asserting the expected `NotImplementedError`.
  4. The `Container` composes cleanly via `build_container`.
  5. The `RAGPipelineOrchestrator` constructs and raises `NotImplementedError`
     from `run` with a message that names contracts.
  6. Each of the three FastAPI apps returns 200 on `/health`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from main import build_container, build_orchestrator
from services.admin.api import create_app as create_admin_app
from services.api_gateway.api import create_app as create_gateway_app
from services.ingest.api import create_app as create_ingest_app
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
from contracts.dto import DocumentReference


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
    from datetime import datetime

    ref = DocumentReference(
        source_id="s", document_id="d", filename="f.md", last_modified=datetime.now()
    )
    with pytest.raises(Exception):  # Pydantic raises ValidationError on frozen mutation
        ref.filename = "other.md"


def test_container_builds_with_all_placeholders() -> None:
    container = build_container()
    # Every field is present and non-None.
    assert container.source_connector is not None
    assert container.document_converter is not None
    assert container.chunker is not None
    assert container.embedding_provider is not None
    assert container.vector_store is not None
    assert container.reranker is not None
    assert container.generation_provider is not None
    assert container.audit_logger is not None
    assert container.config_provider is not None


def test_placeholders_raise_not_implemented() -> None:
    container = build_container()

    with pytest.raises(NotImplementedError, match="SourceConnector"):
        container.source_connector.get_source_id()

    with pytest.raises(NotImplementedError, match="DocumentConverter"):
        container.document_converter.supported_types()

    with pytest.raises(NotImplementedError, match="EmbeddingProvider"):
        container.embedding_provider.get_dimension()

    with pytest.raises(NotImplementedError, match="Reranker"):
        container.reranker.get_model_id()

    with pytest.raises(NotImplementedError, match="GenerationProvider"):
        container.generation_provider.get_model_id()

    with pytest.raises(NotImplementedError, match="VectorStoreRepository"):
        container.vector_store.list_collections()

    with pytest.raises(NotImplementedError, match="AuditLogger"):
        container.audit_logger.log_admin_event(
            action="test", actor="test", timestamp=__import__("datetime").datetime.now()
        )

    with pytest.raises(NotImplementedError, match="ConfigProvider"):
        container.config_provider.get_default_collection()


def test_vector_store_health_reports_unhealthy_without_raising() -> None:
    # Special case: health_check must not raise — /health endpoints depend on it.
    container = build_container()
    status = container.vector_store.health_check()
    assert status.healthy is False
    assert status.detail is not None


def test_orchestrator_constructs_and_raises_on_run() -> None:
    container = build_container()
    orchestrator = build_orchestrator(container)
    with pytest.raises(NotImplementedError, match="RAGPipelineOrchestrator"):
        orchestrator.run([], api_key_id="test")


def test_api_gateway_health() -> None:
    container = build_container()
    orchestrator = build_orchestrator(container)
    app = create_gateway_app(orchestrator)
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "api_gateway"


def test_ingest_api_health() -> None:
    app = create_ingest_app()
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "ingest"


def test_admin_api_health() -> None:
    container = build_container()
    app = create_admin_app(
        config_provider=container.config_provider,
        audit_logger=container.audit_logger,
    )
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "admin"


def test_openapi_docs_available() -> None:
    """Each external HTTP boundary ships OpenAPI docs."""
    container = build_container()
    orchestrator = build_orchestrator(container)

    for app in [
        create_gateway_app(orchestrator),
        create_ingest_app(),
        create_admin_app(
            config_provider=container.config_provider,
            audit_logger=container.audit_logger,
        ),
    ]:
        with TestClient(app) as client:
            assert client.get("/openapi.json").status_code == 200
            assert client.get("/docs").status_code == 200
