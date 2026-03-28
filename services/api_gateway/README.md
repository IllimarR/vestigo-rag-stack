# API Gateway

Owns the OpenAI Responses-compatible public endpoint and the
**`RAGPipelineOrchestrator`**.

## Contracts owned

**None directly.** The Gateway consumes every other contract through the
orchestrator but does not implement any of them.

## Public surface

| Item | Where |
|---|---|
| FastAPI app factory | `api.py::create_app(orchestrator, api_key_verifier=...)` |
| Orchestrator class | `application/rag_pipeline_orchestrator.py::RAGPipelineOrchestrator` |
| HTTP routes | `GET /health`, `POST /v1/responses` (Phase 3 ✓) |
| Auth verifier | `application/auth.py::ApiKeyVerifier` |
| Responses translation | `application/responses_api.py` |

The orchestrator is the **reference example** for contract-only dependency
direction. It takes six `Protocol` arguments in its constructor and does
not import a single concrete implementation.

### `POST /v1/responses`

OpenAI Responses-shaped endpoint. Accepts:

```json
{
  "input": "string or [{role, content}, ...]",
  "instructions": "optional system prompt",
  "collection": "optional retrieval collection override",
  "stream": false
}
```

Non-streaming reply is a `response`-typed JSON body with an
`output[0].content[0].text` string and `usage` token counts. Streaming
mode (`"stream": true`) returns `text/event-stream` with
`response.output_text.delta` deltas terminated by a `response.completed`
event carrying final usage.

Authentication: `Authorization: Bearer <key>` against the allow-list
loaded at composition time. When the allow-list is empty the gateway
runs in dev mode and labels every request as `anonymous` in the audit
log.

## What is still missing

- Phase 4: full API key management via the Admin API (the env-driven
  allow-list bound here is the minimum-viable substitute).
- Phase 5: second `GenerationProvider` (e.g. Anthropic) to exercise the
  modularity proof on the generation side.

## Ports

Default: 8000 (see `.env.example::API_GATEWAY_PORT`).
