"""Tests for the API Gateway's `POST /v1/responses` route.

Uses a fake `RAGPipelineOrchestrator` and a real `ApiKeyVerifier` so the
test exercises the actual FastAPI app via `TestClient` (request parsing,
auth, response shaping, SSE) without standing up any external services.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
from contracts import (
    ChatMessage,
    GenerationChunk,
    GenerationResponse,
    MetadataFilter,
    Role,
    TokenUsage,
)
from fastapi.testclient import TestClient

from services.api_gateway.api import create_app
from services.api_gateway.application.auth import ApiKeyVerifier
from services.api_gateway.application.responses_api import (
    RESPONSES_DONE_EVENT,
    RESPONSES_TEXT_DELTA_EVENT,
)


class _FakeOrchestrator:
    """Stand-in `RAGPipelineOrchestrator` for transport-level tests."""

    def __init__(
        self,
        *,
        response_text: str = "the answer",
        stream_deltas: tuple[str, ...] = ("the ", "answer"),
    ) -> None:
        self._response_text = response_text
        self._stream_deltas = stream_deltas
        self.run_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []

    def run(
        self,
        messages: list[ChatMessage],
        *,
        api_key_id: str,
        collection: str | None = None,
        filters: list[MetadataFilter] | None = None,
    ) -> GenerationResponse:
        self.run_calls.append(
            {
                "messages": messages,
                "api_key_id": api_key_id,
                "collection": collection,
                "filters": filters,
            }
        )
        return GenerationResponse(
            text=self._response_text,
            usage=TokenUsage(prompt_tokens=11, completion_tokens=7),
            model_id="fake-gen",
        )

    def run_stream(
        self,
        messages: list[ChatMessage],
        *,
        api_key_id: str,
        collection: str | None = None,
        filters: list[MetadataFilter] | None = None,
    ) -> Iterator[GenerationChunk]:
        self.stream_calls.append(
            {
                "messages": messages,
                "api_key_id": api_key_id,
                "collection": collection,
                "filters": filters,
            }
        )
        for delta in self._stream_deltas:
            yield GenerationChunk(delta=delta)
        yield GenerationChunk(
            delta="", usage=TokenUsage(prompt_tokens=11, completion_tokens=7)
        )


def _client(*, allowed: dict[str, str] | None = None) -> tuple[TestClient, _FakeOrchestrator]:
    orchestrator = _FakeOrchestrator()
    if allowed:
        keys = dict(allowed)

        def resolver(candidate: str) -> str | None:
            return keys.get(candidate)

        verifier = ApiKeyVerifier(resolver=resolver, enforce=True)
    else:
        verifier = ApiKeyVerifier.disabled()
    app = create_app(orchestrator, api_key_verifier=verifier)  # type: ignore[arg-type]
    return TestClient(app), orchestrator


# --- Auth ------------------------------------------------------------------


def test_health_does_not_require_auth() -> None:
    client, _ = _client(allowed={"sk-prod": "key-prod"})
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "api_gateway"


def test_dev_mode_accepts_unauthenticated_requests() -> None:
    client, orchestrator = _client()
    response = client.post("/v1/responses", json={"input": "hi"})

    assert response.status_code == 200
    assert orchestrator.run_calls[0]["api_key_id"] == "anonymous"


def test_missing_auth_header_rejected_when_keys_configured() -> None:
    client, _ = _client(allowed={"sk-prod": "key-prod"})
    response = client.post("/v1/responses", json={"input": "hi"})

    assert response.status_code == 401


def test_wrong_key_rejected() -> None:
    client, _ = _client(allowed={"sk-prod": "key-prod"})
    response = client.post(
        "/v1/responses",
        json={"input": "hi"},
        headers={"Authorization": "Bearer sk-other"},
    )

    assert response.status_code == 401


def test_valid_key_audited_under_configured_id() -> None:
    client, orchestrator = _client(allowed={"sk-prod": "key-prod"})
    response = client.post(
        "/v1/responses",
        json={"input": "hi"},
        headers={"Authorization": "Bearer sk-prod"},
    )

    assert response.status_code == 200
    assert orchestrator.run_calls[0]["api_key_id"] == "key-prod"


# --- Request parsing -------------------------------------------------------


def test_string_input_becomes_single_user_message() -> None:
    client, orchestrator = _client()
    client.post("/v1/responses", json={"input": "hi"})

    messages = orchestrator.run_calls[0]["messages"]
    assert messages == [ChatMessage(role=Role.USER, content="hi")]


def test_array_input_preserves_roles_and_order() -> None:
    client, orchestrator = _client()
    client.post(
        "/v1/responses",
        json={
            "input": [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "ack"},
                {"role": "user", "content": "second"},
            ]
        },
    )

    messages = orchestrator.run_calls[0]["messages"]
    assert [m.content for m in messages] == ["first", "ack", "second"]
    assert [m.role for m in messages] == [Role.USER, Role.ASSISTANT, Role.USER]


def test_instructions_prepended_as_system_message() -> None:
    client, orchestrator = _client()
    client.post(
        "/v1/responses",
        json={"input": "hi", "instructions": "be terse"},
    )

    messages = orchestrator.run_calls[0]["messages"]
    assert messages[0].role is Role.SYSTEM
    assert messages[0].content == "be terse"
    assert messages[1].role is Role.USER


def test_collection_override_forwarded_to_orchestrator() -> None:
    client, orchestrator = _client()
    client.post(
        "/v1/responses",
        json={"input": "hi", "collection": "alt-kb"},
    )

    assert orchestrator.run_calls[0]["collection"] == "alt-kb"


def test_missing_input_rejected() -> None:
    client, _ = _client()
    response = client.post("/v1/responses", json={})
    assert response.status_code == 400
    assert "input" in response.json()["detail"]


def test_unknown_role_rejected() -> None:
    client, _ = _client()
    response = client.post(
        "/v1/responses",
        json={"input": [{"role": "wizard", "content": "??"}]},
    )
    assert response.status_code == 400
    assert "role" in response.json()["detail"]


def test_non_object_body_rejected() -> None:
    client, _ = _client()
    response = client.post("/v1/responses", json=["not", "an", "object"])
    assert response.status_code == 400


# --- Non-streaming response shape -----------------------------------------


def test_non_streaming_response_carries_responses_api_shape() -> None:
    client, _ = _client()
    response = client.post("/v1/responses", json={"input": "hi"})

    body = response.json()
    assert body["object"] == "response"
    assert body["model"] == "fake-gen"
    assert body["id"].startswith("resp_")
    assert body["output"][0]["role"] == "assistant"
    assert body["output"][0]["content"][0]["type"] == "output_text"
    assert body["output"][0]["content"][0]["text"] == "the answer"
    assert body["usage"] == {"input_tokens": 11, "output_tokens": 7}


# --- Streaming response shape ---------------------------------------------


def test_streaming_response_emits_deltas_then_completion() -> None:
    client, orchestrator = _client()
    with client.stream(
        "POST",
        "/v1/responses",
        json={"input": "hi", "stream": True},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = list(_parse_sse(response.iter_lines()))

    delta_events = [e for e in events if e["event"] == RESPONSES_TEXT_DELTA_EVENT]
    completed = [e for e in events if e["event"] == RESPONSES_DONE_EVENT]

    assert len(delta_events) == 2
    assert "".join(json.loads(e["data"])["delta"] for e in delta_events) == "the answer"
    assert len(completed) == 1
    assert json.loads(completed[0]["data"])["usage"] == {
        "input_tokens": 11,
        "output_tokens": 7,
    }
    assert orchestrator.stream_calls  # stream path was exercised


def _parse_sse(lines: Iterator[str]) -> Iterator[dict[str, str]]:
    """Yield {'event': ..., 'data': ...} for each completed SSE record."""
    current: dict[str, str] = {}
    for raw in lines:
        line = raw.strip() if isinstance(raw, str) else raw.decode().strip()
        if not line:
            if current:
                yield current
                current = {}
            continue
        if line.startswith("event:"):
            current["event"] = line[len("event:") :].strip()
        elif line.startswith("data:"):
            current["data"] = line[len("data:") :].strip()
    if current:
        yield current


# --- Parser direct tests ---------------------------------------------------


def test_parse_responses_request_rejects_empty_messages_array() -> None:
    from services.api_gateway.application.responses_api import parse_responses_request

    with pytest.raises(ValueError, match="at least one"):
        parse_responses_request({"input": []})
