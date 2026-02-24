# Implementation Phases

> Back to [README](../README.md) | See also: [Architecture](architecture.md) · [Contracts](contracts.md) · [Pipeline](pipeline.md) · [Requirements](requirements.md)

---

The solution is implemented in phases that first establish contract boundaries and configuration primitives, then deliver the happy-path vertical slice with client compatibility, and finally expand to manageability, replaceability, and thesis-proof artifacts.

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

- Tech stack and language are decided
- All contracts are defined and consumable from shared modules
- File-based `ConfigProvider` and `AuditLogger` stubs are functional
- Services compile/start with stub implementations wired only through contracts
- Health endpoints are available for each service
- In-memory vector store validates the `VectorStoreRepository` contract design

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
- Implement **OpenAI Chat Completions API-compatible endpoint** in [API Gateway](architecture.md#5-api-gateway)
- Implement **SSE streaming** behavior compatible with OpenAI-style clients
- Add **basic API key authentication** (hardcoded or file-based keys for now — full management comes in Phase 4)
- Ensure responses include chunk/source references and relevant metadata
- Publish OpenAPI documentation for gateway endpoints

**Exit criteria:**

- Query-to-answer pipeline works end-to-end with source-grounded output
- Metadata filters affect retrieval results correctly
- Streaming generation functions in the integrated flow
- External clients can call the gateway as a Chat Completions-compatible API
- SSE responses are consumable by OpenAI-compatible frontends
- Basic authenticated access works

---

## Phase 4 — Admin API, ConfigProvider Persistence, and Operational Control Plane

- Implement [Admin API](architecture.md#7-admin-ui--api) endpoints for API keys, model configuration, chunk settings, default collection, and RAG prompt template
- Implement **database-backed [`ConfigProvider`](contracts.md#9-configprovider)** — replaces the file-based stub from Phase 1. Migration path: seed the database from the existing config file on first run.
- Implement **database-backed [`AuditLogger`](contracts.md#8-auditlogger)** — replaces the file-based stub. Historical file-based logs are not migrated (acceptable for prototype).
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
