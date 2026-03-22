# Admin Service

Owns the Admin control-plane API **and** the `ConfigProvider` implementation
(per `docs/architecture.md` §7: "All configuration is read and written
through the `ConfigProvider` contract").

## Contracts owned

| Contract | Protocol | Placeholder |
|---|---|---|
| `ConfigProvider` | `contracts.ConfigProvider` | `application/placeholders.py::NotImplementedConfigProvider` |

`AuditLogger` is consumed by the Admin API but implemented in `services/audit/`.

## Public surface

`api.py::create_app(config_provider, audit_logger)` — FastAPI app. Phase 1
exposes only `/health`.

## Phase 1 status — what is missing

Application-level:

- File-based `ConfigProvider` reading YAML/JSON (Phase 1 per `docs/phases.md`).
- Database-backed `ConfigProvider` (Phase 4; seeds from the existing config
  file on first run).

API-level (Phase 4):

- API key management (create, revoke, list).
- Model configuration endpoints (embedding, reranking, generation).
- Chunking configuration.
- Default collection setting.
- RAG prompt template management.
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
