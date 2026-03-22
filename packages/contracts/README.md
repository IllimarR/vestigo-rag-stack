# `contracts`

The single dependency hub. Every service imports from here; services never import from each other.

## What lives here

- **Nine `Protocol` classes** — one per contract, each in its own module.
- **Every DTO** — frozen Pydantic v2 models in `dto.py`.
- **Supporting enums** — `ChangeType`, `Role`, `QueryStatus`, `IngestEventType`.

## The nine contracts

| Contract | Module | Owns |
|---|---|---|
| `SourceConnector` | `source_connector.py` | Document origin (filesystem, API push, ...) |
| `DocumentConverter` | `document_converter.py` | Raw → Markdown conversion |
| `Chunker` | `chunker.py` | Markdown → `Chunk[]` |
| `EmbeddingProvider` | `embedding_provider.py` | Text → vector |
| `VectorStoreRepository` | `vector_store.py` | Sole vector DB access point |
| `Reranker` | `reranker.py` | Re-score retrieved chunks |
| `GenerationProvider` | `generation_provider.py` | LLM completion (sync + stream) |
| `AuditLogger` | `audit_logger.py` | Structured audit events |
| `ConfigProvider` | `config_provider.py` | Application-level config |

## Rules

1. **No runtime dependencies on any service.** `contracts` depends only on `pydantic` and the standard library. Enforced via `import-linter`.
2. **DTOs are immutable.** Every Pydantic model uses `model_config = ConfigDict(frozen=True)`. Treat instances as value objects.
3. **Protocols describe structural types.** Implementations do not need to inherit — mypy and runtime duck-typing both work.
4. **`ConfigProvider` vs `.env`.** Application-level settings (models, chunking, prompts) live in `ConfigProvider`. Infrastructure bindings (which backend to instantiate) live in `.env`.

## Phase 1 status

Contracts and DTOs are complete. Concrete implementations do **not** live here — they live under `services/*`.
