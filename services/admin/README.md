# Admin Service

## Contracts owned

**None directly.** The Admin API is a read/write client of `ConfigProvider`
and `AuditLogger` — both contracts are injected at construction.

## Public surface

`api.py::create_app(config_provider, audit_logger)` — FastAPI app. Phase 1
exposes only `/health`.

## Phase 1 status — what is missing

All of Phase 4:

- API key management (create, revoke, list).
- Model configuration endpoints (embedding, reranking, generation).
- Chunking configuration.
- Default collection setting.
- RAG prompt template management.
- Audit log querying endpoints.
- Admin UI frontend (out of scope — this module owns only the API).

## Ports

Default: 8002 (see `.env.example::ADMIN_API_PORT`).
