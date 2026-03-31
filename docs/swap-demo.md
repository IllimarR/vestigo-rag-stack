# Swap-Demo Evidence Pack

> Back to [README](../README.md) | See also: [Architecture](architecture.md) · [Phases](phases.md) · [Contracts](contracts.md)

---

This document is the Phase 5 evidence that the
[Modularity Proof Criteria](architecture.md#modularity-proof-criteria) are
satisfied for every priority contract. For each contract we ship at least
two real implementations and demonstrate that swapping between them is a
**configuration change, not a code change** — exactly what the thesis
argument claims about modular architecture.

The structural side of the proof (no consumer-side edits required) is
enforced two ways:

1. **Composition root is the only file that imports concrete adapters.**
   `main.py` contains every concrete-class import in the repository; every
   other file imports from `contracts` only. `import-linter` enforces this
   under the `contracts depends on nothing project-owned` and
   `Service modules never import each other` rules — running
   `uv run lint-imports` after a swap fails loudly if a consumer reaches
   past its contract.
2. **The parameterized contract suites cover every backend.** Each
   `tests/test_*_contracts.py` module registers all known adapters in a
   `_PROVIDERS` / `_RERANKERS` / `_CHUNKERS` / ... dict and runs the same
   expectations against each one. Adding a new backend means appending a
   factory; no test changes are needed. All 273 tests pass against every
   registered combination.

---

## Swap matrix

| Contract | Backend A | Backend B | Dispatch | Verified by |
|---|---|---|---|---|
| `VectorStoreRepository` | `InMemoryVectorStoreRepository` | `ChromaDbVectorStoreRepository` | `VECTOR_STORE_BACKEND` env | `tests/test_vector_store_contracts.py` (17 × 2 = 34 cases) |
| `SourceConnector` | `FilesystemSourceConnector` | `ApiPushSourceConnector` | `SOURCE_CONNECTORS` env | `tests/test_source_connector_contracts.py` (12 × 2 = 24 cases) |
| `ConfigProvider` | `FileConfigProvider` | `SqliteConfigProvider` | `CONFIG_BACKEND` env | `tests/test_config_provider_contracts.py` (27 × 2 = 54 cases) |
| `AuditLogger` | `FileAuditLogger` | `SqliteAuditLogger` | `AUDIT_BACKEND` env | `tests/test_audit_logger_contracts.py` (20 × 2 = 40 cases) |
| `ApiKeyStore` | `EnvApiKeyStore` | `SqliteApiKeyStore` | `API_KEY_BACKEND` env | `tests/test_api_key_store_contracts.py` (24 cases, env/sqlite-aware) |
| `Chunker` | `RecursiveChunker` | `FixedSizeChunker` | `ChunkConfig.method` | `tests/test_chunker_contracts.py` (12 × 2 = 24 cases) |
| `EmbeddingProvider` | `OpenAIHttpEmbeddingProvider` | `SentenceTransformersEmbeddingProvider` | `EmbeddingConfig.api_type` | `tests/test_embedding_provider_contracts.py` (22 cases) |
| `Reranker` | `CrossEncoderReranker` | `LLMReranker` | `RerankerConfig.type` | `tests/test_reranker_contracts.py` (17 cases) |
| `GenerationProvider` | `OpenAIHttpGenerationProvider` | `AnthropicGenerationProvider` | `GenerationConfig.api_type` | `tests/test_generation_provider_contracts.py` (16 cases) |
| `DocumentConverter` | `MarkitdownDocumentConverter` | *(deferred)* | `DOCUMENT_CONVERTER` env | `tests/test_document_converter_contracts.py` |

**Coverage of the priority swaps** in
[architecture.md §Modularity Proof Criteria](architecture.md#modularity-proof-criteria):

- ✓ `EmbeddingProvider`: local model ↔ OpenAI-compatible API
- ✓ `Reranker`: cross-encoder ↔ LLM-as-reranker
- ✓ `GenerationProvider`: OpenAI API ↔ Anthropic API
- ✓ `VectorStoreRepository`: in-memory ↔ ChromaDB (pgvector intentionally
  out of scope — ChromaDB is the production target; the swap demo's job
  is to prove that a *second* backend works, not to ship every backend)
- *Deferred:* `DocumentConverter` — `markitdown` already covers ten
  formats; a second converter is the lowest-value Phase 5 expansion and
  is parked rather than rushed.

---

## How each swap works in practice

### 1. `EmbeddingProvider`: OpenAI HTTP ↔ local sentence-transformers

The cross-boundary swap: one backend goes over the wire, the other runs
in-process. The contract surface (`embed`, `get_dimension`, `get_model_id`)
is identical; orchestrators have no way to tell the difference.

**Switch to local:**

```yaml
# config/config.yaml
embedding:
  api_type: sentence-transformers
  endpoint: ""
  model_name: sentence-transformers/all-MiniLM-L6-v2
  parameters: {}
```

**Switch to OpenAI HTTP (vLLM, LM Studio, llamacpp-server, OpenAI itself, ...):**

```yaml
embedding:
  api_type: openai-compatible
  endpoint: http://localhost:8080/v1
  model_name: nomic-embed-text
  parameters: {}
```

Restart the gateway. No code change.

### 2. `Reranker`: cross-encoder ↔ LLM-as-reranker

The composing swap: `LLMReranker` is the only `Reranker` that depends on
another contract (`GenerationProvider`). Switching to it means the
already-bound generation provider becomes the relevance judge — and
because the LLM reranker only sees the `GenerationProvider` `Protocol`,
the swap nests cleanly with the generation swap below.

**Switch to LLM-as-reranker:**

```yaml
reranker:
  type: llm
  endpoint: null
  model_name: llama3-judge
  parameters: {}
```

**Switch back to cross-encoder:**

```yaml
reranker:
  type: cross_encoder
  endpoint: null
  model_name: cross-encoder/ms-marco-MiniLM-L-6-v2
  parameters: {}
```

The composition root threads the bound generation provider into
`_build_reranker(...)`, so the LLM branch always uses whatever
`GenerationProvider` was configured. No reranker-side knowledge of
OpenAI/Anthropic/anything.

### 3. `GenerationProvider`: OpenAI HTTP ↔ Anthropic

The wire-protocol swap — the most pedagogically valuable one because the
two backends speak **fundamentally different APIs**, not the same API
with different model strings. Five concrete protocol differences are
absorbed entirely by the adapter:

| | OpenAI HTTP | Anthropic |
|---|---|---|
| Endpoint | `/v1/chat/completions` | `/v1/messages` |
| Auth | `Authorization: Bearer ...` | `x-api-key: ...` + `anthropic-version: ...` |
| System prompt | role=system inside `messages` | top-level `system` field |
| `max_tokens` | optional | required (adapter defaults to 4096) |
| Stream events | OpenAI SSE, `data: {...}` | typed events (`message_start`, `content_block_delta`, `message_delta`, `message_stop`) |

**Switch to Anthropic:**

```yaml
generation:
  api_type: anthropic
  endpoint: https://api.anthropic.com/v1
  model_name: claude-3-5-sonnet-20241022
  parameters:
    api_key: sk-ant-...
```

**Switch back to OpenAI-compatible (vLLM, LM Studio, OpenAI itself, ...):**

```yaml
generation:
  api_type: openai-compatible
  endpoint: http://localhost:8080/v1
  model_name: llama3
  parameters: {}
```

The `RAGPipelineOrchestrator`, the SSE-streaming gateway route, and the
`LLMReranker` (if bound) all keep running unchanged.

### 4. `Chunker`: recursive ↔ fixed-size

The smallest possible swap — same input, same `Chunk` DTO shape, same
position invariants — included to make `ChunkConfig.method` dispatch
visually obvious in the proof. Production deployments will keep the
recursive chunker; the fixed-size variant is here to demonstrate that the
ingest orchestrator doesn't depend on any one chunker's strategy.

```yaml
chunking:
  method: fixed_size   # or "recursive"
  size: 512
  overlap: 50
  parameters: {}
```

### 5. `VectorStoreRepository`, `SourceConnector`, `ConfigProvider`, `AuditLogger`, `ApiKeyStore`

These are infrastructure-level swaps, dispatched via `.env`:

```bash
VECTOR_STORE_BACKEND=in_memory   # or chromadb
SOURCE_CONNECTORS=filesystem      # or api
CONFIG_BACKEND=file               # or sqlite
AUDIT_BACKEND=file                # or sqlite
API_KEY_BACKEND=env               # or sqlite
```

Each pair was wired during the earlier phases (1, 2, 4); the parameterized
contract suites cover all backends.

---

## What "no consumer-side code change" actually means here

Going through any swap above, exactly two things change:

1. A line in `config/config.yaml` or `.env`.
2. The relevant `_build_*` helper in `main.py` chose a different
   branch — but `main.py` is the composition root, and `docs/architecture.md`
   §2 explicitly *defines* it as the swap-protocol boundary. It's the one
   file that knows about concrete classes.

Every other file in the repository keeps working. `RAGPipelineOrchestrator`
doesn't import any concrete provider, the ingest orchestrator doesn't
import any concrete chunker, the gateway route doesn't know whether
generation goes to OpenAI or Anthropic. That's structurally enforced by
`import-linter` (see `pyproject.toml` `[tool.importlinter]`), and visibly
true by `grep -r "from services\." main.py | wc -l` returning the same
count of imports regardless of which adapters are bound at runtime.

---

## Reproducing the evidence

```bash
# 1. Lint contracts and dependency directions
uv run lint-imports

# 2. Run the full contract-compliance suite against every backend
uv run pytest tests/ -q
# Expected: 273 passed, 21 skipped (the skips are ChromaDB integration
# tests that require a running ChromaDB container).

# 3. Live boot with any of the swap configurations above
CONFIG_FILE_PATH=./config/config.yaml uv run python main.py
```

For end-to-end smoke testing with a real swap pair, point
`config/config.yaml` at each combination in turn — every one boots all
three FastAPI services and answers `/health` cleanly.
