# Changelog

> Back to [README](../README.md)

---

## v2 (Current)

Changes from v1 → v2:

| Area | Change | Rationale |
|---|---|---|
| Swap semantics | Explicitly stated that all swaps are restart-time, not runtime | Clarifies architectural intent for prototype scope |
| [ConfigProvider](contracts.md#9-configprovider) scope | Documented two-tier config: `ConfigProvider` for application-level, `.env`/Docker for infrastructure-level | Avoids false expectation that all contracts are config-driven at application level |
| Ingest API | Defined as [`ApiPushSourceConnector`](contracts.md#1-sourceconnector) implementing `SourceConnector` contract | Preserves contract isolation — Ingest API does not bypass the abstraction |
| [Pipeline orchestration](pipeline.md#rag-pipeline-orchestration) | Added explicit `RAGPipelineOrchestrator` within API Gateway | Eliminates ambiguity about who coordinates retrieve → rerank → prompt → generate |
| [Conversation handling](pipeline.md#conversation-handling-prototype) | Defined conversation-to-query mapping (last user message = retrieval query) | Addresses gap between Chat Completions format and single-query retrieval |
| Collection targeting | Added `get/set_default_collection` to `ConfigProvider`; collection override in API requests | Clarifies how retrieval queries target the right collection |
| [`RerankedChunk`](contracts.md#6-reranker) type | Introduced `RerankedChunk` with separate `rerank_score` field | Avoids conflating vector similarity scores with reranker relevance scores |
| [`AuditLogger`](contracts.md#8-auditlogger) status | Added `status` and optional `error_message` fields to `log_query` and `log_ingest_event` | Enables logging of failed/partial query cycles and skipped files |
| Unsupported files | Documented skip-and-log behavior for unsupported file types | Addresses gap in error handling for monitored directories |
| Non-atomic updates | Documented delete-then-store limitation for document updates | Acknowledges prototype tradeoff explicitly |
| Config change timing | Documented that config changes take effect on next pipeline run | Clarifies behavior without adding change notification complexity |
| [Phase restructure](phases.md) | Merged API Gateway into Phase 3; added file-based ConfigProvider/AuditLogger to Phase 1; moved Admin API + DB persistence to Phase 4; reduced from 7 to 6 phases | Fixes ConfigProvider bootstrapping problem; enables client testing earlier; streamlines delivery |
| Tech stack decision | Made language selection an explicit Phase 1 deliverable | Concrete interfaces cannot be defined without knowing the language |
| In-memory vector store | Added to Phase 1 as early contract validation | Inexpensive way to catch contract design flaws before building real implementations |

## v1

Initial specification.
