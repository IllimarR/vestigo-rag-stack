# LLM Service

## Contracts owned

| Contract | Protocol | Implementation |
|---|---|---|
| `EmbeddingProvider` | `contracts.EmbeddingProvider` | `application/openai_http_embedding_provider.py::OpenAIHttpEmbeddingProvider` (Phase 2 ✓) |
| `Reranker` | `contracts.Reranker` | `application/placeholders.py::NotImplementedReranker` |
| `GenerationProvider` | `contracts.GenerationProvider` | `application/openai_http_generation_provider.py::OpenAIHttpGenerationProvider` (Phase 3 ✓) |

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

### `OpenAIHttpGenerationProvider` (Phase 3)

- Speaks the OpenAI `/v1/chat/completions` shape — works against OpenAI
  itself, Ollama, LM Studio, LocalAI, llamacpp-server, vLLM, and similar
  OpenAI-compatible endpoints.
- `generate(request)` returns a full `GenerationResponse`;
  `generate_stream(request)` yields one `GenerationChunk` per
  upstream-emitted `content` delta and a final usage-bearing chunk when
  the server reports usage on the last SSE frame.
- `system_prompt` is prepended as a `system`-role message; user/assistant
  turns flow through unchanged.
- Constructor takes an injectable `httpx.Client` so tests can drive a
  `MockTransport` for both unary and streaming responses.
- Composition root dispatches this adapter when
  `ConfigProvider.get_generation_config().api_type == "openai-compatible"`.

## Contract compliance

- `tests/test_embedding_provider_contracts.py` — parameterized over every
  registered `EmbeddingProvider` via `_PROVIDERS`. Current entries:
  `openai_http`.
- `tests/test_generation_provider_contracts.py` — parameterized over every
  registered `GenerationProvider` via `_PROVIDERS`. Current entries:
  `openai_http`. Covers unary + SSE streaming + system-prompt placement +
  parameter forwarding + Bearer auth.

## What is still missing

Phase 3:

- Cross-encoder reranker (local model) and LLM-as-reranker (delegates to
  the `GenerationProvider` contract internally).

Phase 5 (modularity proof second adapters):

- Local embedding provider (sentence-transformers, e.g.
  `BAAI/bge-small-en-v1.5`) for the offline path.
- Anthropic-API `GenerationProvider` for the generation-side swap.

Each of the three stages is **independently configurable** via `ConfigProvider`;
no adapter here may share transport with another.
