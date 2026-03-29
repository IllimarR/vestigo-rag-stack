"""API-key store — admin-owned credential persistence.

The admin service owns API keys. Two pieces depend on this:

  * The Admin API itself, which exposes CRUD routes (list, create,
    revoke). Needs the full Protocol.
  * The API gateway, which verifies an incoming `Authorization: Bearer
    <key>` header. The gateway is forbidden from importing admin
    modules (`no-cross-service-imports`), so it receives a narrow
    `Callable[[str], str | None]` resolver constructed via
    `store.as_resolver()`. No cross-service import; the contract is the
    callable signature.

Two backends today:
  * `EnvApiKeyStore` — keys are read from the `API_KEYS` env at boot,
    same shape `parse_allowed_keys` already consumes (`bare-key` or
    `name:bare-key`, comma-separated). Read-only — create/revoke raise.
    Lets the simplest deployments avoid the DB.
  * `SqliteApiKeyStore` — keys live in the control-plane DB. Hashed at
    rest (sha256); plaintext is returned to the operator once on
    create and then unrecoverable. Backs the Phase 4 Admin API key
    management endpoints.
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

__all__ = [
    "ApiKeyRecord",
    "ApiKeyStore",
    "CreatedApiKey",
    "EnvApiKeyStore",
    "generate_api_key",
    "hash_api_key",
]


def hash_api_key(plaintext: str) -> str:
    """SHA-256 hex of the candidate. Constant work, no salt because the
    key itself is the secret (128+ bits of entropy via `secrets`)."""

    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    """Generate a fresh 256-bit URL-safe API key.

    Prefix is informational only — operators can tell a Vestigo key
    from a third-party token at a glance, and it doesn't reduce the
    entropy of the secret portion."""

    return "vk_" + secrets.token_urlsafe(32)


@dataclass(frozen=True)
class ApiKeyRecord:
    """Public-facing view of a stored key. The plaintext is never in
    this record — it is shown exactly once on `create_key` and then
    gone."""

    audit_id: str
    name: str
    created_at: datetime
    revoked: bool


@dataclass(frozen=True)
class CreatedApiKey:
    """`create_key` returns both the record and the plaintext, because
    that one-shot return is the only chance the operator has to copy
    the secret. After this leaves the function, the plaintext is not
    recoverable from any backend."""

    record: ApiKeyRecord
    plaintext: str


class ApiKeyStore(Protocol):
    """Admin-owned API key store. Both backends below satisfy this."""

    def resolve(self, plaintext: str) -> str | None:
        """Return the audit id for a valid plaintext, or None.

        Revoked keys must return None. The gateway uses this through
        the `as_resolver` callable wrapper."""
        ...

    def list_keys(self) -> list[ApiKeyRecord]:
        """All keys, including revoked ones (so the admin UI can show history)."""
        ...

    def create_key(self, *, name: str) -> CreatedApiKey:
        """Mint a new key. Returns plaintext exactly once."""
        ...

    def revoke_key(self, audit_id: str) -> bool:
        """Mark a key revoked. Returns True if a row was changed."""
        ...

    def as_resolver(self) -> Callable[[str], str | None]:
        """Return a narrow callable for the gateway.

        The gateway depends on this callable, not on the Protocol — that
        keeps the gateway free of any admin imports while still letting
        the verifier do its job."""
        ...


# --- Env-backed implementation -----------------------------------------------


@dataclass(frozen=True)
class EnvApiKeyStore:
    """Read-only store seeded from the `API_KEYS` env value.

    Compatible with the Phase 3 verifier behaviour: a comma-separated
    list of bare keys or `name:key` entries. Useful for tests and
    minimal deployments that don't want a DB just for credential
    storage. Create/revoke raise `RuntimeError` — env-mode is immutable
    at runtime."""

    by_plaintext: dict[str, ApiKeyRecord]

    @classmethod
    def from_raw(cls, raw: str | None, *, now: datetime) -> EnvApiKeyStore:
        out: dict[str, ApiKeyRecord] = {}
        if not raw:
            return cls(by_plaintext=out)
        for token in raw.split(","):
            entry = token.strip()
            if not entry:
                continue
            if ":" in entry:
                name, key = entry.split(":", 1)
                key = key.strip()
                audit_id = name.strip() or _short_id(key)
                display_name = name.strip() or audit_id
            else:
                key = entry
                audit_id = _short_id(key)
                display_name = audit_id
            if not key:
                continue
            out[key] = ApiKeyRecord(
                audit_id=audit_id,
                name=display_name,
                created_at=now,
                revoked=False,
            )
        return cls(by_plaintext=out)

    def resolve(self, plaintext: str) -> str | None:
        record = self.by_plaintext.get(plaintext)
        if record is None or record.revoked:
            return None
        return record.audit_id

    def list_keys(self) -> list[ApiKeyRecord]:
        return list(self.by_plaintext.values())

    def create_key(self, *, name: str) -> CreatedApiKey:
        raise RuntimeError(
            "EnvApiKeyStore is read-only; switch API_KEY_BACKEND=sqlite "
            "to manage keys via the Admin API."
        )

    def revoke_key(self, audit_id: str) -> bool:
        raise RuntimeError(
            "EnvApiKeyStore is read-only; switch API_KEY_BACKEND=sqlite "
            "to revoke keys."
        )

    def as_resolver(self) -> Callable[[str], str | None]:
        return self.resolve


def _short_id(key: str) -> str:
    return f"key-{key[:8]}" if key else "key-"
