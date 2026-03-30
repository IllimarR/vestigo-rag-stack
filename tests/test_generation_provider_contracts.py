"""Contract-compliance suite for every `GenerationProvider` implementation.

The OpenAI-compatible HTTP adapter is exercised against an
`httpx.MockTransport` simulating the OpenAI `/v1/chat/completions`
shape (both unary JSON responses and SSE streaming). No real
generation backend is contacted.

Register a new backend by appending its factory to `_PROVIDERS`; the
same body of tests then runs against it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from contracts import (
    ChatMessage,
    GenerationProvider,
    GenerationRequest,
    ModelParameters,
    Role,
)

from services.llm.application.anthropic_generation_provider import (
    AnthropicGenerationProvider,
)
from services.llm.application.openai_http_generation_provider import (
    OpenAIHttpGenerationProvider,
)

Factory = Callable[[], GenerationProvider]


# --- Mock OpenAI /v1/chat/completions server -------------------------------


def _build_stream_body(deltas: list[str], usage: dict[str, int] | None) -> bytes:
    """Render an OpenAI-style SSE stream from text deltas plus optional usage."""
    parts: list[str] = []
    for delta in deltas:
        event: dict[str, Any] = {"choices": [{"delta": {"content": delta}}]}
        parts.append(f"data: {json.dumps(event)}\n\n")
    if usage is not None:
        event = {"choices": [{"delta": {}}], "usage": usage}
        parts.append(f"data: {json.dumps(event)}\n\n")
    parts.append("data: [DONE]\n\n")
    return "".join(parts).encode()


def _stub_openai_transport() -> httpx.MockTransport:
    """Return a transport that answers /chat/completions for both modes."""

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/chat/completions"):
            return httpx.Response(404, json={"error": "not found"})

        body: dict[str, Any] = json.loads(request.content)
        is_stream = bool(body.get("stream"))
        # Echo the last user message so tests can assert routing.
        user_messages = [m for m in body["messages"] if m["role"] == "user"]
        echo_text = user_messages[-1]["content"] if user_messages else ""

        if is_stream:
            deltas = list(echo_text) or [""]
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_build_stream_body(
                    deltas,
                    usage={"prompt_tokens": 5, "completion_tokens": len(deltas)},
                ),
            )

        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-stub",
                "model": body["model"],
                "choices": [
                    {
                        "message": {"role": "assistant", "content": echo_text},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": len(echo_text)},
            },
        )

    return httpx.MockTransport(handler)


def _openai_http_factory() -> Factory:
    def build() -> GenerationProvider:
        transport = _stub_openai_transport()
        client = httpx.Client(transport=transport, base_url="http://stub")
        return OpenAIHttpGenerationProvider(
            endpoint="http://stub/v1",
            model_name="stub-model",
            client=client,
        )

    return build


# --- Mock Anthropic /v1/messages server ------------------------------------


def _build_anthropic_stream_body(deltas: list[str]) -> bytes:
    """Render Anthropic's SSE stream from text deltas.

    Mirrors what `claude-3-5-sonnet`-class endpoints emit: a
    `message_start` opens the stream with `input_tokens`, each delta is
    a `content_block_delta/text_delta` event, `message_delta` reports
    `output_tokens`, and `message_stop` closes it.
    """
    def event(event_type: str, payload: dict[str, Any]) -> str:
        return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"

    parts: list[str] = [
        event(
            "message_start",
            {"type": "message_start", "message": {"usage": {"input_tokens": 5}}},
        ),
        event(
            "content_block_start",
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "text", "text": ""},
            },
        ),
    ]
    for delta in deltas:
        parts.append(
            event(
                "content_block_delta",
                {
                    "type": "content_block_delta",
                    "index": 0,
                    "delta": {"type": "text_delta", "text": delta},
                },
            )
        )
    parts.append(
        event(
            "content_block_stop",
            {"type": "content_block_stop", "index": 0},
        )
    )
    parts.append(
        event(
            "message_delta",
            {"type": "message_delta", "usage": {"output_tokens": len(deltas)}},
        )
    )
    parts.append(event("message_stop", {"type": "message_stop"}))
    return "".join(parts).encode()


def _stub_anthropic_transport() -> httpx.MockTransport:
    """Echo the last user message via Anthropic's content-block shape."""

    def handler(request: httpx.Request) -> httpx.Response:
        if not request.url.path.endswith("/messages"):
            return httpx.Response(404, json={"error": "not found"})

        body: dict[str, Any] = json.loads(request.content)
        is_stream = bool(body.get("stream"))
        user_messages = [m for m in body["messages"] if m["role"] == "user"]
        echo_text = user_messages[-1]["content"] if user_messages else ""

        if is_stream:
            deltas = list(echo_text) or [""]
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content=_build_anthropic_stream_body(deltas),
            )

        return httpx.Response(
            200,
            json={
                "id": "msg_stub",
                "type": "message",
                "role": "assistant",
                "model": body["model"],
                "content": [{"type": "text", "text": echo_text}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 5, "output_tokens": len(echo_text)},
            },
        )

    return httpx.MockTransport(handler)


def _anthropic_factory() -> Factory:
    def build() -> GenerationProvider:
        transport = _stub_anthropic_transport()
        client = httpx.Client(transport=transport, base_url="http://stub")
        return AnthropicGenerationProvider(
            endpoint="http://stub/v1",
            model_name="stub-claude",
            api_key="sk-ant-test",
            client=client,
        )

    return build


_PROVIDERS: dict[str, Factory] = {
    "openai_http": _openai_http_factory(),
    "anthropic": _anthropic_factory(),
}


@pytest.fixture(params=sorted(_PROVIDERS), ids=sorted(_PROVIDERS))
def provider(request: pytest.FixtureRequest) -> GenerationProvider:
    return _PROVIDERS[request.param]()


# --- Helpers ---------------------------------------------------------------


def _request(
    *,
    user: str,
    system: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> GenerationRequest:
    return GenerationRequest(
        system_prompt=system,
        messages=(ChatMessage(role=Role.USER, content=user),),
        parameters=ModelParameters(temperature=temperature, max_tokens=max_tokens),
    )


# --- Tests -----------------------------------------------------------------


def test_generate_returns_full_response(provider: GenerationProvider) -> None:
    response = provider.generate(_request(user="hello there"))

    assert response.text == "hello there"
    assert response.model_id  # any non-empty identifier
    assert response.usage.completion_tokens == len("hello there")


def test_generate_passes_system_prompt(provider: GenerationProvider) -> None:
    response = provider.generate(_request(user="x", system="be terse"))
    # Stub echoes only the user message — system prompt is checked separately
    # below; this guards against the system being concatenated into the user.
    assert response.text == "x"


def test_generate_stream_yields_deltas_then_usage(provider: GenerationProvider) -> None:
    chunks = list(provider.generate_stream(_request(user="hi")))

    text = "".join(chunk.delta for chunk in chunks)
    assert text == "hi"

    final = chunks[-1]
    assert final.usage is not None
    assert final.usage.completion_tokens == 2  # one delta per character ("h", "i")


def test_get_model_id_returns_configured_name(provider: GenerationProvider) -> None:
    assert isinstance(provider.get_model_id(), str)
    assert provider.get_model_id()


def test_openai_http_emits_system_role_first() -> None:
    """Implementation-specific: system prompts must be prepended as a
    system-role message, not stuffed into the user content.
    """
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "x",
                "model": "stub",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://stub")
    provider = OpenAIHttpGenerationProvider(
        endpoint="http://stub/v1",
        model_name="stub",
        client=client,
    )

    provider.generate(_request(user="hi", system="be terse"))

    messages = captured["body"]["messages"]
    assert messages[0] == {"role": "system", "content": "be terse"}
    assert messages[1] == {"role": "user", "content": "hi"}


def test_openai_http_forwards_temperature_and_max_tokens() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "x",
                "model": "stub",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://stub")
    provider = OpenAIHttpGenerationProvider(
        endpoint="http://stub/v1",
        model_name="stub",
        client=client,
    )

    provider.generate(_request(user="x", temperature=0.3, max_tokens=42))

    body = captured["body"]
    assert body["temperature"] == 0.3
    assert body["max_tokens"] == 42


def test_openai_http_sends_bearer_when_api_key_set() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "id": "x",
                "model": "stub",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://stub")
    provider = OpenAIHttpGenerationProvider(
        endpoint="http://stub/v1",
        model_name="stub",
        api_key="sk-test",
        client=client,
    )

    provider.generate(_request(user="x"))

    assert captured["auth"] == "Bearer sk-test"


# --- Anthropic-specific wire-protocol checks --------------------------------


def _anthropic_capture_handler(
    captured: dict[str, Any],
) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "x",
                "type": "message",
                "role": "assistant",
                "model": "stub-claude",
                "content": [{"type": "text", "text": "ok"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    return handler


def test_anthropic_lifts_system_to_top_level() -> None:
    """System prompts go to `body.system`, never into `messages`.

    Anthropic actively rejects role='system' entries inside `messages`,
    so this isn't a stylistic choice — getting it wrong breaks the wire.
    """
    captured: dict[str, Any] = {}
    client = httpx.Client(
        transport=httpx.MockTransport(_anthropic_capture_handler(captured)),
        base_url="http://stub",
    )
    provider = AnthropicGenerationProvider(
        endpoint="http://stub/v1",
        model_name="stub-claude",
        api_key="sk-ant-test",
        client=client,
    )

    provider.generate(_request(user="hi", system="be terse"))

    body = captured["body"]
    assert body["system"] == "be terse"
    assert all(m["role"] != "system" for m in body["messages"])
    assert body["messages"][0] == {"role": "user", "content": "hi"}


def test_anthropic_sends_x_api_key_and_version_headers() -> None:
    """Bearer auth is OpenAI-shaped; Anthropic uses `x-api-key` + version."""
    captured: dict[str, Any] = {}
    client = httpx.Client(
        transport=httpx.MockTransport(_anthropic_capture_handler(captured)),
        base_url="http://stub",
    )
    provider = AnthropicGenerationProvider(
        endpoint="http://stub/v1",
        model_name="stub-claude",
        api_key="sk-ant-test",
        client=client,
    )

    provider.generate(_request(user="hi"))

    headers = captured["headers"]
    assert headers["x-api-key"] == "sk-ant-test"
    assert headers["anthropic-version"]  # any non-empty version
    assert "authorization" not in headers  # explicitly no Bearer


def test_anthropic_applies_default_max_tokens_when_missing() -> None:
    """Anthropic requires `max_tokens`; the adapter must inject a default."""
    captured: dict[str, Any] = {}
    client = httpx.Client(
        transport=httpx.MockTransport(_anthropic_capture_handler(captured)),
        base_url="http://stub",
    )
    provider = AnthropicGenerationProvider(
        endpoint="http://stub/v1",
        model_name="stub-claude",
        api_key="sk-ant-test",
        default_max_tokens=2048,
        client=client,
    )

    provider.generate(_request(user="hi"))

    assert captured["body"]["max_tokens"] == 2048


def test_anthropic_forwards_explicit_max_tokens() -> None:
    captured: dict[str, Any] = {}
    client = httpx.Client(
        transport=httpx.MockTransport(_anthropic_capture_handler(captured)),
        base_url="http://stub",
    )
    provider = AnthropicGenerationProvider(
        endpoint="http://stub/v1",
        model_name="stub-claude",
        api_key="sk-ant-test",
        client=client,
    )

    provider.generate(_request(user="hi", max_tokens=42))

    assert captured["body"]["max_tokens"] == 42


def test_anthropic_response_concatenates_text_blocks() -> None:
    """Anthropic's `content` is a list of typed blocks; only `text` blocks contribute."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "x",
                "type": "message",
                "role": "assistant",
                "model": "stub-claude",
                "content": [
                    {"type": "text", "text": "Hello "},
                    {"type": "tool_use", "name": "skip_me"},
                    {"type": "text", "text": "world"},
                ],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 3, "output_tokens": 2},
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://stub")
    provider = AnthropicGenerationProvider(
        endpoint="http://stub/v1",
        model_name="stub-claude",
        api_key="sk-ant-test",
        client=client,
    )

    response = provider.generate(_request(user="x"))

    assert response.text == "Hello world"
    assert response.usage.prompt_tokens == 3
    assert response.usage.completion_tokens == 2
