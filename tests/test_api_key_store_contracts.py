"""Contract-compliance suite for every `ApiKeyStore` implementation.

The env backend is read-only — create/revoke raise — so the matching
tests use `pytest.skip` on env. The shared behaviour (resolve, list,
plaintext-once-only, revoked-keys-return-None) runs against every
backend.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import pytest

from services.admin.application.api_key_store import (
    ApiKeyStore,
    EnvApiKeyStore,
)
from services.admin.application.sqlite_api_key_store import SqliteApiKeyStore

StoreFactory = Callable[[Path], ApiKeyStore]


def _env_store(_tmp: Path) -> ApiKeyStore:
    return EnvApiKeyStore.from_raw(
        "sk-test1,prod:sk-prod1",
        now=datetime(2026, 4, 25, 10, 0, 0),
    )


def _sqlite_store(tmp_path: Path) -> ApiKeyStore:
    store = SqliteApiKeyStore.from_path(tmp_path / "control_plane.db")
    store.seed_from_env("sk-test1,prod:sk-prod1")
    return store


_STORES: dict[str, StoreFactory] = {
    "env": _env_store,
    "sqlite": _sqlite_store,
}


@pytest.fixture(params=sorted(_STORES), ids=sorted(_STORES))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[ApiKeyStore]:
    factory = _STORES[request.param]
    yield factory(tmp_path)


# --- resolve --------------------------------------------------------------


def test_resolve_known_key(store: ApiKeyStore) -> None:
    assert store.resolve("sk-test1") is not None


def test_resolve_named_key_returns_configured_audit_id(store: ApiKeyStore) -> None:
    assert store.resolve("sk-prod1") == "prod"


def test_resolve_unknown_returns_none(store: ApiKeyStore) -> None:
    assert store.resolve("sk-bogus") is None


def test_resolve_empty_string_returns_none(store: ApiKeyStore) -> None:
    assert store.resolve("") is None


# --- list_keys ------------------------------------------------------------


def test_list_keys_includes_seeded_entries(store: ApiKeyStore) -> None:
    records = store.list_keys()
    audit_ids = {r.audit_id for r in records}
    assert "prod" in audit_ids
    # second seeded entry has an env-derived id like "key-sk-test1"[:8]
    assert any(r.audit_id.startswith("key-sk-t") for r in records)


# --- as_resolver ----------------------------------------------------------


def test_as_resolver_returns_same_audit_id(store: ApiKeyStore) -> None:
    resolver = store.as_resolver()
    assert resolver("sk-prod1") == "prod"
    assert resolver("sk-bogus") is None


# --- Writable backends only (sqlite) -------------------------------------


def _writable_only(store: ApiKeyStore) -> None:
    if isinstance(store, EnvApiKeyStore):
        pytest.skip("env-backed store is read-only by design")


def test_create_returns_plaintext_once_and_resolves(store: ApiKeyStore) -> None:
    _writable_only(store)
    created = store.create_key(name="ingest-bot")
    assert created.plaintext  # operator's one chance to copy
    assert created.record.name == "ingest-bot"
    assert created.record.revoked is False

    # Resolving with the plaintext returns the new audit id.
    assert store.resolve(created.plaintext) == created.record.audit_id

    # The created key is visible in list_keys.
    audit_ids = {r.audit_id for r in store.list_keys()}
    assert created.record.audit_id in audit_ids


def test_revoke_key_blocks_further_resolution(store: ApiKeyStore) -> None:
    _writable_only(store)
    created = store.create_key(name="ephemeral")
    plaintext = created.plaintext

    assert store.revoke_key(created.record.audit_id) is True
    assert store.resolve(plaintext) is None

    # Revoking again is idempotent-ish: returns False, no error.
    assert store.revoke_key(created.record.audit_id) is False


def test_revoke_unknown_returns_false(store: ApiKeyStore) -> None:
    _writable_only(store)
    assert store.revoke_key("never-existed") is False


def test_revoked_key_still_listed_for_history(store: ApiKeyStore) -> None:
    _writable_only(store)
    created = store.create_key(name="historical")
    store.revoke_key(created.record.audit_id)

    matching = [r for r in store.list_keys() if r.audit_id == created.record.audit_id]
    assert len(matching) == 1
    assert matching[0].revoked is True


# --- Env-specific -------------------------------------------------------


def test_env_store_mutation_raises() -> None:
    store = EnvApiKeyStore.from_raw("sk-test1", now=datetime(2026, 4, 25, 10, 0, 0))
    with pytest.raises(RuntimeError, match="read-only"):
        store.create_key(name="x")
    with pytest.raises(RuntimeError, match="read-only"):
        store.revoke_key("anything")


def test_env_store_empty_raw_is_resolveless() -> None:
    store = EnvApiKeyStore.from_raw(None, now=datetime(2026, 4, 25, 10, 0, 0))
    assert store.list_keys() == []
    assert store.resolve("any") is None


# --- Sqlite-specific: hash never stored as plaintext ---------------------


def test_sqlite_seed_is_idempotent(tmp_path: Path) -> None:
    store = SqliteApiKeyStore.from_path(tmp_path / "control_plane.db")
    store.seed_from_env("sk-x,sk-y")
    first = sorted(r.audit_id for r in store.list_keys())
    store.seed_from_env("sk-x,sk-y")
    second = sorted(r.audit_id for r in store.list_keys())
    assert first == second


def test_sqlite_plaintext_is_not_persisted(tmp_path: Path) -> None:
    """A direct read of the row's hash column must never equal the
    plaintext — the only proof that the key isn't stored in the clear."""

    from sqlalchemy import select

    from services.admin.application.persistence.models import ApiKey

    db_path = tmp_path / "control_plane.db"
    store = SqliteApiKeyStore.from_path(db_path)
    created = store.create_key(name="hash-test")

    with store._session_factory() as session:
        rows = session.execute(select(ApiKey)).scalars().all()
    by_id = {r.audit_id: r for r in rows}
    assert created.record.audit_id in by_id
    row = by_id[created.record.audit_id]
    assert row.key_hash != created.plaintext
    assert len(row.key_hash) == 64  # sha256 hex
