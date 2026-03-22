"""RAGPipelineOrchestrator — coordinates the query-to-answer flow.

This is the **reference example** for contract-only dependency direction.
The orchestrator depends exclusively on Protocols from `contracts`;
no concrete implementation is imported here. Swapping any stage requires
only that the composition root inject a different implementation.
"""

from __future__ import annotations

from collections.abc import Iterator

from contracts import (
    AuditLogger,
    ChatMessage,
    ConfigProvider,
    EmbeddingProvider,
    GenerationChunk,
    GenerationProvider,
    GenerationResponse,
    Reranker,
    VectorStoreRepository,
)

__all__ = ["RAGPipelineOrchestrator"]


class RAGPipelineOrchestrator:
    """Phase 1 stub. Real implementation arrives in Phase 3.

    Flow (per `docs/pipeline.md`):
      1. Extract query — last user message from `messages`.
      2. Embed query via `embedding_provider`.
      3. Retrieve similar chunks via `vector_store.query_similar`.
      4. Rerank via `reranker`.
      5. Assemble prompt using template from `config_provider.get_rag_prompt_template()`.
      6. Generate via `generation_provider` (or `generate_stream`).
      7. Audit via `audit_logger.log_query`.
      8. Return.
    """

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStoreRepository,
        reranker: Reranker,
        generation_provider: GenerationProvider,
        config_provider: ConfigProvider,
        audit_logger: AuditLogger,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._reranker = reranker
        self._generation_provider = generation_provider
        self._config_provider = config_provider
        self._audit_logger = audit_logger

    def run(
        self,
        messages: list[ChatMessage],
        *,
        api_key_id: str,
        collection: str | None = None,
    ) -> GenerationResponse:
        raise NotImplementedError(
            "RAGPipelineOrchestrator.run is a Phase 1 stub. Implementing this "
            "requires concrete bindings for EmbeddingProvider, "
            "VectorStoreRepository, Reranker, GenerationProvider, "
            "ConfigProvider, and AuditLogger — see docs/pipeline.md §"
            "RAG Pipeline Orchestration for the target flow."
        )

    def run_stream(
        self,
        messages: list[ChatMessage],
        *,
        api_key_id: str,
        collection: str | None = None,
    ) -> Iterator[GenerationChunk]:
        raise NotImplementedError(
            "RAGPipelineOrchestrator.run_stream is a Phase 1 stub. "
            "SSE streaming arrives in Phase 3."
        )
