"""Contract-compliance suite for every `VectorStoreRepository` implementation.

Each test runs once per registered backend. When a new backend is added
(pgvector, Milvus, ...), add its factory to `_BACKENDS` and the whole
suite runs against it for free. This is the concrete artifact behind the
Modularity Proof Criteria in `docs/architecture.md` §2: a single test
body, one contract, N interchangeable implementations.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import pytest
from contracts import (
    Chunk,
    DocumentReference,
    MetadataFilter,
    VectorStoreRepository,
)

from services.vector_store.application.chromadb_vector_store import (
    ChromaDbVectorStoreRepository,
)
from services.vector_store.application.in_memory_vector_store import (
    InMemoryVectorStoreRepository,
)

BackendFactory = Callable[[Path], VectorStoreRepository]


def _in_memory(_tmp: Path) -> VectorStoreRepository:
    return InMemoryVectorStoreRepository()


def _chromadb(tmp: Path) -> VectorStoreRepository:
    del tmp
    host = os.getenv("CHROMADB_TEST_HOST")
    if not host:
        pytest.skip("set CHROMADB_TEST_HOST to run ChromaDB HTTP contract tests")
    port = int(os.getenv("CHROMADB_TEST_PORT", "8000"))
    ssl = os.getenv("CHROMADB_TEST_SSL", "").strip().lower() in {"1", "true", "yes", "on"}
    return ChromaDbVectorStoreRepository(host=host, port=port, ssl=ssl)


_BACKENDS: dict[str, BackendFactory] = {
    "in_memory": _in_memory,
    "chromadb": _chromadb,
}


@pytest.fixture(params=sorted(_BACKENDS), ids=sorted(_BACKENDS))
def store(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[VectorStoreRepository]:
    factory = _BACKENDS[request.param]
    yield factory(tmp_path)


def _chunk(doc_id: str, index: int = 0, source_id: str = "src", **metadata: object) -> Chunk:
    return Chunk(
        text=f"chunk {index} of {doc_id}",
        index=index,
        start=index * 10,
        end=index * 10 + 10,
        parent=DocumentReference(
            source_id=source_id,
            document_id=doc_id,
            filename=f"{doc_id}.md",
            last_modified=datetime(2026, 3, 24, 10, 0, 0),
        ),
        metadata=dict(metadata),
    )


# --- Collection lifecycle ---------------------------------------------------


def test_create_list_delete_collection(store: VectorStoreRepository) -> None:
    assert "kb_main" not in store.list_collections()
    store.create_collection("kb_main", dimension=3)
    assert "kb_main" in store.list_collections()

    # Idempotent when dimensions match.
    store.create_collection("kb_main", dimension=3)

    store.delete_collection("kb_main")
    assert "kb_main" not in store.list_collections()


def test_create_collection_dimension_mismatch(store: VectorStoreRepository) -> None:
    store.create_collection("kb_main", dimension=3)
    with pytest.raises(ValueError, match="dimension"):
        store.create_collection("kb_main", dimension=5)


def test_delete_collection_is_idempotent(store: VectorStoreRepository) -> None:
    store.delete_collection("never_existed")  # must not raise


# --- Writes + similarity ---------------------------------------------------


def test_store_and_query_top_k(store: VectorStoreRepository) -> None:
    store.create_collection("kb_main", dimension=3)
    store.store_chunks(
        [
            (_chunk("A"), [1.0, 0.0, 0.0]),
            (_chunk("B"), [0.9, 0.1, 0.0]),
            (_chunk("C"), [0.0, 1.0, 0.0]),
        ],
        collection="kb_main",
    )

    results = store.query_similar([1.0, 0.0, 0.0], top_k=2, collection="kb_main")
    assert [r.chunk.parent.document_id for r in results] == ["A", "B"]
    assert results[0].similarity_score == pytest.approx(1.0, abs=1e-4)
    assert results[0].similarity_score >= results[1].similarity_score


def test_query_returns_empty_for_unknown_collection(store: VectorStoreRepository) -> None:
    assert store.query_similar([1.0, 0.0, 0.0], top_k=5, collection="no_such") == []


def test_store_rejects_dimension_mismatch(store: VectorStoreRepository) -> None:
    store.create_collection("kb_main", dimension=3)
    with pytest.raises(ValueError, match="dimension"):
        store.store_chunks([(_chunk("A"), [1.0, 0.0])], collection="kb_main")


def test_store_roundtrip_preserves_chunk_identity(store: VectorStoreRepository) -> None:
    """Chunks come back with parent, index, and metadata intact."""
    store.create_collection("kb_main", dimension=2)
    original = _chunk("A", index=7, source_id="fs", tag="alpha", score=0.5)
    store.store_chunks([(original, [1.0, 0.0])], collection="kb_main")
    results = store.query_similar([1.0, 0.0], top_k=1, collection="kb_main")
    assert len(results) == 1
    r = results[0]
    assert r.chunk.parent.document_id == "A"
    assert r.chunk.parent.source_id == "fs"
    assert r.chunk.index == 7
    assert r.chunk.text == original.text
    assert r.chunk.metadata["tag"] == "alpha"
    assert r.chunk.metadata["score"] == 0.5


# --- Metadata filters -------------------------------------------------------


def test_filter_eq(store: VectorStoreRepository) -> None:
    store.create_collection("kb_main", dimension=3)
    store.store_chunks(
        [
            (_chunk("A", tag="x"), [1.0, 0.0, 0.0]),
            (_chunk("B", tag="y"), [0.9, 0.1, 0.0]),
        ],
        collection="kb_main",
    )
    results = store.query_similar(
        [1.0, 0.0, 0.0],
        top_k=5,
        collection="kb_main",
        filters=[MetadataFilter(field="tag", op="eq", value="y")],
    )
    assert [r.chunk.parent.document_id for r in results] == ["B"]


def test_filter_ne(store: VectorStoreRepository) -> None:
    store.create_collection("kb_main", dimension=3)
    store.store_chunks(
        [
            (_chunk("A", tag="x"), [1.0, 0.0, 0.0]),
            (_chunk("B", tag="y"), [0.9, 0.1, 0.0]),
        ],
        collection="kb_main",
    )
    results = store.query_similar(
        [1.0, 0.0, 0.0],
        top_k=5,
        collection="kb_main",
        filters=[MetadataFilter(field="tag", op="ne", value="x")],
    )
    assert [r.chunk.parent.document_id for r in results] == ["B"]


def test_filter_in(store: VectorStoreRepository) -> None:
    store.create_collection("kb_main", dimension=3)
    store.store_chunks(
        [
            (_chunk("A", tag="x"), [1.0, 0.0, 0.0]),
            (_chunk("B", tag="y"), [0.9, 0.1, 0.0]),
            (_chunk("C", tag="z"), [0.0, 1.0, 0.0]),
        ],
        collection="kb_main",
    )
    results = store.query_similar(
        [1.0, 0.0, 0.0],
        top_k=5,
        collection="kb_main",
        filters=[MetadataFilter(field="tag", op="in", value=["x", "z"])],
    )
    assert sorted(r.chunk.parent.document_id for r in results) == ["A", "C"]


def test_filter_gte_lte(store: VectorStoreRepository) -> None:
    store.create_collection("kb_main", dimension=3)
    store.store_chunks(
        [
            (_chunk("A", score=1), [1.0, 0.0, 0.0]),
            (_chunk("B", score=5), [0.9, 0.1, 0.0]),
            (_chunk("C", score=10), [0.0, 1.0, 0.0]),
        ],
        collection="kb_main",
    )
    gte = store.query_similar(
        [1.0, 0.0, 0.0],
        top_k=5,
        collection="kb_main",
        filters=[MetadataFilter(field="score", op="gte", value=5)],
    )
    assert sorted(r.chunk.parent.document_id for r in gte) == ["B", "C"]

    lte = store.query_similar(
        [1.0, 0.0, 0.0],
        top_k=5,
        collection="kb_main",
        filters=[MetadataFilter(field="score", op="lte", value=5)],
    )
    assert sorted(r.chunk.parent.document_id for r in lte) == ["A", "B"]


def test_filter_range(store: VectorStoreRepository) -> None:
    store.create_collection("kb_main", dimension=3)
    store.store_chunks(
        [
            (_chunk("A", score=1), [1.0, 0.0, 0.0]),
            (_chunk("B", score=5), [0.9, 0.1, 0.0]),
            (_chunk("C", score=10), [0.0, 1.0, 0.0]),
        ],
        collection="kb_main",
    )
    results = store.query_similar(
        [1.0, 0.0, 0.0],
        top_k=5,
        collection="kb_main",
        filters=[MetadataFilter(field="score", op="range", value=(2, 9))],
    )
    assert [r.chunk.parent.document_id for r in results] == ["B"]


def test_filter_contains(store: VectorStoreRepository) -> None:
    store.create_collection("kb_main", dimension=3)
    store.store_chunks(
        [
            (_chunk("A", title="quick brown fox"), [1.0, 0.0, 0.0]),
            (_chunk("B", title="lazy dog"), [0.9, 0.1, 0.0]),
        ],
        collection="kb_main",
    )
    results = store.query_similar(
        [1.0, 0.0, 0.0],
        top_k=5,
        collection="kb_main",
        filters=[MetadataFilter(field="title", op="contains", value="brown")],
    )
    assert [r.chunk.parent.document_id for r in results] == ["A"]


# --- Deletes ----------------------------------------------------------------


def test_delete_by_document(store: VectorStoreRepository) -> None:
    store.create_collection("kb_main", dimension=2)
    store.store_chunks(
        [
            (_chunk("A", index=0), [1.0, 0.0]),
            (_chunk("A", index=1), [0.9, 0.1]),
            (_chunk("B", index=0), [0.0, 1.0]),
        ],
        collection="kb_main",
    )
    removed = store.delete_by_document("A", "kb_main")
    assert removed == 2
    remaining = store.query_similar([1.0, 0.0], top_k=5, collection="kb_main")
    assert [r.chunk.parent.document_id for r in remaining] == ["B"]


def test_delete_by_source(store: VectorStoreRepository) -> None:
    store.create_collection("kb_main", dimension=2)
    store.store_chunks(
        [
            (_chunk("A", source_id="fs"), [1.0, 0.0]),
            (_chunk("B", source_id="api"), [0.0, 1.0]),
        ],
        collection="kb_main",
    )
    assert store.delete_by_source("fs", "kb_main") == 1
    remaining = store.query_similar([0.0, 1.0], top_k=5, collection="kb_main")
    assert [r.chunk.parent.source_id for r in remaining] == ["api"]


def test_delete_by_document_on_missing_collection_is_zero(
    store: VectorStoreRepository,
) -> None:
    assert store.delete_by_document("A", "no_such") == 0
    assert store.delete_by_source("fs", "no_such") == 0


# --- Health ----------------------------------------------------------------


def test_health_check(store: VectorStoreRepository) -> None:
    status = store.health_check()
    assert status.healthy is True
    assert status.detail is not None
