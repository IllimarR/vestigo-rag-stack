# vestigo-rag-stack

> **Modular, fully self-hostable RAG (Retrieval-Augmented Generation) service architecture with independent, swappable components behind a standardized API.**

Developed as a working prototype for a [TalTech (Tallinn University of Technology)](https://taltech.ee) bachelor's thesis, demonstrating the architectural feasibility of modular, self-hosted RAG services.

---

## Overview

vestigo-rag-stack is a fully on-premise, modular RAG service architecture. Solutions like OpenWebUI offer integrated RAG capabilities, but bundle them into a monolithic package. vestigo-rag-stack takes a different approach — separating each RAG concern into an independent, swappable service for organizations that need fine-grained control, component-level replaceability, and architectural transparency. It is suitable for any environment where data sovereignty and self-hosting are priorities: every component runs on-premise with no external SaaS dependencies, all data stays within the organization's infrastructure, and each module can be audited, replaced, or configured independently. This makes it particularly relevant for public sector organizations where data privacy and regulatory compliance are critical requirements.

The core design principle: **RAG functionality is separated from the UI into independent, swappable services behind a standardized API.** Each component — ingestion, retrieval, generation, storage — operates behind a formal interface contract and can be replaced independently without affecting the rest of the system.

The system exposes an **OpenAI Responses API-compatible endpoint**, enabling any compatible frontend (OpenWebUI, custom UI, other clients) to use it as a drop-in backend.

---

## Documentation

| Document | Description |
|---|---|
| [Architecture](docs/architecture.md) | Core modules, communication model, and modularity guarantees |
| [Contracts](docs/contracts.md) | Internal service contract specifications for all swappable components |
| [Pipeline & Document Lifecycle](docs/pipeline.md) | RAG query orchestration flow and document change detection |
| [Requirements & Tech Stack](docs/requirements.md) | Hard constraints, validation criteria, tech stack, and project structure |
| [Implementation Phases](docs/phases.md) | Phased delivery plan with exit criteria |
| [Swap-Demo Evidence](docs/swap-demo.md) | Phase 5 per-contract swap walkthrough proving the modularity criteria |
| [Deployment Runbook](docs/deployment.md) | Docker Compose flow, first-run bootstrap, swap recipes, backup |
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

### Development

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/IllimarR/vestigo-rag-stack
cd vestigo-rag-stack

cp .env.example .env   # infrastructure-level settings (ports, backend bindings)

uv sync                # install dependencies into .venv
uv run python main.py  # boots API Gateway :8000, Admin API :8001, Ingest API :8002
```

Verify:

```bash
curl http://localhost:8000/health   # API Gateway
curl http://localhost:8001/health   # Admin API
curl http://localhost:8002/health   # Ingest API
```

All nine contracts now have real bindings. Phase 4 added a second
implementation for the persistence-flavoured ones (SQLite-backed
`ConfigProvider`, `AuditLogger`, and API key store), an ingest push
flow, and the Admin API surface that drives them. Phase 5 added a
second implementation for each remaining priority contract — local
sentence-transformers embeddings, LLM-as-reranker, the Anthropic
generation provider, and a fixed-size chunker — so every contract
called out in the [Modularity Proof Criteria](docs/architecture.md#modularity-proof-criteria)
now has at least two backends. The default seed config (`config.yaml`)
points the generation provider at Ollama on
`http://localhost:11434/v1` and the embedding provider similarly;
bring your own OpenAI-compatible endpoint if you don't have Ollama
running. See [Implementation Phases](docs/phases.md) for what landed
in which phase and [Swap-Demo Evidence](docs/swap-demo.md) for the
per-contract swap walkthrough.

Quick smoke test:

```bash
# dev mode — empty API_KEYS allows anonymous requests
curl -s http://localhost:8000/v1/responses \
  -H 'Content-Type: application/json' \
  -d '{"input": "hello", "stream": false}'
```

### Admin UI (port 3000)

The Vite + React control plane talks to the Admin API on `:8001`.

```bash
cd admin-ui
npm install
npm run dev      # http://localhost:3000
```

Set the admin bearer (`ADMIN_API_KEY` from your `.env`) in the auth
bar in the UI header to unlock the API keys, configuration, and audit
views. See [admin-ui/README.md](admin-ui/README.md) for layout and
scripts.

### Docker Compose (Phase 6)

One-command self-hosted boot. Six containers, two custom images
(`vestigo-app` for the three Python services, `vestigo-admin-ui` for
the static SPA) plus the upstream `chromadb/chroma` image.

```bash
cp .env.example .env       # seed env (set ADMIN_API_KEY / INGEST_API_KEY if you want auth)
docker compose up -d       # builds images on first run, then starts everything
```

When healthy, the same host ports as the dev workflow:
`:8000` gateway · `:8001` admin API · `:8002` ingest API · `:3000`
admin-ui · `:8500` ChromaDB.

Ollama (or any other OpenAI-compatible LLM server) stays on the host —
the Compose stack reaches it via `host.docker.internal`. Edit
`config/config.yaml` to point `embedding.endpoint` and
`generation.endpoint` at `http://host.docker.internal:11434/v1` before
the first run.

See [Deployment Runbook](docs/deployment.md) for the operational
walkthrough — first-run bootstrap, swapping backends in the live stack,
volume layout, backup/restore.

Refer to [Requirements & Tech Stack](docs/requirements.md) for detailed setup and configuration guidance.
