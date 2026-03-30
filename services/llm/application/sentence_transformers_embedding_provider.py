"""Local `EmbeddingProvider` — Phase 5 second implementation.

This adapter runs an embedding model in-process via sentence-transformers'
`SentenceTransformer` class. Unlike `OpenAIHttpEmbeddingProvider`, there's
no HTTP hop: the model weights live on disk, the GPU/CPU does the work,
and dimension is known the moment the model loads.

Decoupling from the model library
---------------------------------
The class doesn't import sentence-transformers, transformers, or torch
at module level. Instead it takes an `encoder` callable mapping a list
of texts to per-text float vectors plus a `dimension`. Production wiring
goes through `sentence_transformers_encoder(model_name)` which lazily
loads the underlying model on first call. Tests inject a tiny fake
encoder and never trigger torch — same trick as `CrossEncoderReranker`.

Two properties intact:
* the contract test suite runs without pulling a real model;
* swapping to a different local library (FlagEmbedding, transformers
  pipeline, an ONNX runtime, ...) is a builder change, not an adapter
  rewrite.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

__all__ = [
    "Encoder",
    "SentenceTransformersEmbeddingProvider",
    "sentence_transformers_encoder",
]


Encoder = Callable[[list[str]], list[list[float]]]


class SentenceTransformersEmbeddingProvider:
    """`EmbeddingProvider` driven by an injected local encoder."""

    def __init__(
        self,
        *,
        encoder: Encoder,
        model_name: str,
        dimension: int | None = None,
    ) -> None:
        self._encoder = encoder
        self._model_name = model_name
        self._dimension_cache: int | None = dimension
        self._dimension_lock = threading.Lock()

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._encoder(texts)
        if len(vectors) != len(texts):
            raise RuntimeError(
                f"encoder returned {len(vectors)} vectors for "
                f"{len(texts)} inputs — encoder contract violated."
            )
        return [list(map(float, v)) for v in vectors]

    def get_dimension(self) -> int:
        with self._dimension_lock:
            if self._dimension_cache is None:
                probe = self._encoder(["."])
                if not probe or not probe[0]:
                    raise RuntimeError(
                        "Encoder returned no vector for the dimension probe."
                    )
                self._dimension_cache = len(probe[0])
            return self._dimension_cache

    def get_model_id(self) -> str:
        return self._model_name


def sentence_transformers_encoder(model_name: str) -> Encoder:
    """Return an `Encoder` backed by sentence-transformers' `SentenceTransformer`.

    The underlying model is loaded the first time the returned encoder is
    invoked, so importing this module does not trigger a torch import.
    """
    model: Any = None
    lock = threading.Lock()

    def encode(texts: list[str]) -> list[list[float]]:
        nonlocal model
        if model is None:
            with lock:
                if model is None:
                    from sentence_transformers import SentenceTransformer  # noqa: PLC0415 — lazy

                    model = SentenceTransformer(model_name)
        raw = model.encode(texts, convert_to_numpy=False)
        return [[float(x) for x in vec] for vec in raw]

    return encode
