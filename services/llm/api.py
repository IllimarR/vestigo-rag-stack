"""Public boundary of the LLM service — in-process only.

There is no external HTTP surface for the LLM service; it's a library that
exposes implementations of `EmbeddingProvider`, `Reranker`, and
`GenerationProvider` for the composition root to wire into callers.
"""

from __future__ import annotations

from services.llm.application.openai_http_embedding_provider import (
    OpenAIHttpEmbeddingProvider,
)
from services.llm.application.openai_http_generation_provider import (
    OpenAIHttpGenerationProvider,
)
from services.llm.application.placeholders import (
    NotImplementedEmbeddingProvider,
    NotImplementedGenerationProvider,
    NotImplementedReranker,
)

__all__ = [
    "NotImplementedEmbeddingProvider",
    "NotImplementedGenerationProvider",
    "NotImplementedReranker",
    "OpenAIHttpEmbeddingProvider",
    "OpenAIHttpGenerationProvider",
]
