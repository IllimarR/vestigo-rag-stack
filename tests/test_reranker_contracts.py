"""Contract-compliance suite for every `Reranker` implementation.

Each registered backend in `_RERANKERS` is exercised against the same
expectations: ordering, score plumbing, top-k clamping, stable ties,
and the empty-input edge case. A new reranker (LLM-as-reranker, etc.)
plugs in by appending its factory.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from contracts import Chunk, DocumentReference, Reranker, ScoredChunk

from services.llm.application.cross_encoder_reranker import (
    CrossEncoderReranker,
    Scorer,
)

Factory = Callable[[Scorer], Reranker]


# --- Factories -----------------------------------------------------------


def _cross_encoder_factory(scorer: Scorer) -> Reranker:
    return CrossEncoderReranker(scorer=scorer, model_name="stub-cross-encoder")


_RERANKERS: dict[str, Factory] = {
    "cross_encoder": _cross_encoder_factory,
}


@pytest.fixture(params=sorted(_RERANKERS), ids=sorted(_RERANKERS))
def factory(request: pytest.FixtureRequest) -> Factory:
    return _RERANKERS[request.param]


# --- Helpers -------------------------------------------------------------


def _ref(doc_id: str = "doc") -> DocumentReference:
    return DocumentReference(
        source_id="test",
        document_id=doc_id,
        filename=f"{doc_id}.md",
        last_modified=datetime(2026, 3, 28, tzinfo=UTC),
    )


def _scored(text: str, similarity: float, index: int = 0) -> ScoredChunk:
    chunk = Chunk(text=text, index=index, start=0, end=len(text), parent=_ref())
    return ScoredChunk(chunk=chunk, similarity_score=similarity)


def _length_scorer(pairs: list[tuple[str, str]]) -> list[float]:
    """Score = number of characters the query and candidate share by length match."""
    return [float(len(candidate)) for _query, candidate in pairs]


# --- Tests ---------------------------------------------------------------


def test_empty_input_returns_empty(factory: Factory) -> None:
    reranker = factory(_length_scorer)
    assert reranker.rerank("query", [], top_k=5) == []


def test_top_k_clamps_to_input_size(factory: Factory) -> None:
    reranker = factory(_length_scorer)
    out = reranker.rerank("q", [_scored("a", 0.1)], top_k=10)
    assert len(out) == 1


def test_top_k_zero_returns_empty(factory: Factory) -> None:
    reranker = factory(_length_scorer)
    out = reranker.rerank("q", [_scored("a", 0.1)], top_k=0)
    assert out == []


def test_orders_by_scorer_desc(factory: Factory) -> None:
    reranker = factory(_length_scorer)
    chunks = [
        _scored("aa", similarity=0.5, index=0),       # score 2
        _scored("aaaa", similarity=0.4, index=1),     # score 4
        _scored("aaa", similarity=0.6, index=2),      # score 3
    ]

    out = reranker.rerank("q", chunks, top_k=3)
    texts = [r.chunk.text for r in out]
    assert texts == ["aaaa", "aaa", "aa"]
    assert [r.final_rank for r in out] == [0, 1, 2]


def test_carries_original_similarity_and_attaches_rerank(factory: Factory) -> None:
    reranker = factory(_length_scorer)
    chunks = [_scored("hello", similarity=0.42)]

    out = reranker.rerank("q", chunks, top_k=1)

    assert out[0].similarity_score == 0.42
    assert out[0].rerank_score == 5.0  # len("hello")


def test_ties_break_by_original_order(factory: Factory) -> None:
    def constant(pairs: list[tuple[str, str]]) -> list[float]:
        return [1.0 for _ in pairs]

    reranker = factory(constant)
    chunks = [
        _scored("first", similarity=0.1, index=0),
        _scored("second", similarity=0.2, index=1),
        _scored("third", similarity=0.3, index=2),
    ]

    out = reranker.rerank("q", chunks, top_k=3)
    texts = [r.chunk.text for r in out]
    assert texts == ["first", "second", "third"]


def test_get_model_id_is_set(factory: Factory) -> None:
    reranker = factory(_length_scorer)
    assert reranker.get_model_id() == "stub-cross-encoder"


def test_scorer_length_mismatch_raises(factory: Factory) -> None:
    def bad_scorer(pairs: list[tuple[str, str]]) -> list[float]:
        # Always return exactly one score regardless of pair count.
        return [1.0]

    reranker = factory(bad_scorer)
    chunks = [_scored("a", 0.1), _scored("b", 0.2)]
    with pytest.raises(RuntimeError, match="scorer returned"):
        reranker.rerank("q", chunks, top_k=2)
