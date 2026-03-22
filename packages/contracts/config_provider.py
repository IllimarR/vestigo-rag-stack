"""ConfigProvider contract — single source of truth for application-level config.

Scope: embedding, reranking, generation, chunking, RAG prompt template, and
default collection. Infrastructure-level bindings (which vector store backend,
which audit backend) are NOT managed here — they live in `.env` / Docker.
"""

from __future__ import annotations

from typing import Protocol

from contracts.dto import (
    ChunkConfig,
    EmbeddingConfig,
    GenerationConfig,
    RerankerConfig,
)

__all__ = ["ConfigProvider"]


class ConfigProvider(Protocol):
    """Modules must never read environment variables or hardcoded values
    for application-level configuration — they query this contract instead.
    """

    # --- Reads ---

    def get_embedding_config(self) -> EmbeddingConfig: ...
    def get_reranker_config(self) -> RerankerConfig: ...
    def get_generation_config(self) -> GenerationConfig: ...
    def get_chunking_config(self) -> ChunkConfig: ...
    def get_rag_prompt_template(self) -> str: ...
    def get_default_collection(self) -> str: ...

    # --- Writes ---

    def set_embedding_config(self, config: EmbeddingConfig) -> None: ...
    def set_reranker_config(self, config: RerankerConfig) -> None: ...
    def set_generation_config(self, config: GenerationConfig) -> None: ...
    def set_chunking_config(self, config: ChunkConfig) -> None: ...
    def set_rag_prompt_template(self, template: str) -> None: ...
    def set_default_collection(self, collection: str) -> None: ...
