# vestigo-rag-stack

## What This Is

A modular, fully self-hostable RAG (Retrieval-Augmented Generation) service architecture where each concern — ingestion, retrieval, generation, storage — operates behind a formal interface contract and can be replaced independently. Built as a TalTech bachelor's thesis prototype proving architectural feasibility of modular, self-hosted RAG services. The system exposes an OpenAI Chat Completions API-compatible endpoint, enabling OpenWebUI or other compatible frontends to use it as a drop-in backend.

## Core Value

Every RAG component is independently replaceable via interface contracts — proven by working swap tests — with all data staying on-premise and no SaaS dependencies.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Modular RAG service architecture with 9 swappable contracts (SourceConnector, DocumentConverter, Chunker, EmbeddingProvider, VectorStoreRepository, Reranker, GenerationProvider, AuditLogger, ConfigProvider)
- [ ] Full ingestion pipeline: document import → convert to Markdown → chunk → embed → store in vector DB
- [ ] Document lifecycle handling (add, modify, delete) with change detection
- [ ] Semantic retrieval with metadata filtering and reranking
- [ ] RAG pipeline orchestration: retrieve → rerank → prompt assembly → generate
- [ ] OpenAI Chat Completions API-compatible endpoint with SSE streaming
- [ ] API key authentication for gateway access
- [ ] Admin API and minimal Admin UI for configuration, key management, and audit logs
- [ ] Database-backed ConfigProvider and AuditLogger (replacing initial file-based stubs)
- [ ] Ingest API via ApiPushSourceConnector
- [ ] Modularity proof: swap tests for VectorStore (ChromaDB ↔ pgvector), EmbeddingProvider, Reranker, GenerationProvider, DocumentConverter
- [ ] Contract compliance tests reusable across implementations
- [ ] Health/readiness endpoints for all services
- [ ] Graceful error handling across all pipeline paths
- [ ] Thesis evidence pack: architecture diagrams, test evidence, API docs
- [ ] Compatible with OpenWebUI as frontend for thesis demonstration

### Out of Scope

- Production-grade enterprise features — this is a thesis prototype
- Model fine-tuning or training — existing models used as-is
- Runtime hot-swapping of components — all swaps are restart-time
- Real-time chat or video content support
- Mobile app or custom user-facing UI (beyond Admin UI)
- Conversation-aware query reformulation — last user message used as retrieval query
- Migration of file-based audit logs to database — acceptable for prototype
- Millions of documents / high concurrency — prototype targets hundreds to low thousands of docs, single-digit concurrent users

## Context

- **Thesis project** for TalTech (Tallinn University of Technology) bachelor's thesis demonstrating architectural feasibility of modular, self-hosted RAG
- Detailed specification already written: architecture, contracts (9 interfaces), pipeline orchestration, document lifecycle, implementation phases (6 phases), and validation criteria
- The spec is mature (v2) with changelog documenting design evolution
- Hybrid communication model: interface contracts for internal pipeline, HTTP APIs for external boundaries (API Gateway, Ingest API, Admin API)
- Two-tier configuration: ConfigProvider for application-level settings, .env/Docker for infrastructure-level bindings
- Non-atomic document updates (delete-then-store) — documented and acceptable for prototype scope

## Constraints

- **Self-hosting**: Every component runs on-premise, no SaaS dependencies permitted
- **Tech stack**: Python with FastAPI — decided for the implementation language
- **Vector store**: ChromaDB as primary, pgvector as swap demonstration target
- **LLM compatibility**: Must support OpenAI API (legacy + current) and Anthropic API for generation; OpenAI-compatible API for embeddings
- **API compatibility**: Gateway must be OpenAI Chat Completions API-compatible for OpenWebUI integration
- **Prototype scale**: Hundreds to low thousands of documents, single-digit concurrent users
- **Containerization**: Docker / Docker Compose for local dev and deployment
- **Monorepo**: Single repo with clear module separation (/services/ingest, /services/retrieval, /services/llm, etc.)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python + FastAPI | Rich ML/RAG ecosystem, strong async support, good for prototype speed | — Pending |
| ChromaDB as primary vector store | Simpler setup, purpose-built for embeddings, good prototype fit | — Pending |
| pgvector as swap target | Proves VectorStoreRepository modularity with a real alternative | — Pending |
| OpenWebUI as demo frontend | Industry-standard OpenAI-compatible UI, no custom UI work needed | — Pending |
| Hybrid communication (contracts + HTTP) | Modularity guarantee without microservice operational complexity | — Pending |
| Contracts-first development | Build interfaces before implementations, proving modularity by design | — Pending |
| Two-tier config (ConfigProvider + .env) | Frequently-changed settings via Admin UI, structural bindings via infrastructure config | — Pending |

---
*Last updated: 2025-02-25 after initialization*
