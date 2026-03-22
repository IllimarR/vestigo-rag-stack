# Vector Store Service

## Contract owned

| Contract | Protocol | Placeholder |
|---|---|---|
| `VectorStoreRepository` | `contracts.VectorStoreRepository` | `application/placeholders.py::NotImplementedVectorStoreRepository` |

This service owns the **sole access point** to the vector database. No other
module may bypass it — enforced by `import-linter` (no direct imports of
database drivers outside this service).

## Public surface

In-process library; no HTTP boundary. The composition root binds a concrete
implementation and passes it to consumers.

## Phase 1 status — what is missing

- ChromaDB adapter.
- pgvector adapter.
- Metadata filter translation layer (each backend serializes `MetadataFilter`
  differently).
- Collection lifecycle.

The Phase 1 placeholder returns `HealthStatus(healthy=False)` rather than
raising from `health_check`, so upstream `/health` endpoints can surface the
unbound state without crashing.
