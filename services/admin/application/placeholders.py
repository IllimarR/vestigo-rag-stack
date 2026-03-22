"""Placeholder implementation of ConfigProvider.

ConfigProvider lives in the Admin service per `docs/architecture.md` §7:
"All configuration is read and written through the `ConfigProvider` contract."
The Admin module owns the read/write side of application-level configuration.
"""

from __future__ import annotations

from contracts import (
    ChunkConfig,
    EmbeddingConfig,
    GenerationConfig,
    RerankerConfig,
)

__all__ = ["NotImplementedConfigProvider"]


def _not_implemented() -> NotImplementedError:
    return NotImplementedError(
        "ConfigProvider is a Phase 1 placeholder. Bind a file-based (Phase 1) "
        "or database-backed (Phase 4) implementation in the composition root."
    )


class NotImplementedConfigProvider:
    # --- Reads ---

    def get_embedding_config(self) -> EmbeddingConfig:
        raise _not_implemented()

    def get_reranker_config(self) -> RerankerConfig:
        raise _not_implemented()

    def get_generation_config(self) -> GenerationConfig:
        raise _not_implemented()

    def get_chunking_config(self) -> ChunkConfig:
        raise _not_implemented()

    def get_rag_prompt_template(self) -> str:
        raise _not_implemented()

    def get_default_collection(self) -> str:
        raise _not_implemented()

    # --- Writes ---

    def set_embedding_config(self, config: EmbeddingConfig) -> None:
        raise _not_implemented()

    def set_reranker_config(self, config: RerankerConfig) -> None:
        raise _not_implemented()

    def set_generation_config(self, config: GenerationConfig) -> None:
        raise _not_implemented()

    def set_chunking_config(self, config: ChunkConfig) -> None:
        raise _not_implemented()

    def set_rag_prompt_template(self, template: str) -> None:
        raise _not_implemented()

    def set_default_collection(self, collection: str) -> None:
        raise _not_implemented()
