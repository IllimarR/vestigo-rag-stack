# LLM Service

## Contracts owned

| Contract | Protocol | Placeholder |
|---|---|---|
| `EmbeddingProvider` | `contracts.EmbeddingProvider` | `application/placeholders.py::NotImplementedEmbeddingProvider` |
| `Reranker` | `contracts.Reranker` | `application/placeholders.py::NotImplementedReranker` |
| `GenerationProvider` | `contracts.GenerationProvider` | `application/placeholders.py::NotImplementedGenerationProvider` |

## Public surface

`api.py` re-exports the placeholder types. There is no HTTP surface — the
LLM service is an in-process library consumed directly by the
`RAGPipelineOrchestrator` and the ingest pipeline.

## Phase 1 status — what is missing

- OpenAI-compatible embedding adapter + local sentence-transformers adapter.
- Cross-encoder reranker + LLM-as-reranker variant.
- OpenAI-compatible generation adapter + Anthropic adapter.
- Streaming support in the generation adapter (SSE-compatible iteration).

Each of the three stages is **independently configurable** via `ConfigProvider`;
no adapter here may share transport with another.
