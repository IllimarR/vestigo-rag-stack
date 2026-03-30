# LLM Service

## Contracts owned

| Contract | Protocol | Implementation |
|---|---|---|
| `EmbeddingProvider` | `contracts.EmbeddingProvider` | `application/openai_http_embedding_provider.py::OpenAIHttpEmbeddingProvider` (Phase 2 ✓) <br>`application/sentence_transformers_embedding_provider.py::SentenceTransformersEmbeddingProvider` (Phase 5 ✓) |
| `Reranker` | `contracts.Reranker` | `application/cross_encoder_reranker.py::CrossEncoderReranker` (Phase 3 ✓) <br>`application/llm_reranker.py::LLMReranker` (Phase 5 ✓) |
| `GenerationProvider` | `contracts.GenerationProvider` | `application/openai_http_generation_provider.py::OpenAIHttpGenerationProvider` (Phase 3 ✓) <br>`application/anthropic_generation_provider.py::AnthropicGenerationProvider` (Phase 5 ✓) |

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

### `SentenceTransformersEmbeddingProvider` (Phase 5)

- Local, in-process embeddings. No HTTP hop — model weights live on
  disk, the GPU/CPU does the work directly. Targets the offline /
  air-gapped deployment path and gives the Phase 5 modularity proof a
  swap that crosses the HTTP boundary.
- The model library is injected via an `Encoder` callable
  (`list[str] -> list[list[float]]`). The default production builder
  `sentence_transformers_encoder(model_name)` lazily loads
  sentence-transformers' `SentenceTransformer` on first invocation, so
  importing the adapter doesn't pull torch — same trick as the
  cross-encoder reranker.
- `get_dimension()` discovers vector width by probing the encoder once
  unless the caller passed an explicit `dimension` at construction.
- Composition root dispatches this adapter when
  `ConfigProvider.get_embedding_config().api_type == "sentence-transformers"`.

### `CrossEncoderReranker` (Phase 3)

- Pairwise relevance scorer: a cross-encoder consumes the
  `(query, candidate)` pair jointly and emits a relevance score, which
  is sharper than the bi-encoder used for retrieval at the cost of
  running once per pair.
- The model library is injected via a `Scorer` callable
  (`list[(query, candidate)] -> list[float]`). The default production
  builder `sentence_transformers_scorer(model_name)` lazily loads
  sentence-transformers' `CrossEncoder` on first invocation, so importing
  the adapter doesn't pull torch.
- `rerank` preserves the original `similarity_score`, attaches the new
  `rerank_score`, sorts descending by rerank score (stable on ties by
  original order), and clamps to `top_k`.
- Composition root dispatches this adapter when
  `ConfigProvider.get_reranker_config().type == "cross-encoder"`.

### `LLMReranker` (Phase 5)

- Borrows the configured `GenerationProvider` as a zero-shot relevance
  judge. For each `(query, candidate)` pair the adapter renders a
  prompt with sentinel markers, asks the LLM for a number 0-10, and
  parses the first float-like token from the response. Ordering and
  tie-breaking match `CrossEncoderReranker` exactly so the two
  backends behave identically when fed equivalent scores.
- **This is the one Reranker that composes another contract.** The
  adapter sees only the `GenerationProvider` `Protocol`; whichever
  provider is bound (OpenAI HTTP, Anthropic, ...) becomes the judge
  with no further code changes. The composition root is responsible
  for wiring the generation provider before the reranker.
- Default `temperature=0` and `max_tokens=16` — we only need a number,
  reproducibly. The prompt template is overridable via the constructor
  for prompt-engineering experiments.
- Composition root dispatches this adapter when
  `ConfigProvider.get_reranker_config().type == "llm"`.

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

### `AnthropicGenerationProvider` (Phase 5)

- Speaks Anthropic's native Messages API (`/v1/messages`) rather than
  the OpenAI shape — the second generation backend gives the thesis
  swap evidence its strongest case because the wire protocol itself
  diverges, not just the model behind it. Hand-rolled HTTPX, no
  `anthropic` SDK dependency.
- Five wire-protocol differences from `OpenAIHttpGenerationProvider`,
  each enforced by a test:
  - Endpoint `/v1/messages`, not `/v1/chat/completions`.
  - Headers `x-api-key` + `anthropic-version` — no Bearer.
  - `system` is a top-level body field (Anthropic rejects
    role='system' inside `messages`).
  - `max_tokens` is required; the adapter defaults to 4096 if the
    caller didn't set one.
  - SSE stream is event-typed (`message_start`, `content_block_delta`,
    `message_delta`, `message_stop`). Text deltas come from
    `content_block_delta` with `delta.type == "text_delta"`. Input
    tokens arrive in `message_start`, output tokens in `message_delta`;
    the adapter accumulates both and emits a usage-bearing final chunk
    on `message_stop`.
- Composition root dispatches this adapter when
  `ConfigProvider.get_generation_config().api_type == "anthropic"`.
  An `api_key` is mandatory — Anthropic does not allow anonymous
  requests, so `_build_generation_provider` refuses to bind without one.

## Contract compliance

- `tests/test_embedding_provider_contracts.py` — parameterized over every
  registered `EmbeddingProvider` via `_PROVIDERS`. Current entries:
  `openai_http`, `sentence_transformers`. The local provider plugs in
  a deterministic fake encoder so the suite stays torch-free.
- `tests/test_generation_provider_contracts.py` — parameterized over every
  registered `GenerationProvider` via `_PROVIDERS`. Current entries:
  `openai_http`, `anthropic`. Each backend gets its own
  `httpx.MockTransport` matching the wire shape it expects (OpenAI's
  `/v1/chat/completions` SSE vs Anthropic's event-typed
  `/v1/messages` stream). Covers unary + SSE streaming +
  system-prompt placement + parameter forwarding + auth conventions
  (Bearer vs `x-api-key`).
- `tests/test_reranker_contracts.py` — parameterized over every registered
  `Reranker` via `_RERANKERS`. Current entries: `cross_encoder`, `llm`.
  Tests inject a fake `Scorer` (cross-encoder) or a scorer-backed fake
  `GenerationProvider` (llm) so the suite covers both backends without
  loading torch or hitting a network.

## What is still missing

Phase 5 (modularity proof second adapters):

- ✓ Local embedding provider (`SentenceTransformersEmbeddingProvider`).
- ✓ LLM-as-reranker (`LLMReranker`) — composes `GenerationProvider`.
- ✓ Anthropic-API `GenerationProvider` (`AnthropicGenerationProvider`).

Each of the three stages is **independently configurable** via `ConfigProvider`;
no adapter here may share transport with another.
