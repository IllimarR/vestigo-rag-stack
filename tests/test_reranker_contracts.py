"""Contract-compliance suite for every `Reranker` implementation.

Each registered backend in `_RERANKERS` is exercised against the same
expectations: ordering, score plumbing, top-k clamping, stable ties,
and the empty-input edge case.

Each factory receives a `Scorer` callable describing the *intended*
per-pair scores. Cross-encoder uses it directly. The LLM-as-reranker
backend wraps it in a fake `GenerationProvider` that parses the
`(query, passage)` pair back out of `LLMReranker`'s prompt markers and
returns the score as the response text — so the same contract
expectations cover both backends without leaking either's internals.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from contracts import (
    Chunk,
    DocumentReference,
    GenerationChunk,
    GenerationRequest,
    GenerationResponse,
    Reranker,
    ScoredChunk,
    TokenUsage,
)

from services.llm.application.cross_encoder_reranker import (
    CrossEncoderReranker,
    Scorer,
)
from services.llm.application.llm_reranker import LLMReranker

Factory = Callable[[Scorer], Reranker]


# --- Factories -----------------------------------------------------------


def _cross_encoder_factory(scorer: Scorer) -> Reranker:
    return CrossEncoderReranker(scorer=scorer, model_name="stub-cross-encoder")


_QUERY_RE = re.compile(r"<<QUERY>>(.*?)<<END_QUERY>>", re.DOTALL)
_PASSAGE_RE = re.compile(r"<<PASSAGE>>(.*?)<<END_PASSAGE>>", re.DOTALL)


class _ScorerBackedGenerationProvider:
    """Fake `GenerationProvider` that drives `LLMReranker` from a `Scorer`.

    Parses the sentinel markers `LLMReranker` writes into its prompt,
    asks the test `Scorer` for the score, and returns that number as
    the response text — exactly what the parser inside `LLMReranker`
    will pull back out.
    """

    def __init__(self, scorer: Scorer) -> None:
        self._scorer = scorer

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        user_msg = request.messages[-1].content
        query_match = _QUERY_RE.search(user_msg)
        passage_match = _PASSAGE_RE.search(user_msg)
        if query_match is None or passage_match is None:
            raise RuntimeError(
                "Test fake could not find LLMReranker markers in prompt."
            )
        score = self._scorer([(query_match.group(1), passage_match.group(1))])[0]
        return GenerationResponse(
            text=str(score),
            usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
            model_id="stub-llm-judge",
        )

    def generate_stream(
        self, request: GenerationRequest
    ) -> Iterator[GenerationChunk]:  # pragma: no cover - reranker uses unary path
        yield GenerationChunk(delta=self.generate(request).text)

    def get_model_id(self) -> str:
        return "stub-llm-judge"


def _llm_reranker_factory(scorer: Scorer) -> Reranker:
    return LLMReranker(
        generation_provider=_ScorerBackedGenerationProvider(scorer),
        model_name="stub-llm-judge",
    )


_RERANKERS: dict[str, Factory] = {
    "cross_encoder": _cross_encoder_factory,
    "llm": _llm_reranker_factory,
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


def test_get_model_id_is_non_empty(factory: Factory) -> None:
    reranker = factory(_length_scorer)
    model_id = reranker.get_model_id()
    assert isinstance(model_id, str)
    assert model_id


# --- Backend-specific behavior --------------------------------------------


def test_cross_encoder_scorer_length_mismatch_raises() -> None:
    """Cross-encoder enforces 1:1 between pairs and returned scores.

    The LLM reranker uses a separate request per pair, so the contract
    expressed here is specific to the batch-scorer backend.
    """

    def bad_scorer(pairs: list[tuple[str, str]]) -> list[float]:
        return [1.0]  # always one score regardless of pair count

    reranker = CrossEncoderReranker(scorer=bad_scorer, model_name="bad")
    chunks = [_scored("a", 0.1), _scored("b", 0.2)]
    with pytest.raises(RuntimeError, match="scorer returned"):
        reranker.rerank("q", chunks, top_k=2)


def test_llm_reranker_parses_noisy_response() -> None:
    """`_parse_score` should pull a float out of natural-language wrappers."""

    class NoisyProvider:
        def __init__(self) -> None:
            self.idx = -1
            self.outputs = ["Score: 8.5", "the relevance is 3", "10/10"]

        def generate(self, request: GenerationRequest) -> GenerationResponse:
            self.idx += 1
            return GenerationResponse(
                text=self.outputs[self.idx],
                usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
                model_id="noisy",
            )

        def generate_stream(  # pragma: no cover
            self, request: GenerationRequest
        ) -> Iterator[GenerationChunk]:
            yield GenerationChunk(delta="")

        def get_model_id(self) -> str:
            return "noisy"

    reranker = LLMReranker(
        generation_provider=NoisyProvider(),
        model_name="noisy",
    )
    chunks = [
        _scored("first", 0.1, index=0),
        _scored("second", 0.2, index=1),
        _scored("third", 0.3, index=2),
    ]

    out = reranker.rerank("q", chunks, top_k=3)
    # Expected scores: 8.5, 3, 10 → order: third (10), first (8.5), second (3)
    assert [r.chunk.text for r in out] == ["third", "first", "second"]
    assert [r.rerank_score for r in out] == [10.0, 8.5, 3.0]


def test_llm_reranker_unparseable_response_scores_zero() -> None:
    """A no-number response must not crash; the candidate sinks to score 0."""

    class JunkProvider:
        def generate(self, request: GenerationRequest) -> GenerationResponse:
            return GenerationResponse(
                text="I cannot judge this",
                usage=TokenUsage(prompt_tokens=0, completion_tokens=0),
                model_id="junk",
            )

        def generate_stream(  # pragma: no cover
            self, request: GenerationRequest
        ) -> Iterator[GenerationChunk]:
            yield GenerationChunk(delta="")

        def get_model_id(self) -> str:
            return "junk"

    reranker = LLMReranker(
        generation_provider=JunkProvider(),
        model_name="junk",
    )
    out = reranker.rerank("q", [_scored("a", 0.1)], top_k=1)
    assert out[0].rerank_score == 0.0
