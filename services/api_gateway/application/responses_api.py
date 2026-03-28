"""OpenAI Responses-API-shaped request/response translation.

Translates between the gateway's HTTP boundary (a subset of the OpenAI
Responses API) and the contracts' `ChatMessage` / `GenerationResponse`
DTOs. The full Responses API surface is large; the prototype supports
the subset OpenWebUI and similar clients need:

  - Request:  `{"input": <string|messages>, "instructions": <str?>, "stream": <bool>}`
  - Response: `{"id", "model", "output": [...], "usage": {...}}`
  - Streaming: SSE with `response.output_text.delta` and `response.completed` events.

Additional advanced fields (`tools`, `truncation`, `previous_response_id`,
`response_format`, ...) are not yet supported and are ignored.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Iterator
from typing import Any

from contracts import (
    ChatMessage,
    GenerationChunk,
    GenerationResponse,
    Role,
)

__all__ = [
    "RESPONSES_DONE_EVENT",
    "RESPONSES_TEXT_DELTA_EVENT",
    "ResponsesRequest",
    "make_response_id",
    "non_streaming_response_body",
    "parse_responses_request",
    "sse_stream",
]

RESPONSES_TEXT_DELTA_EVENT = "response.output_text.delta"
RESPONSES_DONE_EVENT = "response.completed"


class ResponsesRequest:
    """Parsed Responses-shaped request body."""

    __slots__ = ("collection", "instructions", "messages", "stream")

    def __init__(
        self,
        *,
        messages: list[ChatMessage],
        instructions: str | None,
        stream: bool,
        collection: str | None,
    ) -> None:
        self.messages = messages
        self.instructions = instructions
        self.stream = stream
        self.collection = collection


def parse_responses_request(body: dict[str, Any]) -> ResponsesRequest:
    """Translate a Responses-API JSON body into a `ResponsesRequest`."""
    raw_input = body.get("input")
    if raw_input is None:
        raise ValueError("missing required field 'input'")

    messages: list[ChatMessage] = []
    if isinstance(raw_input, str):
        messages.append(ChatMessage(role=Role.USER, content=raw_input))
    elif isinstance(raw_input, list):
        for item in raw_input:
            if not isinstance(item, dict):
                raise ValueError(f"input items must be objects, got {type(item).__name__}")
            role = item.get("role")
            content = item.get("content")
            if not isinstance(role, str) or not isinstance(content, str):
                raise ValueError("each input item must have string 'role' and 'content'")
            try:
                parsed_role = Role(role)
            except ValueError as exc:
                raise ValueError(f"unknown role: {role!r}") from exc
            messages.append(ChatMessage(role=parsed_role, content=content))
    else:
        raise ValueError(f"'input' must be string or array, got {type(raw_input).__name__}")

    if not messages:
        raise ValueError("'input' must contain at least one message")

    instructions = body.get("instructions")
    if instructions is not None and not isinstance(instructions, str):
        raise ValueError("'instructions' must be a string when present")

    stream = bool(body.get("stream", False))

    collection = body.get("collection")
    if collection is not None and not isinstance(collection, str):
        raise ValueError("'collection' must be a string when present")

    if instructions:
        # Prepend instructions as a system-role message so the
        # orchestrator's last-user-message extraction still hits the
        # actual user message.
        messages.insert(0, ChatMessage(role=Role.SYSTEM, content=instructions))

    return ResponsesRequest(
        messages=messages,
        instructions=instructions,
        stream=stream,
        collection=collection,
    )


def make_response_id() -> str:
    """Generate an OpenAI-style `resp_...` identifier."""
    return f"resp_{uuid.uuid4().hex}"


def non_streaming_response_body(
    *, response_id: str, response: GenerationResponse
) -> dict[str, Any]:
    """Render a non-streaming Responses-API JSON body for a finished generation."""
    return {
        "id": response_id,
        "object": "response",
        "model": response.model_id,
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [
                    {"type": "output_text", "text": response.text}
                ],
            }
        ],
        "usage": {
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        },
    }


def sse_stream(
    *, response_id: str, chunks: Iterator[GenerationChunk]
) -> Iterator[bytes]:
    """Translate `GenerationChunk` iterator into Responses-API SSE bytes.

    Emits one `response.output_text.delta` event per non-empty delta
    plus a final `response.completed` event carrying usage.
    """
    last_usage_input = 0
    last_usage_output = 0
    for chunk in chunks:
        if chunk.delta:
            event = {
                "type": RESPONSES_TEXT_DELTA_EVENT,
                "response_id": response_id,
                "delta": chunk.delta,
            }
            yield _sse_frame(RESPONSES_TEXT_DELTA_EVENT, event)
        if chunk.usage is not None:
            last_usage_input = chunk.usage.prompt_tokens
            last_usage_output = chunk.usage.completion_tokens
    completion = {
        "type": RESPONSES_DONE_EVENT,
        "response_id": response_id,
        "usage": {
            "input_tokens": last_usage_input,
            "output_tokens": last_usage_output,
        },
    }
    yield _sse_frame(RESPONSES_DONE_EVENT, completion)


def _sse_frame(event: str, payload: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode()
