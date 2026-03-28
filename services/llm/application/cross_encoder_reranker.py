"""Cross-encoder `Reranker` — Phase 3 first real implementation.

A cross-encoder takes a `(query, candidate)` pair and produces a single
relevance score; unlike the bi-encoder used during retrieval, the
encoder is allowed to attend across the query and candidate jointly, so
it produces sharper relevance signals at the cost of running once per
pair. Typical models: `BAAI/bge-reranker-base`, `cross-encoder/ms-marco-MiniLM-L-6-v2`.

Decoupling from the model library
---------------------------------
The class doesn't import sentence-transformers, transformers, or torch
at module level. Instead it takes a `scorer` callable mapping a list of
`(query, candidate)` pairs to per-pair float scores. Production wiring
goes through `sentence_transformers_scorer(model_name)` which lazily
loads the underlying model on first call. Tests inject a tiny fake
scorer and never trigger torch.

This keeps two properties intact:
* the contract test suite runs without pulling a real model;
* swapping to a different scoring library (FlagEmbedding, transformers
  pipeline, an HTTP service, ...) is a builder change, not an adapter
  rewrite.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from contracts import RerankedChunk, ScoredChunk

__all__ = [
    "CrossEncoderReranker",
    "Scorer",
    "sentence_transformers_scorer",
]


Scorer = Callable[[list[tuple[str, str]]], list[float]]


class CrossEncoderReranker:
    """`Reranker` driven by an injected pairwise scorer."""

    def __init__(self, *, scorer: Scorer, model_name: str) -> None:
        self._scorer = scorer
        self._model_name = model_name

    def rerank(
        self,
        query: str,
        scored_chunks: list[ScoredChunk],
        top_k: int,
    ) -> list[RerankedChunk]:
        if not scored_chunks:
            return []

        pairs = [(query, scored.chunk.text) for scored in scored_chunks]
        raw_scores = list(self._scorer(pairs))
        if len(raw_scores) != len(scored_chunks):
            raise RuntimeError(
                f"scorer returned {len(raw_scores)} scores for "
                f"{len(scored_chunks)} pairs — scorer contract violated."
            )

        # Stable secondary sort by original rank so ties are deterministic.
        order = sorted(
            range(len(scored_chunks)),
            key=lambda i: (-float(raw_scores[i]), i),
        )
        limit = max(0, top_k)
        return [
            RerankedChunk(
                chunk=scored_chunks[idx].chunk,
                similarity_score=scored_chunks[idx].similarity_score,
                rerank_score=float(raw_scores[idx]),
                final_rank=final,
            )
            for final, idx in enumerate(order[:limit])
        ]

    def get_model_id(self) -> str:
        return self._model_name


def sentence_transformers_scorer(model_name: str) -> Scorer:
    """Return a `Scorer` backed by sentence-transformers' `CrossEncoder`.

    The underlying model is loaded the first time the returned scorer is
    invoked, so importing this module does not trigger a torch import.
    """
    cross_encoder: Any = None

    def score(pairs: list[tuple[str, str]]) -> list[float]:
        nonlocal cross_encoder
        if cross_encoder is None:
            from sentence_transformers import CrossEncoder  # noqa: PLC0415 — lazy

            cross_encoder = CrossEncoder(model_name)
        raw = cross_encoder.predict(pairs)
        return [float(x) for x in raw]

    return score
