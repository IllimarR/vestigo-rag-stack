"""Public boundary of the LLM service — in-process only.

There is no external HTTP surface for the LLM service; it's a library that
exposes implementations of `EmbeddingProvider`, `Reranker`, and
`GenerationProvider` for the composition root to wire into callers.
"""

from __future__ import annotations

from services.llm.application.placeholders import (
    NotImplementedEmbeddingProvider,
    NotImplementedGenerationProvider,
    NotImplementedReranker,
)

__all__ = [
    "NotImplementedEmbeddingProvider",
    "NotImplementedGenerationProvider",
    "NotImplementedReranker",
]
