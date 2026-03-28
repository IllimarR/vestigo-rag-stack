# Retrieval Service

## Contracts owned

**None.** Retrieval is a composition of three contracts owned by other services:

| Contract used | Owned by |
|---|---|
| `EmbeddingProvider` | `services/llm/` |
| `VectorStoreRepository` | `services/vector_store/` |
| `Reranker` | `services/llm/` |

## Public surface

`api.py` — intentionally empty. Retrieval is not a stand-alone service:
it is the composition of `EmbeddingProvider.embed`,
`VectorStoreRepository.query_similar`, and `Reranker.rerank` performed
inline by `RAGPipelineOrchestrator` (in `services/api_gateway/`). The
directory exists so the module structure matches the seven modules in
`docs/architecture.md`, and so an eventual retrieval HTTP surface (for
non-RAG clients that just want chunks back) has a home.

## What is still missing

Nothing required for the current phases. A standalone retrieval HTTP
endpoint may land in a later phase if a non-RAG consumer needs raw
ranked chunks rather than a generated answer.
