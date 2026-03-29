"""Tests for the Ingest API's Phase 4 push routes.

Uses in-memory adapters (`ApiPushSourceConnector` + a fake orchestrator)
so the test boots without touching real disk or external services.
"""

from __future__ import annotations

import base64
import os
from collections.abc import Iterator
from typing import Any

import pytest
from contracts import ChangeEvent, ChangeType
from fastapi.testclient import TestClient

from services.admin.application.file_config_provider import FileConfigProvider
from services.ingest.api import create_app
from services.ingest.application.api_push_source_connector import (
    ApiPushSourceConnector,
)
from services.ingest.application.ingest_pipeline_orchestrator import IngestResult


class _FakeOrchestrator:
    """Records calls and returns canned IngestResults so the route can
    be tested end-to-end without standing up the full ingest pipeline."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = IngestResult(ingested=1)

    def process_changes(
        self,
        events: list[ChangeEvent],
        *,
        collection: str,
    ) -> IngestResult:
        self.calls.append({"events": list(events), "collection": collection})
        return self.result


@pytest.fixture(autouse=True)
def _clear_ingest_key_env() -> Iterator[None]:
    prev = os.environ.pop("INGEST_API_KEY", None)
    try:
        yield
    finally:
        if prev is not None:
            os.environ["INGEST_API_KEY"] = prev


def _client(tmp_path: pytest.TempPathFactory) -> tuple[
    TestClient, _FakeOrchestrator, ApiPushSourceConnector
]:
    connector = ApiPushSourceConnector(source_id="api")
    orchestrator = _FakeOrchestrator()
    config_provider = FileConfigProvider(tmp_path / "config.yaml")  # type: ignore[operator]
    app = create_app(
        orchestrator,  # type: ignore[arg-type]
        source_connector=connector,
        config_provider=config_provider,
    )
    return TestClient(app), orchestrator, connector


def _b64(content: bytes) -> str:
    return base64.b64encode(content).decode("ascii")


# --- Single-document push ---------------------------------------------------


def test_push_added_invokes_orchestrator_with_added_event(tmp_path: Any) -> None:
    client, orchestrator, _ = _client(tmp_path)
    response = client.post(
        "/v1/documents",
        json={
            "document_id": "doc-1",
            "filename": "doc-1.md",
            "file_type": "md",
            "content_base64": _b64(b"# Hello"),
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["document_id"] == "doc-1"
    assert body["change_type"] == "added"
    assert body["result"] == "ingested"
    assert body["collection"] == "default"
    assert len(orchestrator.calls) == 1
    event = orchestrator.calls[0]["events"][0]
    assert event.change_type is ChangeType.ADDED


def test_push_modified_after_added(tmp_path: Any) -> None:
    client, orchestrator, _ = _client(tmp_path)
    client.post(
        "/v1/documents",
        json={
            "document_id": "doc-1",
            "filename": "doc-1.md",
            "file_type": "md",
            "content_base64": _b64(b"v1"),
        },
    )

    response = client.post(
        "/v1/documents",
        json={
            "document_id": "doc-1",
            "filename": "doc-1.md",
            "file_type": "md",
            "content_base64": _b64(b"v2"),
        },
    )
    assert response.status_code == 200
    assert response.json()["change_type"] == "modified"
    assert orchestrator.calls[-1]["events"][0].change_type is ChangeType.MODIFIED


def test_push_deletion_does_not_require_content(tmp_path: Any) -> None:
    client, orchestrator, _ = _client(tmp_path)
    orchestrator.result = IngestResult(deleted=1)

    response = client.post(
        "/v1/documents",
        json={
            "document_id": "doc-1",
            "filename": "doc-1.md",
            "change_type": "deleted",
        },
    )
    assert response.status_code == 200
    assert response.json()["change_type"] == "deleted"
    assert response.json()["result"] == "deleted"


def test_collection_override_takes_precedence(tmp_path: Any) -> None:
    client, orchestrator, _ = _client(tmp_path)
    client.post(
        "/v1/documents",
        json={
            "document_id": "doc-1",
            "filename": "doc-1.md",
            "file_type": "md",
            "content_base64": _b64(b"x"),
            "collection": "kb-prod",
        },
    )
    assert orchestrator.calls[-1]["collection"] == "kb-prod"


# --- Validation -------------------------------------------------------------


def test_missing_document_id_rejected(tmp_path: Any) -> None:
    client, _, _ = _client(tmp_path)
    response = client.post(
        "/v1/documents",
        json={"filename": "x.md", "file_type": "md", "content_base64": _b64(b"x")},
    )
    assert response.status_code == 400


def test_bad_base64_rejected(tmp_path: Any) -> None:
    client, _, _ = _client(tmp_path)
    response = client.post(
        "/v1/documents",
        json={
            "document_id": "doc-1",
            "filename": "doc-1.md",
            "file_type": "md",
            "content_base64": "!!!not-base64!!!",
        },
    )
    assert response.status_code == 400


def test_bad_change_type_rejected(tmp_path: Any) -> None:
    client, _, _ = _client(tmp_path)
    response = client.post(
        "/v1/documents",
        json={
            "document_id": "doc-1",
            "filename": "doc-1.md",
            "file_type": "md",
            "content_base64": _b64(b"x"),
            "change_type": "amended",
        },
    )
    assert response.status_code == 400


# --- Batch -----------------------------------------------------------------


def test_batch_processes_multiple_documents(tmp_path: Any) -> None:
    client, orchestrator, _ = _client(tmp_path)
    orchestrator.result = IngestResult(ingested=2)

    response = client.post(
        "/v1/documents/batch",
        json={
            "documents": [
                {
                    "document_id": "doc-1",
                    "filename": "doc-1.md",
                    "file_type": "md",
                    "content_base64": _b64(b"hi"),
                },
                {
                    "document_id": "doc-2",
                    "filename": "doc-2.md",
                    "file_type": "md",
                    "content_base64": _b64(b"hi"),
                },
            ],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ingested"] == 2
    assert len(body["documents"]) == 2
    assert len(orchestrator.calls[0]["events"]) == 2


def test_batch_rejects_empty_list(tmp_path: Any) -> None:
    client, _, _ = _client(tmp_path)
    response = client.post("/v1/documents/batch", json={"documents": []})
    assert response.status_code == 400


# --- Auth -----------------------------------------------------------------


def test_ingest_auth_enforced_when_env_set(tmp_path: Any) -> None:
    os.environ["INGEST_API_KEY"] = "expected-secret"
    client, _, _ = _client(tmp_path)
    payload = {
        "document_id": "doc-1",
        "filename": "doc-1.md",
        "file_type": "md",
        "content_base64": _b64(b"x"),
    }

    rejected = client.post("/v1/documents", json=payload)
    assert rejected.status_code == 401

    accepted = client.post(
        "/v1/documents",
        json=payload,
        headers={"Authorization": "Bearer expected-secret"},
    )
    assert accepted.status_code == 200


# --- Filesystem backend rejects push ---------------------------------------


def test_push_rejected_when_backend_is_not_api(tmp_path: Any) -> None:
    """When SOURCE_CONNECTORS=filesystem, the push routes refuse to
    accept uploads rather than silently dropping them."""

    from services.ingest.application.filesystem_source_connector import (
        FilesystemSourceConnector,
    )

    orchestrator = _FakeOrchestrator()
    fs_root = tmp_path / "fs"
    fs_root.mkdir()
    connector = FilesystemSourceConnector(root=fs_root)
    config_provider = FileConfigProvider(tmp_path / "config.yaml")
    app = create_app(
        orchestrator,  # type: ignore[arg-type]
        source_connector=connector,
        config_provider=config_provider,
    )
    client = TestClient(app)

    response = client.post(
        "/v1/documents",
        json={
            "document_id": "doc-1",
            "filename": "doc-1.md",
            "file_type": "md",
            "content_base64": _b64(b"x"),
        },
    )
    assert response.status_code == 409
