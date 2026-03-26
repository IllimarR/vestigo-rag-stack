"""OpenAI-compatible HTTP embedding provider — Phase 2 first `EmbeddingProvider`.

Targets any server that speaks the OpenAI `/v1/embeddings` shape: OpenAI
itself, Ollama, LM Studio, LocalAI, llamacpp-server, vLLM, etc. The
adapter doesn't care which — it just POSTs `{"model": ..., "input": [...]}`
and reads back the `data[i].embedding` arrays.

The adapter is fully self-contained:
  - Constructor takes an optional `httpx.Client` so tests can inject a
    `MockTransport` and production code can pool connections.
  - `get_dimension()` lazily probes the model on first call by embedding
    a sentinel string, then caches the result.

An API key is optional (Ollama and LM Studio don't require one) — pass
`api_key` to enable Bearer auth.
"""

from __future__ import annotations

import threading

import httpx

__all__ = ["OpenAIHttpEmbeddingProvider"]

DEFAULT_TIMEOUT = 30.0
_DIMENSION_PROBE = "."


class OpenAIHttpEmbeddingProvider:
    """OpenAI-compatible `/v1/embeddings` client."""

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
        self._dimension_cache: int | None = None
        self._dimension_lock = threading.Lock()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        headers: dict[str, str] = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        response = self._client.post(
            f"{self._endpoint}/embeddings",
            json={"model": self._model_name, "input": texts},
            headers=headers,
        )
        response.raise_for_status()
        payload = response.json()
        items = sorted(payload["data"], key=lambda item: item["index"])
        return [list(item["embedding"]) for item in items]

    def get_dimension(self) -> int:
        with self._dimension_lock:
            if self._dimension_cache is None:
                probe = self.embed([_DIMENSION_PROBE])
                if not probe or not probe[0]:
                    raise RuntimeError(
                        "Embedding server returned no vector for the dimension probe."
                    )
                self._dimension_cache = len(probe[0])
            return self._dimension_cache

    def get_model_id(self) -> str:
        return self._model_name
