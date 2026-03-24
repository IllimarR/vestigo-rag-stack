# Admin Service

Owns the Admin control-plane API **and** the `ConfigProvider` implementation
(per `docs/architecture.md` §7: "All configuration is read and written
through the `ConfigProvider` contract").

## Contracts owned

| Contract | Protocol | Implementation |
|---|---|---|
| `ConfigProvider` | `contracts.ConfigProvider` | `application/file_config_provider.py::FileConfigProvider` (Phase 1 ✓) |

`AuditLogger` is consumed by the Admin API but implemented in `services/audit/`.

## Public surface

`api.py::create_app(config_provider, audit_logger)` — FastAPI app. Phase 1
exposes only `/health`.

## Phase 1 status

- ✓ `FileConfigProvider` — YAML file backend. Reads on every access;
  writes atomically via temp-file + rename. Auto-seeds a defaults file at
  `CONFIG_FILE_PATH` on first run so the composition root boots without
  manual setup. A reference `config/config.yaml.example` lives in the repo.

## What is still missing

Phase 4:

- Database-backed `ConfigProvider` (replaces the file-based stub; seeds
  from the existing config file on first run).
- API key management (create, revoke, list).
- Model configuration endpoints (embedding, reranking, generation).
- Chunking configuration endpoint.
- Default collection setting endpoint.
- RAG prompt template management endpoint.
- Audit log querying endpoints.
- Admin UI frontend (out of scope — this module owns only the API).

## Scope reminder — `ConfigProvider` vs `.env`

`ConfigProvider` owns **application-level** configuration only: embedding,
reranking, generation, chunking, prompt template, default collection.
Infrastructure bindings (which backend to instantiate) live in `.env` and
are read by the composition root, not here. Config changes take effect on
the next pipeline run (running jobs continue with the previous configuration).

## Ports

Default: 8002 (see `.env.example::ADMIN_API_PORT`).
