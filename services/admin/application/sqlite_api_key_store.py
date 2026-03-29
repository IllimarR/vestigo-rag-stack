"""SQLite-backed API-key store — Phase 4."""

from __future__ import annotations

import secrets
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from control_plane import Base, get_engine, make_session_factory
from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from services.admin.application.api_key_store import (
    ApiKeyRecord,
    CreatedApiKey,
    generate_api_key,
    hash_api_key,
)
from services.admin.application.persistence.models import ApiKey

__all__ = ["SqliteApiKeyStore"]


class SqliteApiKeyStore:
    """SQLite-backed implementation of `ApiKeyStore`."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine
        self._session_factory: sessionmaker[Any] = make_session_factory(engine)
        self._lock = threading.Lock()
        Base.metadata.create_all(engine)

    @classmethod
    def from_path(cls, path: Path) -> SqliteApiKeyStore:
        return cls(engine=get_engine(path))

    # --- Lookups (used by gateway via resolver) -------------------------------

    def resolve(self, plaintext: str) -> str | None:
        if not plaintext:
            return None
        candidate_hash = hash_api_key(plaintext)
        with self._session_factory() as session:
            row = session.execute(
                select(ApiKey).where(ApiKey.key_hash == candidate_hash)
            ).scalar_one_or_none()
        if row is None or row.revoked:
            return None
        return str(row.audit_id)

    def as_resolver(self) -> Callable[[str], str | None]:
        return self.resolve

    # --- Reads (used by Admin API) --------------------------------------------

    def list_keys(self) -> list[ApiKeyRecord]:
        with self._session_factory() as session:
            rows = session.execute(select(ApiKey).order_by(ApiKey.created_at)).scalars().all()
        return [
            ApiKeyRecord(
                audit_id=row.audit_id,
                name=row.name,
                created_at=row.created_at,
                revoked=row.revoked,
            )
            for row in rows
        ]

    # --- Writes (used by Admin API) -------------------------------------------

    def create_key(self, *, name: str) -> CreatedApiKey:
        plaintext = generate_api_key()
        key_hash = hash_api_key(plaintext)
        # `audit_id` is the human-readable identifier the operator and audit
        # log see. Random suffix avoids collisions when names clash.
        audit_id = f"key-{secrets.token_hex(6)}"
        now = datetime.now(UTC)
        record = ApiKey(
            audit_id=audit_id,
            key_hash=key_hash,
            name=name,
            created_at=now,
            revoked=False,
        )
        with self._lock, self._session_factory() as session:
            session.add(record)
            session.commit()
        return CreatedApiKey(
            record=ApiKeyRecord(
                audit_id=audit_id,
                name=name,
                created_at=now,
                revoked=False,
            ),
            plaintext=plaintext,
        )

    def revoke_key(self, audit_id: str) -> bool:
        with self._lock, self._session_factory() as session:
            row = session.get(ApiKey, audit_id)
            if row is None or row.revoked:
                return False
            row.revoked = True
            session.commit()
        return True

    # --- Env seed helper ------------------------------------------------------

    def seed_from_env(self, raw: str | None) -> None:
        """One-shot import of `API_KEYS` env entries into the DB.

        Idempotent: the hash is the unique key, so re-seeding the same
        plaintext is a no-op. Each plaintext gets the audit id from the
        `name:key` form when provided. Existing rows are not touched.
        """

        if not raw:
            return
        now = datetime.now(UTC)
        with self._lock, self._session_factory() as session:
            for token in raw.split(","):
                entry = token.strip()
                if not entry:
                    continue
                if ":" in entry:
                    name, key = entry.split(":", 1)
                    key = key.strip()
                    label = name.strip() or f"env-{key[:8]}"
                    audit_id = name.strip() or f"key-{key[:8]}"
                else:
                    key = entry
                    label = f"env-{key[:8]}"
                    audit_id = f"key-{key[:8]}"
                if not key:
                    continue
                key_hash = hash_api_key(key)
                existing = session.execute(
                    select(ApiKey).where(ApiKey.key_hash == key_hash)
                ).scalar_one_or_none()
                if existing is not None:
                    continue
                session.add(
                    ApiKey(
                        audit_id=audit_id,
                        key_hash=key_hash,
                        name=label,
                        created_at=now,
                        revoked=False,
                    )
                )
            session.commit()
