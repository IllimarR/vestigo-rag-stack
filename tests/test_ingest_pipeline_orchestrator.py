"""Tests for `IngestPipelineOrchestrator`.

Uses small in-test fake adapters so the orchestrator's behaviour is
verified without depending on which concrete `SourceConnector`,
`DocumentConverter`, `Chunker`, `EmbeddingProvider`,
`VectorStoreRepository`, or `AuditLogger` is bound at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest
from contracts import (
    ChangeEvent,
    ChangeType,
    Chunk,
    ChunkConfig,
    ConvertedDocument,
    DocumentReference,
    EmbeddingConfig,
    GenerationConfig,
    HealthStatus,
    IngestEventType,
    MetadataFilter,
    RawDocument,
    RerankerConfig,
    ScoredChunk,
)

from services.ingest.application.ingest_pipeline_orchestrator import (
    IngestPipelineOrchestrator,
    IngestResult,
)
from services.ingest.application.markitdown_document_converter import (
    UnsupportedFileTypeError,
)

# --- Test doubles -------------------------------------------------------------


class _Source:
    def __init__(self, contents: dict[str, RawDocument]) -> None:
        self._contents = contents
        self.fetched: list[str] = []

    def fetch_document(self, ref: DocumentReference) -> RawDocument:
        self.fetched.append(ref.document_id)
        return self._contents[ref.document_id]

    def list_documents(self) -> list[DocumentReference]:  # pragma: no cover
        return [r.reference for r in self._contents.values()]

    def detect_changes(self, since: datetime) -> list[ChangeEvent]:  # pragma: no cover
        return []

    def get_source_id(self) -> str:  # pragma: no cover
        return "test"


@dataclass
class _Converter:
    supported: tuple[str, ...] = ("md", "txt")
    raise_on: set[str] = field(default_factory=set)
    return_empty: bool = False

    def convert(self, raw: RawDocument) -> ConvertedDocument:
        if raw.file_type in self.raise_on:
            raise UnsupportedFileTypeError(f"forced reject: {raw.file_type}")
        body = "" if self.return_empty else raw.content.decode()
        return ConvertedDocument(
            reference=raw.reference, markdown=body, converter_id="test"
        )

    def supported_types(self) -> list[str]:
        return list(self.supported)


class _Chunker:
    def __init__(self, chunks_per_doc: int = 2) -> None:
        self._n = chunks_per_doc

    def chunk(
        self, markdown: str, parent: DocumentReference, config: ChunkConfig
    ) -> list[Chunk]:
        if not markdown:
            return []
        size = max(1, len(markdown) // self._n)
        return [
            Chunk(
                text=markdown[i * size : (i + 1) * size] or markdown,
                index=i,
                start=i * size,
                end=(i + 1) * size,
                parent=parent,
            )
            for i in range(self._n)
        ]


class _Embedder:
    def __init__(self, dim: int = 3) -> None:
        self._dim = dim
        self.calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(texts)
        return [[float(len(t)) for _ in range(self._dim)] for t in texts]

    def get_dimension(self) -> int:
        return self._dim

    def get_model_id(self) -> str:
        return "test-embedder"


@dataclass
class _VectorStore:
    stored: list[tuple[list[tuple[Chunk, list[float]]], str]] = field(
        default_factory=list
    )
    deleted: list[tuple[str, str]] = field(default_factory=list)

    def store_chunks(
        self, items: list[tuple[Chunk, list[float]]], collection: str
    ) -> None:
        self.stored.append((items, collection))

    def query_similar(  # pragma: no cover
        self,
        query_embedding: list[float],
        top_k: int,
        collection: str,
        filters: list[MetadataFilter] | None = None,
    ) -> list[ScoredChunk]:
        return []

    def delete_by_document(self, document_id: str, collection: str) -> int:
        self.deleted.append((document_id, collection))
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
class _AuditEvent:
    reference: DocumentReference
    event_type: IngestEventType
    chunk_count: int
    error_message: str | None


@dataclass
class _Audit:
    events: list[_AuditEvent] = field(default_factory=list)

    def log_ingest_event(
        self,
        *,
        reference: DocumentReference,
        event_type: IngestEventType,
        chunk_count: int,
        timestamp: datetime,
        error_message: str | None = None,
    ) -> None:
        self.events.append(
            _AuditEvent(reference, event_type, chunk_count, error_message)
        )

    def log_query(self, **_: Any) -> None:  # pragma: no cover
        pass

    def log_admin_event(self, **_: Any) -> None:  # pragma: no cover
        pass

    def query_logs(self, **_: Any) -> list[dict[str, Any]]:  # pragma: no cover
        return []


@dataclass
class _Config:
    chunk_method: str = "recursive"

    def get_chunking_config(self) -> ChunkConfig:
        return ChunkConfig(method=self.chunk_method, size=512, overlap=64)

    def get_embedding_config(self) -> EmbeddingConfig:  # pragma: no cover
        return EmbeddingConfig(endpoint="x", api_type="x", model_name="x")

    def get_reranker_config(self) -> RerankerConfig:  # pragma: no cover
        return RerankerConfig(type="x", endpoint=None, model_name="x")

    def get_generation_config(self) -> GenerationConfig:  # pragma: no cover
        return GenerationConfig(endpoint="x", api_type="x", model_name="x")

    def get_rag_prompt_template(self) -> str:  # pragma: no cover
        return ""

    def set_chunking_config(self, c: ChunkConfig) -> None:  # pragma: no cover
        pass

    def set_embedding_config(self, c: EmbeddingConfig) -> None:  # pragma: no cover
        pass

    def set_reranker_config(self, c: RerankerConfig) -> None:  # pragma: no cover
        pass

    def set_generation_config(self, c: GenerationConfig) -> None:  # pragma: no cover
        pass

    def set_rag_prompt_template(self, template: str) -> None:  # pragma: no cover
        pass

    def get_default_collection(self) -> str:  # pragma: no cover
        return "kb"

    def set_default_collection(self, name: str) -> None:  # pragma: no cover
        pass


def _ref(doc_id: str, file_type: str = "md") -> DocumentReference:
    return DocumentReference(
        source_id="test",
        document_id=doc_id,
        filename=f"{doc_id}.{file_type}",
        last_modified=datetime(2026, 3, 26, tzinfo=UTC),
    )


def _raw(doc_id: str, body: bytes = b"hello world", file_type: str = "md") -> RawDocument:
    return RawDocument(reference=_ref(doc_id, file_type), content=body, file_type=file_type)


def _added(doc_id: str, file_type: str = "md") -> ChangeEvent:
    return ChangeEvent(reference=_ref(doc_id, file_type), change_type=ChangeType.ADDED)


def _modified(doc_id: str, file_type: str = "md") -> ChangeEvent:
    return ChangeEvent(reference=_ref(doc_id, file_type), change_type=ChangeType.MODIFIED)


def _deleted(doc_id: str, file_type: str = "md") -> ChangeEvent:
    return ChangeEvent(reference=_ref(doc_id, file_type), change_type=ChangeType.DELETED)


@pytest.fixture
def harness() -> dict[str, Any]:
    source = _Source({"a": _raw("a"), "b": _raw("b")})
    converter = _Converter()
    chunker = _Chunker(chunks_per_doc=2)
    embedder = _Embedder(dim=3)
    store = _VectorStore()
    config = _Config()
    audit = _Audit()
    orchestrator = IngestPipelineOrchestrator(
        source_connector=source,
        document_converter=converter,
        chunker=chunker,
        embedding_provider=embedder,
        vector_store=store,
        config_provider=config,
        audit_logger=audit,
    )
    return {
        "source": source,
        "converter": converter,
        "chunker": chunker,
        "embedder": embedder,
        "store": store,
        "config": config,
        "audit": audit,
        "orchestrator": orchestrator,
    }


# --- Tests --------------------------------------------------------------------


def test_added_flows_through_pipeline_end_to_end(harness: dict[str, Any]) -> None:
    result = harness["orchestrator"].process_changes([_added("a")], collection="kb")

    assert result == IngestResult(ingested=1)
    assert harness["source"].fetched == ["a"]
    assert len(harness["embedder"].calls) == 1
    assert harness["store"].deleted == []  # never delete on ADDED
    assert len(harness["store"].stored) == 1
    items, collection = harness["store"].stored[0]
    assert collection == "kb"
    assert len(items) == 2  # _Chunker yields 2 per doc
    assert harness["audit"].events[0].event_type == IngestEventType.INGESTED
    assert harness["audit"].events[0].chunk_count == 2


def test_modified_deletes_before_store(harness: dict[str, Any]) -> None:
    result = harness["orchestrator"].process_changes([_modified("a")], collection="kb")

    assert result == IngestResult(updated=1)
    assert harness["store"].deleted == [("a", "kb")]
    assert len(harness["store"].stored) == 1
    assert harness["audit"].events[0].event_type == IngestEventType.UPDATED


def test_deleted_skips_pipeline_and_calls_delete(harness: dict[str, Any]) -> None:
    result = harness["orchestrator"].process_changes([_deleted("a")], collection="kb")

    assert result == IngestResult(deleted=1)
    assert harness["source"].fetched == []
    assert harness["store"].deleted == [("a", "kb")]
    assert harness["store"].stored == []
    assert harness["embedder"].calls == []
    assert harness["audit"].events[0].event_type == IngestEventType.DELETED


def test_unsupported_file_type_is_skipped_with_audit(harness: dict[str, Any]) -> None:
    harness["source"]._contents["weird"] = _raw("weird", file_type="exe")  # noqa: SLF001

    result = harness["orchestrator"].process_changes([_added("weird", "exe")], collection="kb")

    assert result == IngestResult(skipped=1)
    assert harness["store"].stored == []
    audit = harness["audit"].events[0]
    assert audit.event_type == IngestEventType.SKIPPED
    assert audit.error_message is not None
    assert "exe" in audit.error_message


def test_converter_failure_is_caught_and_logged(harness: dict[str, Any]) -> None:
    harness["converter"].raise_on = {"md"}

    result = harness["orchestrator"].process_changes([_added("a")], collection="kb")

    assert result == IngestResult(failed=1)
    assert harness["store"].stored == []
    assert harness["audit"].events[0].event_type == IngestEventType.SKIPPED
    assert harness["audit"].events[0].error_message is not None


def test_empty_markdown_is_skipped(harness: dict[str, Any]) -> None:
    harness["converter"].return_empty = True

    result = harness["orchestrator"].process_changes([_added("a")], collection="kb")

    assert result == IngestResult(skipped=1)
    assert harness["store"].stored == []
    assert "empty" in (harness["audit"].events[0].error_message or "")


def test_batch_continues_after_failure(harness: dict[str, Any]) -> None:
    harness["converter"].raise_on = {"exe"}
    harness["source"]._contents["bad"] = _raw("bad", file_type="exe")  # noqa: SLF001

    result = harness["orchestrator"].process_changes(
        [_added("a"), _added("bad", "exe"), _added("b")], collection="kb"
    )

    # 'a' succeeds, 'bad' is skipped (unsupported), 'b' succeeds.
    assert result.ingested == 2
    assert result.skipped == 1
    assert len(harness["store"].stored) == 2


def test_mixed_event_types_accumulate_counts(harness: dict[str, Any]) -> None:
    result = harness["orchestrator"].process_changes(
        [_added("a"), _modified("b"), _deleted("a")],
        collection="kb",
    )

    assert result == IngestResult(ingested=1, updated=1, deleted=1)
