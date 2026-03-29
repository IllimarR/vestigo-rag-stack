# Admin Service

Owns the Admin control-plane API, the `ConfigProvider` implementations,
and the API key store (per `docs/architecture.md` §7).

## Contracts owned

| Contract | Protocol | Implementation |
|---|---|---|
| `ConfigProvider` | `contracts.ConfigProvider` | `application/file_config_provider.py::FileConfigProvider` (Phase 1 ✓), `application/sqlite_config_provider.py::SqliteConfigProvider` (Phase 4 ✓) |
| `ApiKeyStore` (admin-local Protocol) | `application/api_key_store.py::ApiKeyStore` | `application/api_key_store.py::EnvApiKeyStore`, `application/sqlite_api_key_store.py::SqliteApiKeyStore` (Phase 4 ✓) |

`AuditLogger` is consumed by the Admin API but implemented in `services/audit/`.

## Public surface

`api.py::create_app(config_provider, audit_logger, api_key_store)` —
FastAPI app on port 8001.

| Route | Method | Purpose |
|---|---|---|
| `/health` | GET | Liveness probe |
| `/v1/config` | GET | Full config snapshot |
| `/v1/config/embedding` | PUT | Replace embedding section |
| `/v1/config/reranker` | PUT | Replace reranker section |
| `/v1/config/generation` | PUT | Replace generation section |
| `/v1/config/chunking` | PUT | Replace chunking section |
| `/v1/config/rag-prompt-template` | PUT | Replace prompt template (`{template: str}`) |
| `/v1/config/default-collection` | PUT | Replace default collection (`{collection: str}`) |
| `/v1/audit` | GET | Query audit log (`type`, `api_key_id`, `status`, `date_from`, `date_to`, `offset`, `limit`) |
| `/v1/api-keys` | GET | List API keys (audit_id, name, created_at, revoked) |
| `/v1/api-keys` | POST | Create API key (`{name: str}`); returns plaintext **exactly once** |
| `/v1/api-keys/{audit_id}` | DELETE | Revoke API key |

All writes emit an `admin_event` audit record. Auth is a single
shared secret in `Authorization: Bearer <ADMIN_API_KEY>`; when the env
is unset, admin runs unauthenticated (dev mode, warning logged at boot).

## Backends

### `FileConfigProvider` (default; `CONFIG_BACKEND=file`)

YAML file backend at `CONFIG_FILE_PATH`. Reads on every access; writes
atomically via temp-file + rename. Auto-seeds a defaults file on first
run so the composition root boots without manual setup.

### `SqliteConfigProvider` (`CONFIG_BACKEND=sqlite`)

Single `admin_config_entries` table on the shared control-plane DB
(`CONTROL_PLANE_DB_PATH`). On first run with an empty DB, seeds either
from the existing `CONFIG_FILE_PATH` (so an operator's tuning survives
the file→sqlite hand-off) or from `DEFAULT_CONFIG`.

### `EnvApiKeyStore` (default; `API_KEY_BACKEND=env`)

Read-only store seeded from the `API_KEYS` env value. Same shape the
Phase 3 verifier consumed: comma-separated `bare-key` or `name:bare-key`
entries.

### `SqliteApiKeyStore` (`API_KEY_BACKEND=sqlite`)

Plaintext is sha-256 hashed at rest. `create_key` returns the plaintext
exactly once; subsequent reads expose only `audit_id`, `name`,
`created_at`, `revoked`. If `API_KEYS` is also set, those entries are
seeded into the DB on first run (idempotent — keyed by hash).

## What is still missing (remaining Phase 4)

- Per-user / role-aware admin auth (Phase 6).
- Admin UI frontend on port 3000 (separate workstream).
- HTTP routes materializing the `ApiPushSourceConnector` (lives in
  the ingest service, not here).

## Scope reminder — `ConfigProvider` vs `.env`

`ConfigProvider` owns **application-level** configuration only: embedding,
reranking, generation, chunking, prompt template, default collection.
Infrastructure bindings (which backend to instantiate) live in `.env` and
are read by the composition root, not here. Config changes take effect on
the next pipeline run (running jobs continue with the previous configuration).

## Ports

Default: 8001 (see `.env.example::ADMIN_API_PORT`).
