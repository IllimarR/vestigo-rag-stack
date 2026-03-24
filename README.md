# vestigo-rag-stack

> **Modular, fully self-hostable RAG (Retrieval-Augmented Generation) service architecture with independent, swappable components behind a standardized API.**

Developed as a working prototype for a [TalTech (Tallinn University of Technology)](https://taltech.ee) bachelor's thesis, demonstrating the architectural feasibility of modular, self-hosted RAG services.

---

## Overview

vestigo-rag-stack is a fully on-premise, modular RAG service architecture. Solutions like OpenWebUI offer integrated RAG capabilities, but bundle them into a monolithic package. vestigo-rag-stack takes a different approach — separating each RAG concern into an independent, swappable service for organizations that need fine-grained control, component-level replaceability, and architectural transparency. It is suitable for any environment where data sovereignty and self-hosting are priorities: every component runs on-premise with no external SaaS dependencies, all data stays within the organization's infrastructure, and each module can be audited, replaced, or configured independently. This makes it particularly relevant for public sector organizations where data privacy and regulatory compliance are critical requirements.

The core design principle: **RAG functionality is separated from the UI into independent, swappable services behind a standardized API.** Each component — ingestion, retrieval, generation, storage — operates behind a formal interface contract and can be replaced independently without affecting the rest of the system.

The system exposes an **OpenAI Chat Completions API-compatible endpoint**, enabling any compatible frontend (OpenWebUI, custom UI, other clients) to use it as a drop-in backend.

---

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | Core modules, communication model, and modularity guarantees |
| [Contracts](docs/contracts.md) | Internal service contract specifications for all swappable components |
| [Pipeline & Document Lifecycle](docs/pipeline.md) | RAG query orchestration flow and document change detection |
| [Requirements & Tech Stack](docs/requirements.md) | Hard constraints, validation criteria, tech stack, and project structure |
| [Implementation Phases](docs/phases.md) | Phased delivery plan with exit criteria |
| [Changelog](docs/changelog.md) | Specification version history |

---

## What This Project Is

- A **thesis prototype** proving architectural feasibility of modular, self-hosted RAG
- A **backend RAG service layer** with a minimal Admin UI
- A demonstration of **component replaceability** via interface contracts
- A fully **self-hostable** system with no SaaS dependencies

## What This Project Is NOT

- A production-ready enterprise system — it is a thesis prototype proving architectural feasibility
- A UI project — the focus is the backend RAG service layer (Admin UI is the exception)
- A model fine-tuning or training project — existing models are used as-is

## Expected Scale (Prototype Scope)

- Hundreds to low thousands of documents — not millions
- Single-digit concurrent users
- This justifies simpler choices (e.g., ChromaDB over a distributed vector DB) while the architecture remains designed for future scaling

---

## Quick Start

### Development (Phase 1 skeleton)

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/IllimarR/vestigo-rag-stack
cd vestigo-rag-stack

cp .env.example .env   # infrastructure-level settings (ports, backend bindings)

uv sync                # install dependencies into .venv
uv run python main.py  # boots API Gateway :8000, Ingest API :8001, Admin API :8002
```

Verify:

```bash
curl http://localhost:8000/health   # API Gateway
curl http://localhost:8001/health   # Ingest API
curl http://localhost:8002/health   # Admin API
```

Phase 1 delivers functional implementations of three contracts:
`ConfigProvider` (YAML file at `CONFIG_FILE_PATH`, auto-seeded on first run),
`AuditLogger` (JSONL at `AUDIT_LOG_FILE`), and `VectorStoreRepository`
(in-memory cosine similarity — contract-validation stub, not production).
The remaining six contracts still raise `NotImplementedError` until their
phase lands. See [Implementation Phases](docs/phases.md) for what lands when.

### Docker Compose (planned)

A `docker-compose.yml` stack will be provided in a later phase (see
[Phases](docs/phases.md) and [Requirements](docs/requirements.md)). Until
then, run the services directly via `uv run python main.py` as above.

Refer to [Requirements & Tech Stack](docs/requirements.md) for detailed setup and configuration guidance.