"""Contract-compliance suite for every `Chunker` implementation.

Register a new chunker factory in `_CHUNKERS` and the whole suite runs
against it.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import pytest
from contracts import Chunk, ChunkConfig, Chunker, DocumentReference

from services.ingest.application.recursive_chunker import RecursiveChunker

ChunkerFactory = Callable[[], Chunker]

_CHUNKERS: dict[str, ChunkerFactory] = {
    "recursive": RecursiveChunker,
}


@pytest.fixture(params=sorted(_CHUNKERS), ids=sorted(_CHUNKERS))
def chunker(request: pytest.FixtureRequest) -> Chunker:
    return _CHUNKERS[request.param]()


def _method_for(name: str) -> str:
    """Map the fixture backend name to the `ChunkConfig.method` string it accepts."""
    return name


def _parent() -> DocumentReference:
    return DocumentReference(
        source_id="src",
        document_id="doc-1",
        filename="doc-1.md",
        last_modified=datetime(2026, 3, 24, 10, 0, 0),
    )


def _config(method: str, size: int, overlap: int) -> ChunkConfig:
    return ChunkConfig(method=method, size=size, overlap=overlap)


# --- Empty / trivial inputs ------------------------------------------------


def test_empty_input_returns_no_chunks(
    chunker: Chunker, request: pytest.FixtureRequest
) -> None:
    method = _method_for(request.node.callspec.params["chunker"])
    result = chunker.chunk("", _parent(), _config(method, size=100, overlap=10))
    assert result == []


def test_input_smaller_than_size_returns_one_chunk(
    chunker: Chunker, request: pytest.FixtureRequest
) -> None:
    method = _method_for(request.node.callspec.params["chunker"])
    text = "short text"
    result = chunker.chunk(text, _parent(), _config(method, size=100, overlap=10))
    assert len(result) == 1
    assert result[0].text == text
    assert result[0].start == 0
    assert result[0].end == len(text)


# --- Multi-chunk behavior --------------------------------------------------


def test_large_input_splits_into_multiple_chunks(
    chunker: Chunker, request: pytest.FixtureRequest
) -> None:
    method = _method_for(request.node.callspec.params["chunker"])
    # 200 chars of alternating paragraphs — easy to split.
    text = "\n\n".join(f"Paragraph {i} " * 3 for i in range(10))
    result = chunker.chunk(text, _parent(), _config(method, size=80, overlap=10))
    assert len(result) > 1
    for chunk in result:
        assert len(chunk.text) <= 80


def test_chunks_are_monotonically_ordered(
    chunker: Chunker, request: pytest.FixtureRequest
) -> None:
    method = _method_for(request.node.callspec.params["chunker"])
    text = " ".join(f"word{i}" for i in range(200))
    result = chunker.chunk(text, _parent(), _config(method, size=100, overlap=20))
    for i in range(1, len(result)):
        assert result[i].index == result[i - 1].index + 1
        assert result[i].start >= result[i - 1].start


def test_chunk_positions_reference_original_text(
    chunker: Chunker, request: pytest.FixtureRequest
) -> None:
    """Chunk.text must match the slice of the original at (start, end)."""
    method = _method_for(request.node.callspec.params["chunker"])
    text = "ABCDEFGHIJ" * 30  # 300 chars
    result = chunker.chunk(text, _parent(), _config(method, size=50, overlap=10))
    for chunk in result:
        assert chunk.text == text[chunk.start : chunk.end]


def test_full_coverage_no_gaps(
    chunker: Chunker, request: pytest.FixtureRequest
) -> None:
    """Every character of the source appears in at least one chunk."""
    method = _method_for(request.node.callspec.params["chunker"])
    text = "abcdefghijklmnopqrstuvwxyz" * 10  # 260 chars
    result = chunker.chunk(text, _parent(), _config(method, size=50, overlap=10))
    covered = [False] * len(text)
    for chunk in result:
        for i in range(chunk.start, chunk.end):
            covered[i] = True
    assert all(covered)


# --- Overlap ---------------------------------------------------------------


def test_overlap_produces_shared_content(
    chunker: Chunker, request: pytest.FixtureRequest
) -> None:
    """With non-zero overlap, adjacent chunks share characters."""
    method = _method_for(request.node.callspec.params["chunker"])
    text = "x" * 200  # no separator to fight with — pure char split
    result = chunker.chunk(text, _parent(), _config(method, size=50, overlap=20))
    assert len(result) > 1
    for i in range(1, len(result)):
        # Chunk i starts before chunk i-1 ends → there's an overlap region.
        assert result[i].start < result[i - 1].end


# --- Parent + metadata -----------------------------------------------------


def test_chunks_reference_parent(
    chunker: Chunker, request: pytest.FixtureRequest
) -> None:
    method = _method_for(request.node.callspec.params["chunker"])
    parent = _parent()
    result = chunker.chunk("hello world", parent, _config(method, size=100, overlap=0))
    for chunk in result:
        assert chunk.parent == parent


# --- Config validation -----------------------------------------------------


def test_rejects_non_positive_size(
    chunker: Chunker, request: pytest.FixtureRequest
) -> None:
    method = _method_for(request.node.callspec.params["chunker"])
    with pytest.raises(ValueError, match="size"):
        chunker.chunk("hello", _parent(), _config(method, size=0, overlap=0))


def test_rejects_overlap_not_smaller_than_size(
    chunker: Chunker, request: pytest.FixtureRequest
) -> None:
    method = _method_for(request.node.callspec.params["chunker"])
    with pytest.raises(ValueError, match="overlap"):
        chunker.chunk("hello", _parent(), _config(method, size=10, overlap=10))


# --- Method dispatch -------------------------------------------------------


def test_rejects_wrong_method(
    chunker: Chunker, request: pytest.FixtureRequest
) -> None:
    """A chunker rejects config with a method it does not implement.

    This is how the `ChunkConfig.method` field dispatches across
    implementations bound via `ConfigProvider`.
    """
    current = request.node.callspec.params["chunker"]
    wrong_method = "semantic" if current == "recursive" else "recursive"
    with pytest.raises(ValueError, match="method"):
        chunker.chunk("hello", _parent(), _config(wrong_method, size=100, overlap=0))


# --- Chunk DTO identity ----------------------------------------------------


def test_chunks_are_proper_dto_instances(
    chunker: Chunker, request: pytest.FixtureRequest
) -> None:
    method = _method_for(request.node.callspec.params["chunker"])
    result = chunker.chunk("hello world", _parent(), _config(method, size=100, overlap=0))
    for c in result:
        assert isinstance(c, Chunk)
        assert c.text
        assert c.end > c.start
        assert c.index >= 0
