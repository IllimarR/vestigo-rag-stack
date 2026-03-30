"""Public boundary of the LLM service — in-process only.

There is no external HTTP surface for the LLM service; it's a library that
exposes implementations of `EmbeddingProvider`, `Reranker`, and
`GenerationProvider` for the composition root to wire into callers.
"""

from __future__ import annotations

from services.llm.application.cross_encoder_reranker import (
    CrossEncoderReranker,
    sentence_transformers_scorer,
)
from services.llm.application.llm_reranker import LLMReranker
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
from services.llm.application.sentence_transformers_embedding_provider import (
    SentenceTransformersEmbeddingProvider,
    sentence_transformers_encoder,
)

__all__ = [
    "CrossEncoderReranker",
    "LLMReranker",
    "NotImplementedEmbeddingProvider",
    "NotImplementedGenerationProvider",
    "NotImplementedReranker",
    "OpenAIHttpEmbeddingProvider",
    "OpenAIHttpGenerationProvider",
    "SentenceTransformersEmbeddingProvider",
    "sentence_transformers_encoder",
    "sentence_transformers_scorer",
]
