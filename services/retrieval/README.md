# Retrieval Service

## Contracts owned

**None.** Retrieval is a composition of three contracts owned by other services:

| Contract used | Owned by |
|---|---|
| `EmbeddingProvider` | `services/llm/` |
| `VectorStoreRepository` | `services/vector_store/` |
| `Reranker` | `services/llm/` |

## Public surface

`api.py` — intentionally empty in Phase 1. Phase 3 will add a retrieval
function (query string → ranked chunks with metadata) consumed by the
`RAGPipelineOrchestrator`.

## Phase 1 status — what is missing

Everything. The directory exists so the module structure matches the seven
modules in `docs/architecture.md`.
