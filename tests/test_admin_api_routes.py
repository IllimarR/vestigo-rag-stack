"""Tests for the Admin API's Phase 4 routes.

Backends-as-fixtures (file ConfigProvider + FileAuditLogger + env
ApiKeyStore) keep the test surface independent of SQLite, but the
sqlite providers slot in via the same `create_app` boundary and are
covered by their own parameterized contract suites.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.admin.api import create_app
from services.admin.application.api_key_store import EnvApiKeyStore
from services.admin.application.file_config_provider import FileConfigProvider
from services.admin.application.sqlite_api_key_store import SqliteApiKeyStore
from services.audit.application.file_audit_logger import FileAuditLogger


@pytest.fixture(autouse=True)
def _clear_admin_key_env() -> Iterator[None]:
    """Each test runs with admin auth disabled by default; tests that
    need it set the env explicitly. The autouse fixture ensures no
    bleed-through between tests."""

    prev = os.environ.pop("ADMIN_API_KEY", None)
    try:
        yield
    finally:
        if prev is not None:
            os.environ["ADMIN_API_KEY"] = prev


def _file_app(tmp_path: Path) -> tuple[TestClient, FileConfigProvider, FileAuditLogger]:
    cp = FileConfigProvider(tmp_path / "config.yaml")
    al = FileAuditLogger(tmp_path / "audit.log")
    store = EnvApiKeyStore.from_raw(None, now=datetime(2026, 4, 25, 10, 0, 0))
    app = create_app(config_provider=cp, audit_logger=al, api_key_store=store)
    return TestClient(app), cp, al


def _sqlite_app(
    tmp_path: Path,
) -> tuple[TestClient, FileConfigProvider, FileAuditLogger, SqliteApiKeyStore]:
    cp = FileConfigProvider(tmp_path / "config.yaml")
    al = FileAuditLogger(tmp_path / "audit.log")
    store = SqliteApiKeyStore.from_path(tmp_path / "control_plane.db")
    app = create_app(config_provider=cp, audit_logger=al, api_key_store=store)
    return TestClient(app), cp, al, store


# --- Config endpoints --------------------------------------------------------


def test_get_config_returns_seeded_defaults(tmp_path: Path) -> None:
    client, _, _ = _file_app(tmp_path)
    response = client.get("/v1/config")
    assert response.status_code == 200
    body = response.json()
    assert body["chunking"]["method"] == "recursive"
    assert "{context}" in body["rag_prompt_template"]
    assert body["default_collection"] == "default"


def test_put_embedding_persists_and_audits(tmp_path: Path) -> None:
    client, cp, al = _file_app(tmp_path)
    response = client.put(
        "/v1/config/embedding",
        json={
            "endpoint": "http://e",
            "api_type": "openai-compatible",
            "model_name": "e5-large",
            "parameters": {},
        },
    )
    assert response.status_code == 200
    refreshed = cp.get_embedding_config()
    assert refreshed.model_name == "e5-large"
    audit_rows = al.query_logs(filters={"type": "admin_event"})
    assert any("config.embedding.set" in r.get("action", "") for r in audit_rows)


def test_put_chunking_validates_body(tmp_path: Path) -> None:
    client, _, _ = _file_app(tmp_path)
    # Body is missing the required size/overlap fields.
    response = client.put("/v1/config/chunking", json={"method": "recursive"})
    assert response.status_code == 400


def test_put_rag_prompt_template(tmp_path: Path) -> None:
    client, cp, _ = _file_app(tmp_path)
    response = client.put("/v1/config/rag-prompt-template", json={"template": "NEW: {question}"})
    assert response.status_code == 200
    assert cp.get_rag_prompt_template() == "NEW: {question}"


def test_put_default_collection(tmp_path: Path) -> None:
    client, cp, _ = _file_app(tmp_path)
    response = client.put("/v1/config/default-collection", json={"collection": "kb-prod"})
    assert response.status_code == 200
    assert cp.get_default_collection() == "kb-prod"


def test_put_default_collection_rejects_empty(tmp_path: Path) -> None:
    client, _, _ = _file_app(tmp_path)
    response = client.put("/v1/config/default-collection", json={"collection": ""})
    assert response.status_code == 400


# --- Audit endpoint ----------------------------------------------------------


def test_get_audit_returns_recent_events(tmp_path: Path) -> None:
    client, _, al = _file_app(tmp_path)
    al.log_admin_event(action="seed", actor="admin", timestamp=datetime(2026, 4, 25, 10, 0, 0))
    response = client.get("/v1/audit")
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 100
    assert any(row.get("action") == "seed" for row in body["results"])


def test_get_audit_filters_by_type(tmp_path: Path) -> None:
    client, _, al = _file_app(tmp_path)
    al.log_admin_event(action="seed", actor="admin", timestamp=datetime(2026, 4, 25, 10, 0, 0))
    response = client.get("/v1/audit", params={"type": "admin_event"})
    body = response.json()
    assert all(row.get("type") == "admin_event" for row in body["results"])


# --- API key endpoints -------------------------------------------------------


def test_list_keys_returns_seeded_env_entries(tmp_path: Path) -> None:
    cp = FileConfigProvider(tmp_path / "config.yaml")
    al = FileAuditLogger(tmp_path / "audit.log")
    store = EnvApiKeyStore.from_raw("sk-x", now=datetime(2026, 4, 25, 10, 0, 0))
    app = create_app(config_provider=cp, audit_logger=al, api_key_store=store)
    client = TestClient(app)
    response = client.get("/v1/api-keys")
    body = response.json()
    assert len(body["results"]) == 1


def test_create_key_returns_plaintext_once(tmp_path: Path) -> None:
    client, _, al, _ = _sqlite_app(tmp_path)
    response = client.post("/v1/api-keys", json={"name": "ingest-bot"})
    assert response.status_code == 200
    body = response.json()
    assert body["plaintext"]
    assert body["name"] == "ingest-bot"
    assert body["audit_id"].startswith("key-")
    audit_rows = al.query_logs(filters={"type": "admin_event"})
    assert any("api_key.create" in r.get("action", "") for r in audit_rows)


def test_create_key_rejects_blank_name(tmp_path: Path) -> None:
    client, _, _, _ = _sqlite_app(tmp_path)
    response = client.post("/v1/api-keys", json={"name": "   "})
    assert response.status_code == 400


def test_create_key_blocked_on_env_backend(tmp_path: Path) -> None:
    client, _, _ = _file_app(tmp_path)  # env-backed by default
    response = client.post("/v1/api-keys", json={"name": "x"})
    assert response.status_code == 409


def test_revoke_key_blocks_future_resolution(tmp_path: Path) -> None:
    client, _, _, store = _sqlite_app(tmp_path)
    create = client.post("/v1/api-keys", json={"name": "ephemeral"})
    plaintext = create.json()["plaintext"]
    audit_id = create.json()["audit_id"]

    response = client.delete(f"/v1/api-keys/{audit_id}")
    assert response.status_code == 200
    assert store.resolve(plaintext) is None


def test_revoke_unknown_returns_404(tmp_path: Path) -> None:
    client, _, _, _ = _sqlite_app(tmp_path)
    response = client.delete("/v1/api-keys/never-existed")
    assert response.status_code == 404


# --- Auth --------------------------------------------------------------------


def test_admin_auth_enforced_when_env_set(tmp_path: Path) -> None:
    os.environ["ADMIN_API_KEY"] = "expected-secret"
    client, _, _ = _file_app(tmp_path)

    rejected = client.get("/v1/config")
    assert rejected.status_code == 401

    accepted = client.get(
        "/v1/config",
        headers={"Authorization": "Bearer expected-secret"},
    )
    assert accepted.status_code == 200

    wrong = client.get("/v1/config", headers={"Authorization": "Bearer wrong"})
    assert wrong.status_code == 401
