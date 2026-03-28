"""RAGPipelineOrchestrator — coordinates the query-to-answer flow.

This is the **reference example** for contract-only dependency direction.
The orchestrator depends exclusively on Protocols from `contracts`;
no concrete implementation is imported here. Swapping any stage requires
only that the composition root inject a different implementation.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

from contracts import (
    AuditLogger,
    ChatMessage,
    ConfigProvider,
    EmbeddingProvider,
    GenerationChunk,
    GenerationProvider,
    GenerationRequest,
    GenerationResponse,
    MetadataFilter,
    ModelParameters,
    QueryStatus,
    RerankedChunk,
    Reranker,
    Role,
    TokenUsage,
    VectorStoreRepository,
)

__all__ = ["RAGPipelineOrchestrator"]

# Sensible prototype defaults; promote to ConfigProvider when the spec adds
# a RetrievalConfig DTO. RETRIEVE_TOP_K > RERANK_TOP_K because the reranker
# is supposed to discard noise the bi-encoder retrieval can't.
DEFAULT_RETRIEVE_TOP_K = 20
DEFAULT_RERANK_TOP_K = 5


class RAGPipelineOrchestrator:
    """Implements the query flow specified in `docs/pipeline.md`."""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStoreRepository,
        reranker: Reranker,
        generation_provider: GenerationProvider,
        config_provider: ConfigProvider,
        audit_logger: AuditLogger,
        retrieve_top_k: int = DEFAULT_RETRIEVE_TOP_K,
        rerank_top_k: int = DEFAULT_RERANK_TOP_K,
    ) -> None:
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._reranker = reranker
        self._generation_provider = generation_provider
        self._config_provider = config_provider
        self._audit_logger = audit_logger
        self._retrieve_top_k = retrieve_top_k
        self._rerank_top_k = rerank_top_k

    def run(
        self,
        messages: list[ChatMessage],
        *,
        api_key_id: str,
        collection: str | None = None,
        filters: list[MetadataFilter] | None = None,
    ) -> GenerationResponse:
        prepared = self._prepare(messages, collection=collection, filters=filters)
        try:
            response = self._generation_provider.generate(prepared.request)
        except Exception as exc:
            self._log(
                prepared.query,
                prepared.reranked,
                response_text="",
                usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
                api_key_id=api_key_id,
                status=QueryStatus.FAILED,
                error_message=f"{type(exc).__name__}: {exc}",
            )
            raise
        self._log(
            prepared.query,
            prepared.reranked,
            response_text=response.text,
            usage=response.usage,
            api_key_id=api_key_id,
            status=QueryStatus.SUCCESS,
        )
        return response

    def run_stream(
        self,
        messages: list[ChatMessage],
        *,
        api_key_id: str,
        collection: str | None = None,
        filters: list[MetadataFilter] | None = None,
    ) -> Iterator[GenerationChunk]:
        prepared = self._prepare(messages, collection=collection, filters=filters)
        accumulated: list[str] = []
        usage = TokenUsage(prompt_tokens=0, completion_tokens=0)
        try:
            for chunk in self._generation_provider.generate_stream(prepared.request):
                accumulated.append(chunk.delta)
                if chunk.usage is not None:
                    usage = chunk.usage
                yield chunk
        except Exception as exc:
            self._log(
                prepared.query,
                prepared.reranked,
                response_text="".join(accumulated),
                usage=usage,
                api_key_id=api_key_id,
                status=QueryStatus.PARTIAL if accumulated else QueryStatus.FAILED,
                error_message=f"{type(exc).__name__}: {exc}",
            )
            raise
        self._log(
            prepared.query,
            prepared.reranked,
            response_text="".join(accumulated),
            usage=usage,
            api_key_id=api_key_id,
            status=QueryStatus.SUCCESS,
        )

    # --- Internals -----------------------------------------------------------

    def _prepare(
        self,
        messages: list[ChatMessage],
        *,
        collection: str | None,
        filters: list[MetadataFilter] | None,
    ) -> _Prepared:
        if not messages:
            raise ValueError("messages must contain at least one ChatMessage")

        query = _last_user_query(messages)
        if not query:
            raise ValueError("conversation has no user message to use as query")

        target_collection = collection or self._config_provider.get_default_collection()

        embedding = self._embedding_provider.embed([query])[0]
        retrieved = self._vector_store.query_similar(
            embedding,
            top_k=self._retrieve_top_k,
            collection=target_collection,
            filters=filters,
        )
        reranked = self._reranker.rerank(query, retrieved, top_k=self._rerank_top_k)

        system_prompt = _render_template(
            self._config_provider.get_rag_prompt_template(),
            reranked=reranked,
            query=query,
        )

        generation_config = self._config_provider.get_generation_config()
        params = generation_config.parameters or {}
        parameters = ModelParameters(
            temperature=_optional_float(params.get("temperature")),
            top_p=_optional_float(params.get("top_p")),
            max_tokens=_optional_int(params.get("max_tokens")),
        )

        request = GenerationRequest(
            system_prompt=system_prompt,
            messages=tuple(messages),
            parameters=parameters,
        )
        return _Prepared(query=query, reranked=reranked, request=request)

    def _log(
        self,
        query: str,
        reranked: list[RerankedChunk],
        *,
        response_text: str,
        usage: TokenUsage,
        api_key_id: str,
        status: QueryStatus,
        error_message: str | None = None,
    ) -> None:
        self._audit_logger.log_query(
            query=query,
            retrieved=reranked,
            response_text=response_text,
            usage=usage,
            timestamp=datetime.now(UTC),
            api_key_id=api_key_id,
            status=status,
            error_message=error_message,
        )


class _Prepared:
    """Bundle of stage-2..5 outputs reused by run() and run_stream()."""

    __slots__ = ("query", "reranked", "request")

    def __init__(
        self,
        *,
        query: str,
        reranked: list[RerankedChunk],
        request: GenerationRequest,
    ) -> None:
        self.query = query
        self.reranked = reranked
        self.request = request


def _last_user_query(messages: list[ChatMessage]) -> str:
    for message in reversed(messages):
        if message.role is Role.USER:
            return message.content
    return ""


def _render_template(template: str, *, reranked: list[RerankedChunk], query: str) -> str:
    context = "\n\n".join(
        f"[chunk:{i}] {item.chunk.text}" for i, item in enumerate(reranked)
    )
    try:
        return template.format(context=context, question=query)
    except KeyError as exc:
        raise ValueError(
            f"rag_prompt_template references unknown placeholder {exc}; "
            "supported placeholders: {context}, {question}."
        ) from exc


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)
