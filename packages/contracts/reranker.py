"""Reranker contract — re-scores retrieved chunks by relevance to the query."""

from __future__ import annotations

from typing import Protocol

from contracts.dto import RerankedChunk, ScoredChunk

__all__ = ["Reranker"]


class Reranker(Protocol):
    """Hides whether the implementation uses a cross-encoder, LLM-as-reranker,
    or any other method. Produces `RerankedChunk` whose `rerank_score` is
    semantically distinct from vector similarity score.
    """

    def rerank(
        self,
        query: str,
        scored_chunks: list[ScoredChunk],
        top_k: int,
    ) -> list[RerankedChunk]:
        """Return `top_k` chunks re-ordered with per-chunk rerank scores."""
        ...

    def get_model_id(self) -> str:
        """Identifier of the reranking model in use."""
        ...
