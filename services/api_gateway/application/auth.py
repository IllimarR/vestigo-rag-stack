"""API key authentication for the gateway.

Phase 3 ships the minimal-viable surface: a comma-separated list of
allowed keys loaded once at boot, checked against the `Authorization:
Bearer <key>` header. Phase 4 replaces this with proper key
management via the Admin API.

* If the configured allow-list is empty, every request is allowed and
  the audit log records the request under `api_key_id="anonymous"`. The
  composition root logs a warning when it sees an empty list so this
  isn't a silent dev-mode-in-production trap.
* If the list is non-empty, requests must present a matching Bearer
  token; the audit log records the request under
  `api_key_id="key-<first-8-of-the-key>"`. This is intentionally a
  prefix and not the raw key, so audit logs don't leak the secret.
"""

from __future__ import annotations

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
    """Resolves an incoming `Authorization` header to an audit key id.

    `allowed` maps full key strings to the opaque id the audit log will
    record. When empty, the verifier operates in dev mode and returns
    `ANONYMOUS_KEY_ID` for every request.
    """

    allowed: dict[str, str]

    def verify(self, authorization_header: str | None) -> str:
        if not self.allowed:
            return ANONYMOUS_KEY_ID

        if not authorization_header or not authorization_header.startswith(_BEARER_PREFIX):
            raise AuthError("missing or malformed Authorization: Bearer <key> header")

        candidate = authorization_header[len(_BEARER_PREFIX) :].strip()
        if candidate not in self.allowed:
            raise AuthError("api key not recognised")
        return self.allowed[candidate]


def parse_allowed_keys(raw: str | None) -> dict[str, str]:
    """Parse a comma-separated API_KEYS env value into the verifier map.

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
