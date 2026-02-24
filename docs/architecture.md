# Architecture

> Back to [README](../README.md) | See also: [Contracts](contracts.md) · [Pipeline](pipeline.md) · [Requirements](requirements.md)

---

## Core Architecture — Modular Components

The system consists of independent, loosely-coupled modules. Each module operates behind a formal [interface contract](contracts.md) and is independently replaceable.

### 1. Ingest Service

Document import, chunking, and embedding pipeline.

- Supports multiple data sources (file system directory monitoring, SharePoint, databases)
- Exposes an **Ingest API** implemented as an `ApiPushSourceConnector` — an implementation of the [`SourceConnector`](contracts.md#1-sourceconnector) contract that accepts documents via HTTP and translates them into the standard `ChangeEvent` pipeline flow. This keeps the Ingest API within the contract abstraction rather than bypassing it.
- Automatic sync/re-indexing when source documents change (see [Document Lifecycle](pipeline.md#document-lifecycle--change-detection))
- **Document lifecycle**: when a source document is updated, its chunks are re-embedded; when deleted, stale chunks are removed from the vector store. The delete-then-store sequence is non-atomic — if re-storage fails after deletion, the document's chunks are lost until the next successful sync. This is acceptable for prototype scope.
- **Unsupported files**: files with unsupported types (e.g., standalone images) encountered in monitored directories are silently skipped and logged as informational events via the [`AuditLogger`](contracts.md#8-auditlogger).
- **Supported document types**: Word (.docx), Excel (.xlsx), PDF (.pdf), Markdown (.md), plain text (.txt), HTML (.html), CSV (.csv), and other common formats. Images are only supported when embedded within documents — standalone image files are not ingested.
- **Conversion pipeline**: all documents are first converted to Markdown (.md) as the canonical format for chunking and embedding. Both the original file and the converted .md are stored for traceability and re-embedding.
- **Chunking strategy is configurable** — chunk size, overlap, and method (recursive, semantic, etc.) are adjustable without code changes. The chunking component conforms to the [`Chunker`](contracts.md#3-chunker) contract and is swappable like other modules.
- **Document converter is swappable** — the conversion component conforms to the [`DocumentConverter`](contracts.md#2-documentconverter) contract and is replaceable (e.g., swap Pandoc for a different converter) without affecting the rest of the pipeline. Conversion runs on-premise; no SaaS conversion services are permitted.
- Embedding is delegated to a component conforming to the [`EmbeddingProvider`](contracts.md#4-embeddingprovider) contract, independently configurable from reranking and generation models
- Preserves and stores document metadata (title, description, author, date, source system, document type, tags, direct link to original)

### 2. Vector Store

Stores embeddings and metadata.

- Accessed exclusively through the [`VectorStoreRepository`](contracts.md#5-vectorstorerepository) contract — no service may interact with the underlying database directly
- Swappable (e.g., ChromaDB, pgvector, Milvus) by providing a new implementation of the contract
- Supports metadata filtering (by document type, date, tags, source)
- **Collection/namespace management**: supports multiple collections or knowledge bases to organize documents logically. The target collection for retrieval queries is determined by configuration (a default collection set via [`ConfigProvider`](contracts.md#9-configprovider)), with the option for API requests to specify a collection override.
- Runs fully on-premise

### 3. Retrieval Service

Semantic search over the vector store.

- Takes a user query, returns ranked relevant chunks WITH all metadata (title, description, author, date, source system, document type, tags, direct link to original)
- Accesses the vector store exclusively through the [`VectorStoreRepository`](contracts.md#5-vectorstorerepository) contract
- Supports metadata-based filtering and enrichment
- Reranking is delegated to a component conforming to the [`Reranker`](contracts.md#6-reranker) contract, independently configurable from embedding and generation models

### 4. LLM Interface

Communicates with language models.

Each stage uses a separately configurable model endpoint: **embedding model**, **reranking model**, and **answer generation model** are all independent. Each stage is accessed through its own contract ([`EmbeddingProvider`](contracts.md#4-embeddingprovider), [`Reranker`](contracts.md#6-reranker), [`GenerationProvider`](contracts.md#7-generationprovider)).

Supported API formats vary by stage:

- **Embedding**: OpenAI-compatible API (legacy and current) or local model (e.g., sentence-transformers)
- **Reranking**: Cross-encoder models (local or API-based) or LLM-as-reranker pattern via any supported generation API
- **Generation**: OpenAI API (legacy and current) and Anthropic API

The system is model-agnostic — swapping any model or provider requires only a config change and (if necessary) a new contract implementation.

### 5. API Gateway

Exposes the full RAG pipeline as an OpenAI Chat Completions API-compatible endpoint.

- Enables different frontends (OpenWebUI, custom UI, other clients) to use the service
- Enforces API key authentication (keys managed via Admin UI)
- Supports streaming responses (SSE) as expected by OpenAI-compatible clients
- Standardized request/response format
- Contains the **[`RAGPipelineOrchestrator`](pipeline.md#rag-pipeline-orchestration)** — an internal component that coordinates the full query flow: extract query from conversation → embed → retrieve → rerank → assemble prompt with RAG template → generate response. The orchestrator depends only on contracts, never on concrete implementations.
- **Conversation-to-query mapping**: the orchestrator extracts the retrieval query from the incoming chat messages. For the prototype, the last user message is used as the retrieval query. The full conversation history is passed to the generation prompt for context continuity.

### 6. Audit & Logging

Observability and traceability.

- All services emit audit events through the [`AuditLogger`](contracts.md#8-auditlogger) contract
- All queries and responses are auditable/loggable
- The audit backend is swappable (database, file, external logging system) by providing a new contract implementation

### 7. Admin UI & API

Configuration, management, and monitoring.

- Simple web-based Admin UI for managing the system
- View audit logs: queries, responses, token usage per request
- API key management: create, revoke, and list API keys for the API Gateway
- Model configuration: configure endpoints, API type, model names for each stage (embedding, reranking, generation) — each with its own supported API formats
- Model parameters: token limits, temperature, top_p, system prompts, and other generation settings — per model
- **RAG prompt template management**: the template that defines how retrieved context chunks are injected into the generation prompt is configurable via the Admin UI — this is a critical piece of the [RAG pipeline](pipeline.md#rag-pipeline-orchestration)
- All configuration is read and written through the [`ConfigProvider`](contracts.md#9-configprovider) contract
- All Admin actions backed by a REST API with Swagger/OpenAPI documentation

### API Documentation

**All public APIs** (Ingest API, Retrieval Service, API Gateway, Admin API) provide **Swagger/OpenAPI documentation** so third-party developers can easily integrate and build on top of the system.

---

## Communication Architecture

The system uses a **hybrid communication model**: internal interfaces for the core pipeline, HTTP APIs for external boundaries.

### Internal Communication — Interface Contracts

All communication between modules within the core RAG pipeline (ingest → chunk → embed → store → retrieve → rerank → generate) happens through **shared [interface contracts](contracts.md)**. Modules depend on the contract, never on each other's internals.

This means:

- Modules run in the same process and communicate via direct method calls through contracts
- No unnecessary network serialization or HTTP overhead within the pipeline
- Swapping an implementation (e.g., replacing the vector store backend) requires only providing a new contract implementation — no other module changes
- **Swapping is restart-time, not runtime** — changing which implementation is bound to a contract requires a configuration change and a service restart. Runtime hot-swapping is not a goal for this prototype.
- Any internal contract can be promoted to a network API boundary later as a deployment decision, not an architectural change

### External Communication — HTTP APIs

The following boundaries are exposed as real HTTP REST APIs for third-party and cross-system integration:

- **API Gateway** — OpenAI Chat Completions API-compatible endpoint for frontends and clients
- **Ingest API** — allows external systems to push documents into the pipeline (implemented as [`ApiPushSourceConnector`](contracts.md#1-sourceconnector))
- **Admin API** — configuration, key management, and audit log access

This hybrid approach delivers the **modularity guarantee** (every component is independently replaceable via contracts) without the **operational complexity** of full microservices (service discovery, inter-service auth, distributed debugging, network latency chains) — which is disproportionate for a thesis prototype.

---

## Modularity Proof Criteria

To demonstrate that the architecture is genuinely modular, the following conditions are provable:

1. **Contract isolation** — Every swappable component is accessed exclusively through its [contract](contracts.md). No module references another module's internal types, classes, or configuration directly.

2. **Implementation swap test** — For each contract, at least two implementations exist or are demonstrably addable without modifying any consuming module. Priority swap tests:
   - [`VectorStoreRepository`](contracts.md#5-vectorstorerepository): ChromaDB ↔ pgvector
   - [`EmbeddingProvider`](contracts.md#4-embeddingprovider): local model ↔ OpenAI-compatible API
   - [`Reranker`](contracts.md#6-reranker): cross-encoder ↔ LLM-as-reranker
   - [`GenerationProvider`](contracts.md#7-generationprovider): OpenAI API ↔ Anthropic API
   - [`DocumentConverter`](contracts.md#2-documentconverter): Pandoc-based ↔ alternative converter

3. **Dependency direction** — All dependencies point inward toward contracts, never between concrete implementations. A dependency diagram confirms that removing or replacing any single implementation leaves all other modules and contracts intact.

4. **Configuration-driven binding** — Which concrete implementation is used for each contract is determined by configuration, not by hardcoded references. For application-level contracts (embedding, reranking, generation, chunking), binding is managed via [`ConfigProvider`](contracts.md#9-configprovider). For infrastructure-level contracts (vector store backend, source connectors, document converter, audit backend), binding is managed via `.env` and Docker Compose. In both cases, swapping a component means changing a config value and providing the implementation — not editing other modules. **All swaps require a service restart**; runtime hot-swapping is not a prototype goal.
