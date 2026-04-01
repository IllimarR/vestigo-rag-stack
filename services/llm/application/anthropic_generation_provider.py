"""Anthropic `GenerationProvider` — Phase 5 second generation backend.

This adapter speaks Anthropic's native Messages API (`/v1/messages`)
rather than the OpenAI `/v1/chat/completions` shape. The wire protocol
diverges in five places, which is exactly why this swap is interesting
as thesis evidence:

  1. **Endpoint** — `/v1/messages`, not `/v1/chat/completions`.
  2. **Auth** — `x-api-key: <key>` plus `anthropic-version: 2023-06-01`.
     No Bearer header.
  3. **System prompt** — top-level `system` field. Anthropic rejects
     system-role entries inside `messages`.
  4. **`max_tokens` is required.** The SDK accepts an int; this adapter
     applies `DEFAULT_MAX_TOKENS` when the caller doesn't set one.
  5. **Streaming** — server-sent events typed by `event:` lines
     (`message_start`, `content_block_delta`, `message_delta`,
     `message_stop`, ...). Text deltas live in `content_block_delta`
     events whose `delta.type == "text_delta"`. Token usage arrives in
     two pieces: `input_tokens` in `message_start`,
     `output_tokens` in `message_delta`.

We hand-roll the wire protocol over `httpx` rather than depend on
the `anthropic` SDK so the dependency surface stays minimal and the
swap demo doesn't require an extra pip package.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
from contracts import (
    GenerationChunk,
    GenerationRequest,
    GenerationResponse,
    TokenUsage,
)

from services.llm.application._retry import execute_with_retry

__all__ = ["AnthropicGenerationProvider"]

DEFAULT_TIMEOUT = 60.0
DEFAULT_MAX_TOKENS = 4096
DEFAULT_API_VERSION = "2023-06-01"


class AnthropicGenerationProvider:
    """Anthropic Messages-API client (sync + SSE streaming)."""

    def __init__(
        self,
        endpoint: str,
        model_name: str,
        *,
        api_key: str,
        api_version: str = DEFAULT_API_VERSION,
        default_max_tokens: int = DEFAULT_MAX_TOKENS,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._model_name = model_name
        self._api_key = api_key
        self._api_version = api_version
        self._default_max_tokens = default_max_tokens
        self._client = client or httpx.Client(timeout=timeout)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        body = self._build_body(request, stream=False)
        response = execute_with_retry(
            lambda: self._client.post(
                f"{self._endpoint}/messages",
                json=body,
                headers=self._headers(),
            )
        )
        response.raise_for_status()
        payload = response.json()

        text = _collect_text_blocks(payload.get("content"))
        usage = _parse_usage(payload.get("usage"))
        model_id = payload.get("model") or self._model_name
        return GenerationResponse(text=text, usage=usage, model_id=model_id)

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        # Streaming intentionally does not use `execute_with_retry`: once
        # Anthropic has started emitting `content_block_delta` events the
        # stream cannot be resumed, and replaying the request would risk
        # double-billing the user. SSE callers handle stream errors above.
        body = self._build_body(request, stream=True)
        input_tokens = 0
        output_tokens = 0
        with self._client.stream(
            "POST",
            f"{self._endpoint}/messages",
            json=body,
            headers=self._headers(),
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines():
                line = (
                    raw_line.strip()
                    if isinstance(raw_line, str)
                    else raw_line.decode().strip()
                )
                if not line or not line.startswith("data:"):
                    # `event:` lines and blank separators are decorative —
                    # the `type` is also inside the `data:` JSON payload.
                    continue
                payload_str = line[len("data:") :].strip()
                if not payload_str:
                    continue
                event = json.loads(payload_str)
                event_type = event.get("type")

                if event_type == "message_start":
                    usage_raw = (event.get("message") or {}).get("usage") or {}
                    input_tokens = int(usage_raw.get("input_tokens") or 0)
                elif event_type == "content_block_delta":
                    delta = event.get("delta") or {}
                    if delta.get("type") == "text_delta":
                        text = delta.get("text") or ""
                        if text:
                            yield GenerationChunk(delta=text, usage=None)
                elif event_type == "message_delta":
                    usage_raw = event.get("usage") or {}
                    output_tokens = int(usage_raw.get("output_tokens") or 0)
                elif event_type == "message_stop":
                    yield GenerationChunk(
                        delta="",
                        usage=TokenUsage(
                            prompt_tokens=input_tokens,
                            completion_tokens=output_tokens,
                        ),
                    )
                    return

    def get_model_id(self) -> str:
        return self._model_name

    # --- Internals -----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self._api_key,
            "anthropic-version": self._api_version,
        }

    def _build_body(self, request: GenerationRequest, *, stream: bool) -> dict[str, Any]:
        # Anthropic rejects system-role entries inside `messages` — the
        # system prompt is a top-level field.
        messages = [
            {"role": message.role.value, "content": message.content}
            for message in request.messages
        ]

        params = request.parameters
        body: dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "max_tokens": params.max_tokens or self._default_max_tokens,
            "stream": stream,
        }
        if request.system_prompt:
            body["system"] = request.system_prompt
        if params.temperature is not None:
            body["temperature"] = params.temperature
        if params.top_p is not None:
            body["top_p"] = params.top_p
        for key, value in params.extra.items():
            body.setdefault(key, value)
        return body


def _collect_text_blocks(blocks: Any) -> str:
    """Concatenate `text` from all text-type content blocks; tolerate None."""
    if not isinstance(blocks, list):
        return ""
    pieces: list[str] = []
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                pieces.append(text)
    return "".join(pieces)


def _parse_usage(raw: Any) -> TokenUsage:
    if not isinstance(raw, dict):
        return TokenUsage(prompt_tokens=0, completion_tokens=0)
    return TokenUsage(
        prompt_tokens=int(raw.get("input_tokens") or 0),
        completion_tokens=int(raw.get("output_tokens") or 0),
    )
