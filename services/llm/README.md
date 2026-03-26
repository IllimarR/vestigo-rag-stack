# LLM Service

## Contracts owned

| Contract | Protocol | Implementation |
|---|---|---|
| `EmbeddingProvider` | `contracts.EmbeddingProvider` | `application/openai_http_embedding_provider.py::OpenAIHttpEmbeddingProvider` (Phase 2 ✓) |
| `Reranker` | `contracts.Reranker` | `application/placeholders.py::NotImplementedReranker` |
| `GenerationProvider` | `contracts.GenerationProvider` | `application/placeholders.py::NotImplementedGenerationProvider` |

## Public surface

`api.py` re-exports every implementation. There is no HTTP surface — the
LLM service is an in-process library consumed by the `RAGPipelineOrchestrator`
and the ingest pipeline.

## Implementations

### `OpenAIHttpEmbeddingProvider` (Phase 2)

- Speaks the OpenAI `/v1/embeddings` shape — works against OpenAI itself,
  Ollama, LM Studio, LocalAI, llamacpp-server, vLLM, or any other
  OpenAI-compatible endpoint.
- Constructor accepts an `httpx.Client` so tests can inject a `MockTransport`
  and production code can pool connections.
- `get_dimension()` lazily probes the model on first call (embeds a
  sentinel string), then caches.
- Optional `api_key` enables `Authorization: Bearer` headers — omit for
  local servers that don't require auth.
- Composition root dispatches this adapter when
  `ConfigProvider.get_embedding_config().api_type == "openai-compatible"`.

## Contract compliance

`tests/test_embedding_provider_contracts.py` — parameterized over every
registered provider. The HTTP adapter is tested against an
`httpx.MockTransport` that simulates the OpenAI shape, so no real server
is required to run the suite.

## What is still missing

Phase 2 (recommended second adapter for the swap proof):

- **Local embedding provider** (sentence-transformers with `BAAI/bge-small-en-v1.5`
  or similar) — true offline path, demonstrates `EmbeddingProvider` swap test
  per `docs/architecture.md` §Modularity Proof §2.

Phase 3:

- OpenAI-compatible generation adapter (non-streaming + SSE streaming).
- Anthropic generation adapter (second `GenerationProvider` for swap evidence).
- Cross-encoder reranker (local model).
- LLM-as-reranker (uses the `GenerationProvider` contract internally).

Each of the three stages is **independently configurable** via `ConfigProvider`;
no adapter here may share transport with another.
