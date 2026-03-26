"""Contract-compliance suite for every `EmbeddingProvider` implementation.

The only registered backend today is the OpenAI-compatible HTTP adapter.
It's tested against an `httpx.MockTransport` that simulates an OpenAI /v1/
embeddings server, so no real endpoint (OpenAI, Ollama, LM Studio) is
required to run the suite.

When a second backend lands (e.g. `SentenceTransformersEmbeddingProvider`),
register its factory in `_PROVIDERS` and the whole suite runs against it.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from contracts import EmbeddingProvider

from services.llm.application.openai_http_embedding_provider import (
    OpenAIHttpEmbeddingProvider,
)

Factory = Callable[[], EmbeddingProvider]


# --- Mock OpenAI /v1/embeddings server -------------------------------------


def _stub_openai_transport(*, dimension: int = 4) -> httpx.MockTransport:
    """Return a MockTransport that answers /embeddings with deterministic vectors.

    For input text `t`, the embedding is a vector of length `dimension` built
    from the character codepoints of `t` — deterministic, so tests can check
    both shape and repeatability.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/embeddings"):
            body: dict[str, Any] = json.loads(request.content)
            texts: list[str] = list(body["input"])
            data = []
            for idx, text in enumerate(texts):
                codes = [float(ord(c)) for c in text] or [0.0]
                # Pad or truncate to `dimension`.
                embedding = (codes * ((dimension // len(codes)) + 1))[:dimension]
                data.append({"embedding": embedding, "index": idx})
            return httpx.Response(
                200,
                json={"data": data, "model": body["model"], "object": "list"},
            )
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


def _openai_http_factory(*, dimension: int = 4) -> Factory:
    def build() -> EmbeddingProvider:
        transport = _stub_openai_transport(dimension=dimension)
        client = httpx.Client(transport=transport, base_url="http://stub")
        return OpenAIHttpEmbeddingProvider(
            endpoint="http://stub/v1",
            model_name="stub-model",
            client=client,
        )

    return build


_PROVIDERS: dict[str, Factory] = {
    "openai_http": _openai_http_factory(dimension=4),
}


@pytest.fixture(params=sorted(_PROVIDERS), ids=sorted(_PROVIDERS))
def provider(request: pytest.FixtureRequest) -> EmbeddingProvider:
    return _PROVIDERS[request.param]()


# --- Shape + contract checks -----------------------------------------------


def test_embed_empty_input_returns_empty(provider: EmbeddingProvider) -> None:
    assert provider.embed([]) == []


def test_embed_single_input_returns_one_vector(provider: EmbeddingProvider) -> None:
    result = provider.embed(["hello"])
    assert len(result) == 1
    assert isinstance(result[0], list)
    assert all(isinstance(v, float) for v in result[0])


def test_embed_preserves_input_order(provider: EmbeddingProvider) -> None:
    result = provider.embed(["a", "bb", "ccc"])
    assert len(result) == 3
    # The stub produces embeddings derived from the text; deterministic.
    # For openai_http: verify they're distinct.
    assert result[0] != result[1]
    assert result[1] != result[2]


def test_embed_is_deterministic(provider: EmbeddingProvider) -> None:
    first = provider.embed(["repeat me"])
    second = provider.embed(["repeat me"])
    assert first == second


def test_all_embeddings_have_same_dimension(provider: EmbeddingProvider) -> None:
    result = provider.embed(["short", "a much longer input text", "x"])
    dims = {len(v) for v in result}
    assert len(dims) == 1


def test_get_dimension_matches_embed_output(provider: EmbeddingProvider) -> None:
    dim = provider.get_dimension()
    result = provider.embed(["anything"])
    assert len(result[0]) == dim


def test_get_dimension_is_cached(provider: EmbeddingProvider) -> None:
    """Multiple `get_dimension()` calls should return the same value without
    (in production) making repeated probe requests. We don't count requests
    here, just check determinism.
    """
    a = provider.get_dimension()
    b = provider.get_dimension()
    assert a == b


def test_get_model_id_returns_non_empty_string(provider: EmbeddingProvider) -> None:
    model_id = provider.get_model_id()
    assert isinstance(model_id, str)
    assert model_id


# --- HTTP-specific behavior -------------------------------------------------


def test_http_provider_sends_bearer_when_api_key_set() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization", "")
        return httpx.Response(
            200,
            json={
                "data": [{"embedding": [0.1, 0.2], "index": 0}],
                "model": "stub",
                "object": "list",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAIHttpEmbeddingProvider(
        endpoint="http://stub/v1",
        model_name="stub",
        api_key="secret-123",
        client=client,
    )
    p.embed(["hi"])
    assert captured["auth"] == "Bearer secret-123"


def test_http_provider_sends_no_bearer_when_api_key_missing() -> None:
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json={
                "data": [{"embedding": [0.1, 0.2], "index": 0}],
                "model": "stub",
                "object": "list",
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAIHttpEmbeddingProvider(
        endpoint="http://stub/v1",
        model_name="stub",
        client=client,
    )
    p.embed(["hi"])
    assert captured["auth"] is None


def test_http_provider_raises_on_non_2xx() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "server exploded"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    p = OpenAIHttpEmbeddingProvider(
        endpoint="http://stub/v1",
        model_name="stub",
        client=client,
    )
    with pytest.raises(httpx.HTTPStatusError):
        p.embed(["hi"])
