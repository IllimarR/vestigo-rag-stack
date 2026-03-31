"""OpenAI-compatible HTTP generation provider — Phase 3 first `GenerationProvider`.

Targets any server that speaks the OpenAI `/v1/chat/completions`
shape: vLLM (the thesis-target upstream), OpenAI itself, LM Studio,
llamacpp-server, LocalAI, and similar. The adapter doesn't care which
— it just POSTs `{"model": ..., "messages": [...], ...}` and reads
back the choice content. Streaming follows OpenAI's SSE convention
(`data: {...}` lines terminated by `data: [DONE]`).

The adapter is fully self-contained:
  - Constructor takes an optional `httpx.Client` so tests can inject a
    `MockTransport` for both unary and streaming responses.
  - API key is optional (many self-hosted servers don't require one)
    — pass `api_key` to enable Bearer auth.
  - Streaming yields one `GenerationChunk` per non-empty `content`
    delta plus a final chunk whenever the upstream reports `usage`.

The `GenerationRequest.system_prompt` is prepended as a `system`-role
message when present, so callers don't have to mutate `request.messages`.
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
    Role,
    TokenUsage,
)

__all__ = ["OpenAIHttpGenerationProvider"]

DEFAULT_TIMEOUT = 60.0
_STREAM_DONE = "[DONE]"


class OpenAIHttpGenerationProvider:
    """OpenAI-compatible `/v1/chat/completions` client (sync + SSE streaming)."""

    def __init__(
        self,
        endpoint: str,
        model_name: str,
        *,
        api_key: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._model_name = model_name
        self._api_key = api_key
        self._client = client or httpx.Client(timeout=timeout)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        body = self._build_body(request, stream=False)
        response = self._client.post(
            f"{self._endpoint}/chat/completions",
            json=body,
            headers=self._headers(),
        )
        response.raise_for_status()
        payload = response.json()

        choice = payload["choices"][0]
        message = choice.get("message") or {}
        text = message.get("content") or ""
        usage = _parse_usage(payload.get("usage"))
        model_id = payload.get("model") or self._model_name
        return GenerationResponse(text=text, usage=usage, model_id=model_id)

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        body = self._build_body(request, stream=True)
        with self._client.stream(
            "POST",
            f"{self._endpoint}/chat/completions",
            json=body,
            headers=self._headers(),
        ) as response:
            response.raise_for_status()
            for raw_line in response.iter_lines():
                line = raw_line.strip() if isinstance(raw_line, str) else raw_line.decode().strip()
                if not line or not line.startswith("data:"):
                    continue
                payload_str = line[len("data:") :].strip()
                if payload_str == _STREAM_DONE:
                    return
                event = json.loads(payload_str)

                delta = ""
                if event.get("choices"):
                    delta_obj = event["choices"][0].get("delta") or {}
                    delta = delta_obj.get("content") or ""
                usage = _parse_usage(event.get("usage")) if event.get("usage") else None

                if delta:
                    yield GenerationChunk(delta=delta, usage=usage)
                elif usage is not None:
                    # Some servers send a usage-only frame at the end of the stream.
                    yield GenerationChunk(delta="", usage=usage)

    def get_model_id(self) -> str:
        return self._model_name

    # --- Internals -----------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    def _build_body(self, request: GenerationRequest, *, stream: bool) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if request.system_prompt:
            messages.append({"role": Role.SYSTEM.value, "content": request.system_prompt})
        messages.extend(
            {"role": message.role.value, "content": message.content}
            for message in request.messages
        )

        body: dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "stream": stream,
        }

        params = request.parameters
        if params.temperature is not None:
            body["temperature"] = params.temperature
        if params.top_p is not None:
            body["top_p"] = params.top_p
        if params.max_tokens is not None:
            body["max_tokens"] = params.max_tokens
        for key, value in params.extra.items():
            body.setdefault(key, value)

        return body


def _parse_usage(raw: Any) -> TokenUsage:
    if not raw:
        return TokenUsage(prompt_tokens=0, completion_tokens=0)
    return TokenUsage(
        prompt_tokens=int(raw.get("prompt_tokens") or 0),
        completion_tokens=int(raw.get("completion_tokens") or 0),
    )
