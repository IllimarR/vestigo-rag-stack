# Pipeline & Document Lifecycle

> Back to [README](../README.md) | See also: [Architecture](architecture.md) · [Contracts](contracts.md) · [Requirements](requirements.md)

---

## RAG Pipeline Orchestration

The **`RAGPipelineOrchestrator`** is an internal component within the [API Gateway](architecture.md#5-api-gateway) service that coordinates the full query-to-answer flow. It depends only on [contracts](contracts.md), never on concrete implementations.

### Orchestration Flow

1. **Extract query** — the last user message from the incoming chat request is used as the retrieval query
2. **Embed query** — a query embedding is generated via [`EmbeddingProvider`](contracts.md#4-embeddingprovider)
3. **Retrieve** — similar chunks are searched via [`VectorStoreRepository.query_similar`](contracts.md#5-vectorstorerepository), using the configured default collection (or request-specified override) and any metadata filters
4. **Rerank** — retrieved chunks are re-scored via [`Reranker`](contracts.md#6-reranker)
5. **Assemble prompt** — the top reranked chunks are injected into the RAG prompt template (from [`ConfigProvider`](contracts.md#9-configprovider)), combined with the full conversation history
6. **Generate** — the assembled prompt is passed to [`GenerationProvider`](contracts.md#7-generationprovider) for response generation (streaming or non-streaming)
7. **Audit** — the full query cycle is logged via [`AuditLogger`](contracts.md#8-auditlogger)
8. **Return** — the generated response is returned with source references and metadata

### Conversation Handling (Prototype)

For the prototype, conversation-to-query mapping is simple: the **last user message** is used as the retrieval query. The full conversation history is included in the generation prompt for context continuity but does not affect retrieval. More sophisticated query extraction (e.g., conversation-aware query reformulation) is out of scope.

---

## Document Lifecycle & Change Detection

[Source connectors](contracts.md#1-sourceconnector) emit **change events** through the `SourceConnector` contract. The [Ingest Service](architecture.md#1-ingest-service) subscribes to these events and orchestrates the appropriate pipeline action:

- **Document added** → convert → chunk → embed → store in vector store
- **Document modified** → delete old chunks from vector store → re-convert → re-chunk → re-embed → store
- **Document deleted** → delete all associated chunks from vector store
- **Unsupported file encountered** → skip, log as informational event via [`AuditLogger`](contracts.md#8-auditlogger)

The change detection mechanism depends on the source connector implementation (file system watcher, polling interval, webhook, etc.). The Ingest Service does not know or care how changes are detected — it only processes the `ChangeEvent` objects it receives.

### Non-Atomic Update Caveat

The prototype uses a **delete-then-store** approach for document updates rather than atomic upserts. If deletion succeeds but re-storage fails, the document's chunks are lost until the next successful sync cycle. This tradeoff is documented and acceptable at prototype scale. See also the note on [`VectorStoreRepository`](contracts.md#5-vectorstorerepository).
