"""API key authentication for the gateway.

The gateway never reads the key store directly — that would require
importing admin modules, which `no-cross-service-imports` forbids.
Instead the composition root constructs whichever store is configured
(env or sqlite-backed) and passes `store.as_resolver()` to the verifier
as a `Callable[[str], str | None]`.

Behaviour:
  * `enforce=False` (no auth backend configured) — every request maps
    to `ANONYMOUS_KEY_ID`. The composition root logs a warning so this
    is not a silent dev-mode-in-production trap.
  * `enforce=True` — the `Authorization: Bearer <key>` header is
    required; the resolver returns the key's audit id or None.
    `parse_allowed_keys` remains exported for tests and for the env
    backend's seeding path.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

__all__ = [
    "ANONYMOUS_KEY_ID",
    "ApiKeyVerifier",
    "AuthError",
    "parse_allowed_keys",
]

ANONYMOUS_KEY_ID = "anonymous"
_BEARER_PREFIX = "Bearer "


class AuthError(Exception):
    """Raised when the Authorization header is missing or invalid."""


@dataclass(frozen=True)
class ApiKeyVerifier:
    """Resolves an incoming `Authorization` header to an audit key id."""

    resolver: Callable[[str], str | None]
    enforce: bool

    @classmethod
    def disabled(cls) -> ApiKeyVerifier:
        """No-auth verifier — every request maps to `ANONYMOUS_KEY_ID`."""

        return cls(resolver=_anonymous_resolver, enforce=False)

    def verify(self, authorization_header: str | None) -> str:
        if not self.enforce:
            return ANONYMOUS_KEY_ID

        if not authorization_header or not authorization_header.startswith(_BEARER_PREFIX):
            raise AuthError("missing or malformed Authorization: Bearer <key> header")

        candidate = authorization_header[len(_BEARER_PREFIX) :].strip()
        audit_id = self.resolver(candidate)
        if audit_id is None:
            raise AuthError("api key not recognised")
        return audit_id


def _anonymous_resolver(_: str) -> str | None:
    return ANONYMOUS_KEY_ID


def parse_allowed_keys(raw: str | None) -> dict[str, str]:
    """Parse a comma-separated API_KEYS env value into a {key: audit_id} map.

    Each entry can be either a bare key or `name:key`; bare keys are
    given an audit id derived from their first eight characters.
    Whitespace and empty entries are tolerated.
    """
    if not raw:
        return {}

    out: dict[str, str] = {}
    for token in raw.split(","):
        entry = token.strip()
        if not entry:
            continue
        if ":" in entry:
            name, key = entry.split(":", 1)
            key = key.strip()
            audit_id = name.strip() or _short_id(key)
        else:
            key = entry
            audit_id = _short_id(key)
        if not key:
            continue
        out[key] = audit_id
    return out


def _short_id(key: str) -> str:
    return f"key-{key[:8]}" if key else "key-"
