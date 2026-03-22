# API Gateway

Owns the OpenAI Chat Completions-compatible public endpoint and the
**`RAGPipelineOrchestrator`**.

## Contracts owned

**None directly.** The Gateway consumes every other contract through the
orchestrator but does not implement any of them.

## Public surface

| Item | Where |
|---|---|
| FastAPI app factory | `api.py::create_app(orchestrator)` |
| Orchestrator class | `application/rag_pipeline_orchestrator.py::RAGPipelineOrchestrator` |

The orchestrator is the **reference example** for contract-only dependency
direction. It takes six `Protocol` arguments in its constructor and does
not import a single concrete implementation.

## Phase 1 status — what is missing

- `POST /v1/chat/completions` (Phase 3).
- SSE streaming (Phase 3).
- API key authentication middleware (Phase 3 basic, Phase 4 full management).
- Actual orchestration logic in `RAGPipelineOrchestrator.run` / `run_stream`
  (Phase 3). Both currently raise `NotImplementedError` with pointers to
  which contracts need binding.

## Ports

Default: 8000 (see `.env.example::API_GATEWAY_PORT`).
