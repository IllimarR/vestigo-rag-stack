"""Tests for `RAGPipelineOrchestrator`.

Uses small in-test fake adapters so the orchestrator's behaviour is
verified without depending on which concrete `EmbeddingProvider`,
`VectorStoreRepository`, `Reranker`, `GenerationProvider`,
`ConfigProvider`, or `AuditLogger` is bound at runtime.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pytest
from contracts import (
    ChatMessage,
    Chunk,
    ChunkConfig,
    DocumentReference,
    EmbeddingConfig,
    GenerationChunk,
    GenerationConfig,
    GenerationRequest,
    GenerationResponse,
    HealthStatus,
    MetadataFilter,
    QueryStatus,
    RerankedChunk,
    RerankerConfig,
    Role,
    ScoredChunk,
    TokenUsage,
)

from services.api_gateway.application.rag_pipeline_orchestrator import (
    RAGPipelineOrchestrator,
)

# --- Test doubles -------------------------------------------------------------


class _Embedder:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[float(len(t)), 1.0, 0.0] for t in texts]

    def get_dimension(self) -> int:
        return 3

    def get_model_id(self) -> str:
        return "fake-embedder"


@dataclass
class _VectorStore:
    chunks: list[Chunk] = field(default_factory=list)
    last_call: dict[str, Any] = field(default_factory=dict)

    def store_chunks(  # pragma: no cover
        self, items: list[tuple[Chunk, list[float]]], collection: str
    ) -> None:
        pass

    def query_similar(
        self,
        query_embedding: list[float],
        top_k: int,
        collection: str,
        filters: list[MetadataFilter] | None = None,
    ) -> list[ScoredChunk]:
        self.last_call = {
            "query_embedding": query_embedding,
            "top_k": top_k,
            "collection": collection,
            "filters": filters,
        }
        return [
            ScoredChunk(chunk=chunk, similarity_score=1.0 / (i + 1))
            for i, chunk in enumerate(self.chunks)
        ]

    def delete_by_document(self, document_id: str, collection: str) -> int:  # pragma: no cover
        return 0

    def delete_by_source(self, source_id: str, collection: str) -> int:  # pragma: no cover
        return 0

    def list_collections(self) -> list[str]:  # pragma: no cover
        return []

    def create_collection(self, name: str, dimension: int) -> None:  # pragma: no cover
        pass

    def delete_collection(self, name: str) -> None:  # pragma: no cover
        pass

    def health_check(self) -> HealthStatus:  # pragma: no cover
        return HealthStatus(healthy=True)


@dataclass
class _Reranker:
    last_call: dict[str, Any] = field(default_factory=dict)

    def rerank(
        self, query: str, scored_chunks: list[ScoredChunk], top_k: int
    ) -> list[RerankedChunk]:
        self.last_call = {"query": query, "top_k": top_k}
        # Reverse retrieval order so tests can assert reranker actually ran.
        reversed_chunks = list(reversed(scored_chunks))
        return [
            RerankedChunk(
                chunk=scored.chunk,
                similarity_score=scored.similarity_score,
                rerank_score=float(top_k - i),
                final_rank=i,
            )
            for i, scored in enumerate(reversed_chunks[:top_k])
        ]

    def get_model_id(self) -> str:
        return "fake-reranker"


@dataclass
class _Generation:
    response_text: str = "the answer"
    stream_deltas: tuple[str, ...] = ("the ", "answer")
    stream_usage: TokenUsage = field(
        default_factory=lambda: TokenUsage(prompt_tokens=7, completion_tokens=3)
    )
    raise_on_generate: BaseException | None = None
    raise_on_stream_at: int | None = None
    captured_request: GenerationRequest | None = None

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        self.captured_request = request
        if self.raise_on_generate is not None:
            raise self.raise_on_generate
        return GenerationResponse(
            text=self.response_text,
            usage=TokenUsage(prompt_tokens=10, completion_tokens=5),
            model_id="fake-gen",
        )

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        self.captured_request = request
        for i, delta in enumerate(self.stream_deltas):
            if self.raise_on_stream_at is not None and i == self.raise_on_stream_at:
                raise RuntimeError("upstream blew up mid-stream")
            yield GenerationChunk(delta=delta)
        yield GenerationChunk(delta="", usage=self.stream_usage)

    def get_model_id(self) -> str:
        return "fake-gen"


@dataclass
class _Audit:
    queries: list[dict[str, Any]] = field(default_factory=list)

    def log_query(
        self,
        *,
        query: str,
        retrieved: list[RerankedChunk],
        response_text: str,
        usage: TokenUsage,
        timestamp: datetime,
        api_key_id: str,
        status: QueryStatus,
        error_message: str | None = None,
    ) -> None:
        self.queries.append(
            {
                "query": query,
                "retrieved": retrieved,
                "response_text": response_text,
                "usage": usage,
                "api_key_id": api_key_id,
                "status": status,
                "error_message": error_message,
            }
        )

    def log_ingest_event(self, **_: Any) -> None:  # pragma: no cover
        pass

    def log_admin_event(self, **_: Any) -> None:  # pragma: no cover
        pass

    def query_logs(self, **_: Any) -> list[dict[str, Any]]:  # pragma: no cover
        return []


@dataclass
class _Config:
    template: str = "system\n{context}\nQ: {question}"
    default_collection: str = "kb"
    generation_params: dict[str, Any] = field(
        default_factory=lambda: {"temperature": 0.5, "max_tokens": 128}
    )

    def get_embedding_config(self) -> EmbeddingConfig:  # pragma: no cover
        return EmbeddingConfig(endpoint="x", api_type="x", model_name="x")

    def get_reranker_config(self) -> RerankerConfig:  # pragma: no cover
        return RerankerConfig(type="x", endpoint=None, model_name="x")

    def get_generation_config(self) -> GenerationConfig:
        return GenerationConfig(
            endpoint="x",
            api_type="x",
            model_name="x",
            parameters=self.generation_params,
        )

    def get_chunking_config(self) -> ChunkConfig:  # pragma: no cover
        return ChunkConfig(method="x", size=1, overlap=0)

    def get_rag_prompt_template(self) -> str:
        return self.template

    def get_default_collection(self) -> str:
        return self.default_collection

    def set_embedding_config(self, c: EmbeddingConfig) -> None:  # pragma: no cover
        pass

    def set_reranker_config(self, c: RerankerConfig) -> None:  # pragma: no cover
        pass

    def set_generation_config(self, c: GenerationConfig) -> None:  # pragma: no cover
        pass

    def set_chunking_config(self, c: ChunkConfig) -> None:  # pragma: no cover
        pass

    def set_rag_prompt_template(self, t: str) -> None:  # pragma: no cover
        pass

    def set_default_collection(self, name: str) -> None:  # pragma: no cover
        pass


def _ref() -> DocumentReference:
    return DocumentReference(
        source_id="s",
        document_id="d",
        filename="d.md",
        last_modified=datetime(2026, 3, 28),
    )


def _chunk(text: str, index: int = 0) -> Chunk:
    return Chunk(text=text, index=index, start=0, end=len(text), parent=_ref())


@pytest.fixture
def harness() -> dict[str, Any]:
    embedder = _Embedder()
    store = _VectorStore(chunks=[_chunk("alpha", 0), _chunk("beta", 1), _chunk("gamma", 2)])
    reranker = _Reranker()
    generation = _Generation()
    audit = _Audit()
    config = _Config()
    orchestrator = RAGPipelineOrchestrator(
        embedding_provider=embedder,
        vector_store=store,
        reranker=reranker,
        generation_provider=generation,
        config_provider=config,
        audit_logger=audit,
        retrieve_top_k=20,
        rerank_top_k=2,
    )
    return {
        "embedder": embedder,
        "store": store,
        "reranker": reranker,
        "generation": generation,
        "audit": audit,
        "config": config,
        "orchestrator": orchestrator,
    }


def _conversation(user: str = "what is alpha?") -> list[ChatMessage]:
    return [ChatMessage(role=Role.USER, content=user)]


# --- run() ------------------------------------------------------------------


def test_run_returns_generation_response(harness: dict[str, Any]) -> None:
    response = harness["orchestrator"].run(_conversation(), api_key_id="k1")
    assert response.text == "the answer"
    assert response.usage.prompt_tokens == 10


def test_run_uses_last_user_message_as_query(harness: dict[str, Any]) -> None:
    convo = [
        ChatMessage(role=Role.USER, content="ignored older question"),
        ChatMessage(role=Role.ASSISTANT, content="ack"),
        ChatMessage(role=Role.USER, content="real query"),
    ]
    harness["orchestrator"].run(convo, api_key_id="k1")
    assert harness["embedder"].calls == [["real query"]]
    assert harness["reranker"].last_call["query"] == "real query"


def test_run_uses_default_collection_when_not_overridden(harness: dict[str, Any]) -> None:
    harness["orchestrator"].run(_conversation(), api_key_id="k1")
    assert harness["store"].last_call["collection"] == "kb"


def test_run_honours_collection_override(harness: dict[str, Any]) -> None:
    harness["orchestrator"].run(_conversation(), api_key_id="k1", collection="alt")
    assert harness["store"].last_call["collection"] == "alt"


def test_run_forwards_filters(harness: dict[str, Any]) -> None:
    filters = [MetadataFilter(field="tag", op="eq", value="x")]
    harness["orchestrator"].run(_conversation(), api_key_id="k1", filters=filters)
    assert harness["store"].last_call["filters"] == filters


def test_run_truncates_to_rerank_top_k(harness: dict[str, Any]) -> None:
    harness["orchestrator"].run(_conversation(), api_key_id="k1")
    assert harness["reranker"].last_call["top_k"] == 2
    # Audit log carries exactly the reranked chunks (top_k = 2).
    audit = harness["audit"].queries[0]
    assert len(audit["retrieved"]) == 2


def test_run_renders_template_with_context_and_question(harness: dict[str, Any]) -> None:
    harness["orchestrator"].run(_conversation("Why?"), api_key_id="k1")
    request = harness["generation"].captured_request
    assert request is not None
    system = request.system_prompt or ""
    assert "Q: Why?" in system
    # Reranker emits chunks in reversed order so the first context entry is "gamma".
    assert "[chunk:0] gamma" in system


def test_run_forwards_generation_params(harness: dict[str, Any]) -> None:
    harness["orchestrator"].run(_conversation(), api_key_id="k1")
    request = harness["generation"].captured_request
    assert request is not None
    assert request.parameters.temperature == 0.5
    assert request.parameters.max_tokens == 128


def test_run_audits_success(harness: dict[str, Any]) -> None:
    harness["orchestrator"].run(_conversation(), api_key_id="k1")
    audit = harness["audit"].queries[0]
    assert audit["status"] is QueryStatus.SUCCESS
    assert audit["api_key_id"] == "k1"
    assert audit["response_text"] == "the answer"


def test_run_audits_failure_and_reraises(harness: dict[str, Any]) -> None:
    harness["generation"].raise_on_generate = RuntimeError("upstream down")
    with pytest.raises(RuntimeError, match="upstream down"):
        harness["orchestrator"].run(_conversation(), api_key_id="k1")
    audit = harness["audit"].queries[0]
    assert audit["status"] is QueryStatus.FAILED
    assert audit["error_message"] is not None
    assert "upstream down" in audit["error_message"]


def test_run_rejects_empty_messages(harness: dict[str, Any]) -> None:
    with pytest.raises(ValueError, match="at least one"):
        harness["orchestrator"].run([], api_key_id="k1")


def test_run_rejects_conversation_with_no_user_message(harness: dict[str, Any]) -> None:
    convo = [ChatMessage(role=Role.ASSISTANT, content="hi")]
    with pytest.raises(ValueError, match="no user message"):
        harness["orchestrator"].run(convo, api_key_id="k1")


# --- run_stream() -----------------------------------------------------------


def test_run_stream_yields_all_deltas_then_audits(harness: dict[str, Any]) -> None:
    chunks = list(harness["orchestrator"].run_stream(_conversation(), api_key_id="k1"))
    text = "".join(chunk.delta for chunk in chunks)
    assert text == "the answer"

    audit = harness["audit"].queries[0]
    assert audit["status"] is QueryStatus.SUCCESS
    assert audit["response_text"] == "the answer"
    assert audit["usage"].completion_tokens == 3


def test_run_stream_audits_partial_when_upstream_fails_mid_stream(
    harness: dict[str, Any],
) -> None:
    harness["generation"].raise_on_stream_at = 1  # blow up after first delta
    with pytest.raises(RuntimeError):
        list(harness["orchestrator"].run_stream(_conversation(), api_key_id="k1"))

    audit = harness["audit"].queries[0]
    assert audit["status"] is QueryStatus.PARTIAL
    assert audit["response_text"] == "the "  # only the first delta was emitted


def test_run_stream_audits_failed_when_upstream_fails_before_any_chunk(
    harness: dict[str, Any],
) -> None:
    harness["generation"].raise_on_stream_at = 0
    with pytest.raises(RuntimeError):
        list(harness["orchestrator"].run_stream(_conversation(), api_key_id="k1"))

    audit = harness["audit"].queries[0]
    assert audit["status"] is QueryStatus.FAILED
    assert audit["response_text"] == ""
