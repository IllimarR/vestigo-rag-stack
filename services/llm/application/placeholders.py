"""Placeholder implementations for embedding, reranking, and generation."""

from __future__ import annotations

from collections.abc import Iterator

from contracts import (
    GenerationChunk,
    GenerationRequest,
    GenerationResponse,
    RerankedChunk,
    ScoredChunk,
)

__all__ = [
    "NotImplementedEmbeddingProvider",
    "NotImplementedGenerationProvider",
    "NotImplementedReranker",
]


def _not_implemented(contract: str) -> NotImplementedError:
    return NotImplementedError(
        f"{contract} is a Phase 1 placeholder. Bind a concrete implementation "
        "in the composition root before invoking this method."
    )


class NotImplementedEmbeddingProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise _not_implemented("EmbeddingProvider")

    def get_dimension(self) -> int:
        raise _not_implemented("EmbeddingProvider")

    def get_model_id(self) -> str:
        raise _not_implemented("EmbeddingProvider")


class NotImplementedReranker:
    def rerank(
        self,
        query: str,
        scored_chunks: list[ScoredChunk],
        top_k: int,
    ) -> list[RerankedChunk]:
        raise _not_implemented("Reranker")

    def get_model_id(self) -> str:
        raise _not_implemented("Reranker")


class NotImplementedGenerationProvider:
    def generate(self, request: GenerationRequest) -> GenerationResponse:
        raise _not_implemented("GenerationProvider")

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        raise _not_implemented("GenerationProvider")

    def get_model_id(self) -> str:
        raise _not_implemented("GenerationProvider")
