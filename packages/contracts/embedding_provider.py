"""EmbeddingProvider contract — generates vector embeddings for text."""

from __future__ import annotations

from typing import Protocol

__all__ = ["EmbeddingProvider"]


class EmbeddingProvider(Protocol):
    """Independently configurable from reranking and generation.

    Implementations may be local (sentence-transformers, E5) or remote
    (OpenAI-compatible embedding API).
    """

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text, in the same order."""
        ...

    def get_dimension(self) -> int:
        """Dimensionality of the embedding vectors this provider produces."""
        ...

    def get_model_id(self) -> str:
        """Identifier of the embedding model currently in use."""
        ...
