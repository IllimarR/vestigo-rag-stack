# Requirements & Tech Stack

> Back to [README](../README.md) | See also: [Architecture](architecture.md) · [Contracts](contracts.md) · [Pipeline](pipeline.md) · [Phases](phases.md)

---

## Hard Constraints

- **Fully self-hostable** — every component (vector DB, embedding model, API layer, etc.) runs locally with no SaaS dependencies. No component may require a third-party cloud service to function.
- **LLM-agnostic via multiple API formats** — generation supports OpenAI API (legacy and current) and Anthropic API; embedding supports OpenAI-compatible API or local models; reranking supports cross-encoder models or LLM-based reranking. The system does not dictate where models live — that is an infrastructure decision, not an architectural one.
- **Components are independently testable** — clear service boundaries defined by [contracts](contracts.md)
- **Components are swappable** — replacing any component requires only a new contract implementation and a configuration change
- **Responses include source references** — metadata, document links, chunk origins
- **Health checks** — every service exposes a health/readiness endpoint for Docker Compose and monitoring
- **Graceful error handling** — if an LLM endpoint is down, embedding fails mid-batch, or a document fails conversion, the system handles it gracefully (log, retry where appropriate, skip and report — not crash the pipeline)

---

## Key Validation Criteria (Thesis)

1. Semantic search works with real documents
2. Responses contain source references and metadata
3. Metadata filters work (document type, date, tags)
4. Components are independently replaceable — proven by contract isolation and implementation swap tests (see [Modularity Proof Criteria](architecture.md#modularity-proof-criteria))
5. API Gateway is OpenAI Chat Completions API-compatible, supports streaming (SSE), and works with external clients
6. All components are self-hostable — no SaaS dependency required
7. Health check endpoints respond correctly for all services
8. Dependency diagram confirms all dependencies point toward contracts, never between implementations

---

## Tech Stack Preferences

- **Language**: Python 3.12+ — decided in [Phase 1](phases.md#phase-1--foundation-contracts-and-configuration-baseline). Contracts are defined as `typing.Protocol` classes; DTOs as frozen Pydantic v2 models. The specification itself remains language-agnostic so the architecture is re-implementable in another language if needed.
- **Generation LLM**: OpenAI API-compatible (legacy + current) or Anthropic API-compatible endpoint — configured via [`ConfigProvider`](contracts.md#9-configprovider)
- **Embedding**: Local models (e.g., sentence-transformers, E5) or via OpenAI-compatible embedding API
- **Reranking**: Local cross-encoder models or LLM-as-reranker via any supported generation API
- **Vector DB**: Start with ChromaDB or pgvector (abstracted behind [`VectorStoreRepository`](contracts.md#5-vectorstorerepository))
- **API framework**: REST framework with OpenAPI/Swagger support
- **Containerization**: Docker / Docker Compose for local dev and deployment
- **Testing**: Component-level and integration tests; contract compliance tests for each implementation

---

## Project Structure Principles

- Monorepo with clear module separation (`/services/ingest`, `/services/retrieval`, `/services/llm`, etc.)
- Each service has its own Dockerfile
- Shared contracts defined in a dedicated contracts package (`packages/contracts/`, importable as `contracts`) — all modules depend on this, never on each other
- Configuration: **`.env` files are used for infrastructure-level settings** (database connection, service ports, initial admin credentials, component binding decisions such as which vector store or audit backend to use). All **application-level configuration** — model endpoints, API keys, chunking parameters, RAG prompt templates, model parameters — is stored in the database and managed via the Admin UI through the [`ConfigProvider`](contracts.md#9-configprovider) contract.
- `docker-compose.yml` to spin up the full stack locally
- Clear README with architecture diagram description

---

## Development Approach

- Start with the core happy path: ingest a document → chunk → embed → store → query → retrieve → generate response with sources
- Build [contracts](contracts.md) first, concrete implementations second
- Keep it simple but architecturally sound — demonstrate modularity, not feature completeness
- Write tests that prove components can be swapped independently (contract compliance tests)
