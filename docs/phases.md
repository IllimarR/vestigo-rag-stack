# Implementation Phases

> Back to [README](../README.md) | See also: [Architecture](architecture.md) · [Contracts](contracts.md) · [Pipeline](pipeline.md) · [Requirements](requirements.md)

---

The solution is implemented in phases that first establish contract boundaries and configuration primitives, then deliver the happy-path vertical slice with client compatibility, and finally expand to manageability, replaceability, and thesis-proof artifacts.

---

## Current Status

| # | Phase | State |
|---|---|---|
| 1 | Foundation, Contracts, and Configuration Baseline | ✓ **Complete** |
| 2 | Ingestion Pipeline MVP | ✓ **Complete** — full ingest pipeline wired end-to-end |
| 3 | Retrieval, Generation, and API Gateway | ✓ **Complete** — query pipeline live behind `POST /v1/responses` |
| 4 | Admin API, ConfigProvider Persistence, and Operational Control Plane | ✓ **Complete** |
| 5 | Modularity Proof and Swap Demonstrations | ✓ **Complete** — every priority swap has a second adapter |
| 6 | Hardening, Validation, and Thesis Evidence Pack | **In progress** — Compose stack + runbook landed |

### Phase 1 delivered

- Python 3.12+ chosen; `pyproject.toml` uses `uv` for environment management.
- Shared contracts package at `packages/contracts/` — nine `typing.Protocol` classes and frozen Pydantic v2 DTOs.
- Monorepo service scaffolding mapping 1:1 onto the seven modules in [Architecture](architecture.md).
- Three external HTTP boundaries (API Gateway :8000, Admin API :8001, Ingest API :8002), each shipping `/health` and OpenAPI docs.
- [`RAGPipelineOrchestrator`](pipeline.md#rag-pipeline-orchestration) stub depending only on contracts — the reference example for contract-only dependency direction.
- Composition root (`main.py`) binding real Phase 1 implementations and placeholders for later phases.
- **[`ConfigProvider`](contracts.md#9-configprovider)** — `FileConfigProvider`, YAML backend, atomic writes, auto-seeded defaults on first run.
- **[`AuditLogger`](contracts.md#8-auditlogger)** — `FileAuditLogger`, append-only JSONL with filter + pagination `query_logs`.
- **[`VectorStoreRepository`](contracts.md#5-vectorstorerepository)** — `InMemoryVectorStoreRepository`, cosine similarity in pure Python, full `MetadataFilter` support, collection lifecycle, thread-safe. Contract-validation stub per Phase 1 early validation; also doubles as one side of the modularity swap test once Phase 2 adds a real backend.
- Six Phase 2/3 contracts (`SourceConnector`, `DocumentConverter`, `Chunker`, `EmbeddingProvider`, `Reranker`, `GenerationProvider`) bound to `NotImplementedError`-raising placeholders with clear messages pointing at which contract needs implementing.
- Quality gates: `mypy --strict` clean across 45 source files; three `import-linter` contracts enforcing contract isolation, no cross-service imports, and sole DB access via `services.vector_store`; 18-test pytest suite passing (contract imports, DTO frozenness, adapter roundtrips, `/health`, OpenAPI).

### Phase 1 deferred

- Docker Compose skeleton and per-service Dockerfiles — held until Phase 2 brings a real containerized backend (ChromaDB or pgvector) that needs orchestration. Running the stack in Phase 1 uses `uv run python main.py` directly.

### Phase 2 progress

- ✓ **ChromaDB `VectorStoreRepository`** — server-backed HTTP mode, env-selectable via `VECTOR_STORE_BACKEND=chromadb` + `CHROMADB_HOST`/`CHROMADB_PORT`/`CHROMADB_SSL`. Serializes `Chunk` to JSON in metadata, flattens user metadata for native `where`-clause filtering, translates `MetadataFilter` operators (`contains` is post-filtered in Python).
- ✓ **`RecursiveChunker`** — boundary-aware sliding window over Markdown. Prefers paragraph > line > sentence > word separators within a ~25% lookback of the hard cap. `Chunk.start` / `Chunk.end` reference positions in the original text; overlap is a natural consequence of start offset, not text duplication. Bound when `ConfigProvider.get_chunking_config().method == "recursive"`.
- ✓ **`OpenAIHttpEmbeddingProvider`** — speaks the OpenAI `/v1/embeddings` shape. Works with vLLM (the thesis-target upstream), OpenAI itself, LM Studio, llamacpp-server, LocalAI, and similar OpenAI-compatible servers. Lazy dimension discovery, optional Bearer auth, injectable `httpx.Client` for testing. Bound when `ConfigProvider.get_embedding_config().api_type == "openai-compatible"`.
- ✓ **`FilesystemSourceConnector`** — recursive scan of `INGEST_FILESYSTEM_ROOT` with in-memory snapshot diffing to emit ADDED / MODIFIED / DELETED `ChangeEvent`s; `since` watermark filters ADDED / MODIFIED while deletions are always reported. Env-selected via `SOURCE_CONNECTORS=filesystem`.
- ✓ **`MarkitdownDocumentConverter`** — Microsoft `markitdown` (MIT) converts PDF, DOCX, PPTX, XLSX, HTML, CSV, JSON, XML, plain text, and a handful of other office formats to Markdown. Conservative whitelist; unsupported types raise `UnsupportedFileTypeError` for the orchestrator to skip-and-log. Env-selected via `DOCUMENT_CONVERTER=markitdown`.
- ✓ **`IngestPipelineOrchestrator`** — applies `ChangeEvent` batches per `docs/pipeline.md` §Document Lifecycle. ADDED / MODIFIED / DELETED flows, delete-then-store on MODIFIED, skip-and-log on unsupported types or per-document exceptions, accumulated `IngestResult` counts.
- ✓ **Contract compliance suites** — parameterized tests across backends: vector store (17 × N), chunker (13 × N), embedding provider (12 × N), source connector (13 × N), document converter (11 × N). New backends plug into the relevant `_*` dict and inherit the full suite.
- ✓ **Composition root dispatch** — application-level contracts (`Chunker`, `EmbeddingProvider`) dispatch on `ConfigProvider` values per `docs/architecture.md` §Modularity Proof §4; infrastructure-level contracts (`VectorStoreRepository`, `SourceConnector`, `DocumentConverter`) dispatch on `.env`.
- Deferred to later phases: HTTP trigger for the ingest pipeline (`ApiPushSourceConnector` routes — Phase 4); optional second `EmbeddingProvider` (local sentence-transformers) for the swap-test evidence — Phase 5.

### Phase 4 progress

- ✓ **Shared `packages/control_plane/`** — `Base`, `get_engine`, `make_session_factory`. SQLAlchemy 2.x. SQLite file at `CONTROL_PLANE_DB_PATH`. Foreign-keys pragma enabled on every connection. `import-linter` enforces that only `services.admin` and `services.audit` may touch the package, mirroring the vector-store contract.
- ✓ **`SqliteConfigProvider`** — `CONFIG_BACKEND=sqlite` branch. Single `admin_config_entries` table (key + JSON value); on first run with an empty DB, seeds either from `CONFIG_FILE_PATH` (if present — the file→sqlite migration path) or from `DEFAULT_CONFIG`.
- ✓ **`SqliteAuditLogger`** — `AUDIT_BACKEND=sqlite` branch. Single `audit_events` table with indexed `type`, `timestamp`, `api_key_id`, `status`, `event_type` columns + JSON payload; `query_logs` produces the same row shape as `FileAuditLogger`. JSONL history is *not* migrated.
- ✓ **`ApiKeyStore`** — Protocol owned by the admin service, two implementations: `EnvApiKeyStore` (read-only env-seeded, default) and `SqliteApiKeyStore` (DB-backed CRUD with sha-256 hashed plaintext; plaintext returned exactly once on create). The gateway depends only on `store.as_resolver()` — no cross-service import.
- ✓ **`ApiKeyVerifier`** refactored to `resolver + enforce` shape so both env and sqlite stores plug in without code duplication.
- ✓ **Admin API endpoints** at `:8001/v1/` — `GET /config`, six per-section `PUT` writes (embedding, reranker, generation, chunking, rag-prompt-template, default-collection), `GET /audit?…`, `GET|POST /api-keys`, `DELETE /api-keys/{audit_id}`. Every write emits an admin audit event. Shared-secret bearer auth via `ADMIN_API_KEY` env (full per-user auth is a Phase 6 follow-up).
- ✓ **`ApiPushSourceConnector`** — in-memory push connector materializing the architecture's "the Ingest API IS an ApiPushSourceConnector" claim. ADDED/MODIFIED decided by whether `document_id` is known; `drop()` releases staged bytes after the orchestrator runs so memory is bounded.
- ✓ **Ingest API push routes** at `:8002/v1/` — `POST /documents` (single) and `POST /documents/batch` (array). Routes refuse with 409 when `SOURCE_CONNECTORS≠api` so the failure mode is loud. Shared-secret bearer auth via `INGEST_API_KEY` env.
- ✓ **Contract compliance suites** — `test_config_provider_contracts.py` (27 × N), `test_audit_logger_contracts.py` (20 × N), `test_api_key_store_contracts.py` (24 × N including the env/sqlite skip discipline). Admin routes covered by `test_admin_api_routes.py` (15 cases); ingest routes by `test_ingest_api_routes.py` (11 cases). The source-connector parameterized suite (12 × N) gained an `api_push` factory; the same test bodies cover both filesystem and api-push connectors.
- ✓ **admin-ui** at port 3000 — Vite + React + TypeScript scaffold under `admin-ui/`. Three views (API keys, Configuration, Audit log) talking to `:8001/v1/` via a typed `fetch` wrapper. The shared admin bearer is held in `localStorage` (`vestigo.admin.token`). Vitest + Testing Library cover the smoke surface — tab switching, initial loads, localStorage persistence, and `Authorization` header attachment.
- Deferred: Alembic remains deferred (schema is bootstrapped via `Base.metadata.create_all()` — adequate while no migrations exist). Multi-source ingestion (filesystem + api active simultaneously) is a future enhancement; today `SOURCE_CONNECTORS` picks one. Per-user / role-aware admin auth is a Phase 6 concern.

### Phase 3 progress

- ✓ **`OpenAIHttpGenerationProvider`** — calls upstream `/v1/chat/completions` (vLLM as the thesis-target upstream, plus OpenAI itself, LM Studio, llamacpp-server, LocalAI, ...). Non-streaming and SSE streaming; system prompt prepended; parameters threaded through from `GenerationConfig`. Bound when `ConfigProvider.get_generation_config().api_type == "openai-compatible"`.
- ✓ **`CrossEncoderReranker`** — pairwise cross-encoder reranker with an injectable `Scorer` callable. The default `sentence_transformers_scorer(model_name)` lazily loads sentence-transformers' `CrossEncoder` on first call, so the module's import surface stays light and contract tests run without touching torch. Bound when `ConfigProvider.get_reranker_config().type == "cross_encoder"`.
- ✓ **`RAGPipelineOrchestrator.run` / `run_stream`** — real implementation of the query flow in `docs/pipeline.md`. Embed → retrieve (top-k 20) → rerank (top-k 5) → render system prompt from `ConfigProvider.get_rag_prompt_template()` → generate → audit (SUCCESS / PARTIAL / FAILED).
- ✓ **`POST /v1/responses`** — OpenAI Responses-shaped endpoint with non-streaming JSON and SSE streaming (`response.output_text.delta` + `response.completed`). Bearer-token auth via env-driven `ApiKeyVerifier` (full key management arrives in Phase 4).
- ✓ **Contract compliance suites** — generation provider (7 × N) and reranker (8 × N) added alongside the Phase 2 suites; orchestrator and route are covered by dedicated test modules.
- Deferred: full API-key management (Phase 4); second `Reranker` (LLM-as-reranker) and second `GenerationProvider` (Anthropic) for Phase 5 swap evidence.

### Phase 5 progress

- ✓ **Second `EmbeddingProvider`** — `SentenceTransformersEmbeddingProvider` runs in-process via sentence-transformers' `SentenceTransformer` (no HTTP hop). Same injectable-encoder pattern as `CrossEncoderReranker`: the default `sentence_transformers_encoder(model_name)` lazily loads the model on first call, tests inject a deterministic fake encoder so the parameterized suite stays torch-free. Bound when `EmbeddingConfig.api_type == "sentence-transformers"`. Demonstrates the cross-boundary swap: HTTP backend ↔ in-process backend, contract surface unchanged.
- ✓ **Second `Reranker`** — `LLMReranker` borrows the configured `GenerationProvider` as a zero-shot relevance judge. For each `(query, candidate)` pair it renders a prompt with sentinel markers, asks the LLM for a number 0-10, and parses the first float-like token from the response. Same descending-score sort and stable index tie-break as `CrossEncoderReranker`. **This is the only `Reranker` that composes another contract** — the swap nests: whichever `GenerationProvider` is bound becomes the judge with no further adapter change. Bound when `RerankerConfig.type == "llm"`.
- ✓ **Second `GenerationProvider`** — `AnthropicGenerationProvider` speaks Anthropic's native Messages API (`/v1/messages`), not the OpenAI shape. Hand-rolled HTTPX, no `anthropic` SDK dependency. Five wire-protocol differences absorbed by the adapter: endpoint, `x-api-key` + `anthropic-version` headers, system prompt lifted to top-level body field, `max_tokens` required (default 4096), and event-typed SSE stream (`message_start` / `content_block_delta` / `message_delta` / `message_stop`). Bound when `GenerationConfig.api_type == "anthropic"`. The composition root refuses to bind without `parameters.api_key` — Anthropic does not allow anonymous requests, so the failure is loud at boot.
- ✓ **Second `Chunker`** — `FixedSizeChunker` is the simplest possible chunker (pure sliding window, no separator hunting, no Markdown awareness). Same `Chunk.start` / `Chunk.end` / verbatim-slice invariants as `RecursiveChunker`, so downstream stages cannot tell which produced a chunk. Exists for the smallest-possible-swap demo of `ChunkConfig.method` dispatch. Bound when `ChunkConfig.method == "fixed_size"`.
- ✓ **Contract compliance suites** — every parameterized suite gained entries for the new backends without code duplication: embedding (22 cases × 2), reranker (17 cases including the LLM-specific parse-robustness tests), generation (16 cases including the five Anthropic wire-protocol tests), chunker (12 × 2 = 24 cases). The same body of contract expectations runs against each backend; new backends only ever append a factory.
- ✓ **Swap-demo evidence pack** — see `docs/swap-demo.md` for the per-contract YAML before/after, the matrix mapping each priority swap to its verifying tests, and the reproduction steps. Documents that "no consumer-side code change" holds structurally (enforced by `import-linter`) as well as empirically (full test suite passes for every registered combination).
- ✓ **Live-boot verification per swap** — each new branch (`embedding.api_type=sentence-transformers`, `reranker.type=llm`, `generation.api_type=anthropic`, `chunking.method=fixed_size`) was exercised by booting all three FastAPI services and confirming each `/health` returns ok.
- Deferred: `pgvector` `VectorStoreRepository` (ChromaDB is the production target — a second vector backend is the lowest-value Phase 5 expansion). Second `DocumentConverter` (markitdown already covers ~10 formats; parking).

### Phase 6 progress

- ✓ **Docker Compose stack** — `docker-compose.yml` orchestrates six containers (gateway, admin, ingest, admin-ui, chromadb) on a shared bridge network. Two persistent named volumes (`chromadb-data`, `control-plane-data`) plus host bind-mounts for `config/` and `data/incoming/`. Healthcheck-gated startup ordering — admin/ingest/gateway wait on chromadb, admin-ui waits on admin — so a clean `up -d` always converges to a working stack. Closes the Phase 1 deferral.
- ✓ **Shared Python image** — single multi-stage `Dockerfile` produces `vestigo-app:latest`; three containers share the image and differ only by the `--service {gateway,admin,ingest}` flag. Reinforces the architectural argument that the three services share one code path until the very last entrypoint decision in `main.py`. `main.py` gained a `--service` flag with backwards-compatible default `all` so the developer workflow (`uv run python main.py`) is unchanged.
- ✓ **admin-ui static image** — multi-stage build (`node:20-alpine` → `nginx:alpine`) serving the Vite build on port 3000 with SPA fallback routing. No reverse-proxy — the browser hits the Admin API directly via the host port mapping.
- ✓ **Host-LLM reachability** — every Python container declares `extra_hosts: host.docker.internal:host-gateway`, so OpenAI-shaped endpoints pointed at the host's LLM server (vLLM in the thesis target deployment) keep working on Linux without Compose edits. The LLM server deliberately stays out of the Compose stack — model weights and GPU access belong on the host, and running vLLM is out of scope for the prototype.
- ✓ **Deployment runbook** — `docs/deployment.md` documents first-run bootstrap, per-strand swap recipes (config-yaml swaps, env swaps, code-level swaps), volume layout, backup/restore commands, troubleshooting, and the clean-checkout reproducibility script that closes the "system runs self-hosted end-to-end with reproducible setup" exit criterion.
- ✓ **End-to-end verification** — `docker compose up -d` from a clean repo (after `cp .env.example .env`) brings up all six containers healthy; every `/health` returns ok and ChromaDB's heartbeat returns a timestamp. Recorded in `docs/deployment.md` as the reproduction script.
- Remaining: architecture/dependency Mermaid diagrams in `docs/architecture.md`, targeted HTTP-retry hardening for the wire-bound providers, validation run against a small corpus with evidence capture.

---

## Phase 1 — Foundation, Contracts, and Configuration Baseline

- **Finalize tech stack and implementation language** — prerequisite for defining concrete contract signatures
- Finalize monorepo structure and shared [contracts](contracts.md) package as the single dependency hub
- Define contract-level data models and interface signatures for all core contracts (including [`RerankedChunk`](contracts.md#6-reranker) as a distinct type from `ScoredChunk`)
- Implement **file-based [`ConfigProvider`](contracts.md#9-configprovider)** as the initial stub — reads configuration from a YAML/JSON file, supports all `ConfigProvider` contract methods. This allows Phases 2–3 to resolve model endpoints, chunking config, and RAG prompt templates without the Admin API or database being ready yet.
- Implement **file-based [`AuditLogger`](contracts.md#8-auditlogger)** stub — writes audit events to a structured log file. Enables auditability from the start without database infrastructure.
- Establish health/readiness endpoint conventions for every service
- Prepare Docker Compose skeleton and service bootstrapping
- **(Early contract validation)**: Implement a simple **in-memory [`VectorStoreRepository`](contracts.md#5-vectorstorerepository)** as a throwaway test implementation. This is not for production use — it validates that the contract is not accidentally coupled to any specific database's semantics before the real implementation is built.

**Exit criteria:**

- ✓ Tech stack and language are decided
- ✓ All contracts are defined and consumable from shared modules
- ✓ File-based `ConfigProvider` and `AuditLogger` stubs are functional
- ✓ Services compile/start with stub implementations wired only through contracts
- ✓ Health endpoints are available for each service
- ✓ In-memory vector store validates the `VectorStoreRepository` contract design

---

## Phase 2 — Ingestion Pipeline MVP

- Implement initial [`SourceConnector`](contracts.md#1-sourceconnector) for filesystem input
- Implement first [`DocumentConverter`](contracts.md#2-documentconverter) and configurable [`Chunker`](contracts.md#3-chunker)
- Integrate first [`EmbeddingProvider`](contracts.md#4-embeddingprovider)
- Implement first production [`VectorStoreRepository`](contracts.md#5-vectorstorerepository) backend (ChromaDB or pgvector) and collection lifecycle basics
- Implement [document lifecycle handling](pipeline.md#document-lifecycle--change-detection) for add, modify, delete events
- Implement skip-and-log behavior for unsupported file types

**Exit criteria:**

- Documents can be ingested end-to-end: convert → chunk → embed → store
- Re-index and deletion flows work for modified/deleted source documents
- Unsupported files are skipped and logged without crashing the pipeline
- Metadata is preserved from source into stored chunks

---

## Phase 3 — Retrieval, Generation, and API Gateway

This phase delivers the complete vertical slice: query-to-answer with client compatibility.

- Implement Retrieval Service flow: query embedding, similarity search, metadata filtering
- Add first [`Reranker`](contracts.md#6-reranker) implementation (producing `RerankedChunk` with distinct rerank scores)
- Implement first [`GenerationProvider`](contracts.md#7-generationprovider) with both non-streaming and streaming paths
- Implement **[`RAGPipelineOrchestrator`](pipeline.md#rag-pipeline-orchestration)** within the API Gateway: coordinates retrieve → rerank → prompt assembly → generate
- Implement **[conversation-to-query mapping](pipeline.md#conversation-handling-prototype)**: last user message as retrieval query, full history in generation prompt
- Implement **OpenAI Responses API-compatible endpoint** in [API Gateway](architecture.md#5-api-gateway)
- Implement **SSE streaming** behavior compatible with OpenAI-style clients
- Add **basic API key authentication** (hardcoded or file-based keys for now — full management comes in Phase 4)
- Ensure responses include chunk/source references and relevant metadata
- Publish OpenAPI documentation for gateway endpoints

**Exit criteria:**

- Query-to-answer pipeline works end-to-end with source-grounded output
- Metadata filters affect retrieval results correctly
- Streaming generation functions in the integrated flow
- External clients can call the gateway as a Responses-compatible API
- SSE responses are consumable by OpenAI-compatible frontends
- Basic authenticated access works

---

## Phase 4 — Admin API, ConfigProvider Persistence, and Operational Control Plane

**Control-plane DB:** SQLite via SQLAlchemy 2.x. File-backed at `CONTROL_PLANE_DB_PATH` (env). Shared `Base`/engine/sessionmaker live in `packages/control_plane/` (sibling to `packages/contracts/`); admin and audit services own their own table classes against that shared `Base`. Schema bootstrap is `Base.metadata.create_all()` for the prototype; Alembic stays deferred until a real schema migration is needed. Chosen over Postgres to keep the stack fully self-hostable with zero extra services; SQLAlchemy is the swap boundary if a future deployment needs Postgres. Vector storage stays in ChromaDB — the control-plane DB is for config, audit, and API keys only.

- Implement [Admin API](architecture.md#7-admin-ui--api) endpoints for API keys, model configuration, chunk settings, default collection, and RAG prompt template
- Implement **SQLite-backed [`ConfigProvider`](contracts.md#9-configprovider)** (`CONFIG_BACKEND=sqlite`) — runs alongside `FileConfigProvider` rather than replacing it. Migration path: on first DB run, seed from the existing config file. The file backend stays as a valid choice for the simplest deployments.
- Implement **SQLite-backed [`AuditLogger`](contracts.md#8-auditlogger)** (`AUDIT_BACKEND=sqlite`) — runs alongside `FileAuditLogger`. Historical JSONL logs are not migrated (acceptable for prototype).
- Implement audit event querying for Admin use cases
- Add OpenAPI documentation for Admin and Ingest APIs
- Implement [`ApiPushSourceConnector`](contracts.md#1-sourceconnector) for the Ingest API
- Add minimal Admin UI workflows for core control-plane actions

**Exit criteria:**

- Runtime behavior is configuration-driven via database-backed `ConfigProvider`
- API keys and model/chunk/prompt settings are manageable via Admin API
- Audit logs support core traceability and inspection workflows
- Ingest API accepts documents via HTTP through the `ApiPushSourceConnector`
- Admin UI provides basic management capability

---

## Phase 5 — Modularity Proof and Swap Demonstrations

- Add at least one alternate implementation for high-priority swap contracts (see [Modularity Proof Criteria](architecture.md#modularity-proof-criteria))
- Execute swap tests for vector store, embedding, reranking, generation, and converter paths
- Verify dependency direction and contract isolation using architecture diagrams and code checks
- Add contract compliance tests reusable across implementations

**Exit criteria:**

- Swap scenarios run without consumer-side code changes
- Dependency graph demonstrates inward dependency on contracts only
- Contract compliance tests pass for baseline and alternate implementations

---

## Phase 6 — Hardening, Validation, and Thesis Evidence Pack

- Complete graceful error handling, retries, and failure reporting across ingest/retrieval/generation paths
- Finalize health/readiness behavior and container orchestration reliability
- Run validation against [thesis criteria](requirements.md#key-validation-criteria-thesis) with representative document corpus
- Prepare architecture diagrams, test evidence, and API docs as final proof artifacts
- Consolidate operational docs for local self-hosted deployment

**Exit criteria:**

- All thesis validation criteria are demonstrably satisfied
- System runs self-hosted end-to-end with reproducible setup
- Evidence package clearly proves modularity and replaceability claims

---

## Suggested Delivery Order by Value

1. **Phase 1 → 2 → 3** to secure the core RAG vertical slice with client compatibility early
2. **Phase 4** for manageability, traceability, and full Ingest API
3. **Phase 5 → 6** to prove modular thesis claims and finalize quality gates
