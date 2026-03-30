"""LLM-as-reranker — Phase 5 second `Reranker` implementation.

Where `CrossEncoderReranker` runs a dedicated relevance model, this
adapter borrows the configured `GenerationProvider` to act as a
zero-shot judge: for each `(query, candidate)` pair it prompts the
LLM to emit a single relevance score, and the parsed numbers drive
the same ordering logic as the cross-encoder path.

Why this matters architecturally
--------------------------------
This is the only `Reranker` that *composes another contract*. The
adapter knows nothing about HTTP, Ollama, Anthropic, or any vendor —
it only knows the `GenerationProvider` `Protocol`. So the swap story
nests: the gateway is wired to `LLMReranker`; whichever
`GenerationProvider` is bound (OpenAI HTTP, Anthropic, ...) becomes
the judge, with no further code changes. The modularity proof for
the reranker contract therefore also exercises that contracts
themselves compose cleanly.

Prompt and parsing
------------------
The default prompt asks for a single number 0-10 and uses sentinel
markers (`<<QUERY>>...<<END_QUERY>>`, `<<PASSAGE>>...<<END_PASSAGE>>`)
so test fakes can parse the request without depending on natural-
language phrasing. The score parser pulls the first float-like token
out of the response — robust to "8", "8.5", "Score: 8.5", or
"The relevance is 8.". Pairs that fail to yield any number score 0.0
(better than crashing and losing the rest of the candidates).

`temperature` defaults to 0 for deterministic judging.
"""

from __future__ import annotations

import re

from contracts import (
    ChatMessage,
    GenerationProvider,
    GenerationRequest,
    ModelParameters,
    RerankedChunk,
    Role,
    ScoredChunk,
)

__all__ = ["LLMReranker", "DEFAULT_PROMPT_TEMPLATE"]


DEFAULT_PROMPT_TEMPLATE = (
    "You are scoring how relevant a passage is to a user query. "
    "Reply with a single number between 0 and 10. "
    "10 = directly answers the query; 0 = unrelated.\n\n"
    "<<QUERY>>{query}<<END_QUERY>>\n"
    "<<PASSAGE>>{passage}<<END_PASSAGE>>\n\n"
    "Score:"
)

_SCORE_PATTERN = re.compile(r"-?\d+(?:\.\d+)?")


class LLMReranker:
    """`Reranker` that delegates pair-wise scoring to a `GenerationProvider`."""

    def __init__(
        self,
        *,
        generation_provider: GenerationProvider,
        model_name: str,
        prompt_template: str = DEFAULT_PROMPT_TEMPLATE,
        parameters: ModelParameters | None = None,
    ) -> None:
        self._gen = generation_provider
        self._model_name = model_name
        self._template = prompt_template
        # Low max_tokens — we only need a number. Temperature 0 for
        # reproducible thesis-evidence runs.
        self._parameters = parameters or ModelParameters(
            temperature=0.0,
            max_tokens=16,
        )

    def rerank(
        self,
        query: str,
        scored_chunks: list[ScoredChunk],
        top_k: int,
    ) -> list[RerankedChunk]:
        if not scored_chunks:
            return []

        raw_scores: list[float] = []
        for scored in scored_chunks:
            prompt = self._template.format(query=query, passage=scored.chunk.text)
            request = GenerationRequest(
                system_prompt=None,
                messages=(ChatMessage(role=Role.USER, content=prompt),),
                parameters=self._parameters,
            )
            response = self._gen.generate(request)
            raw_scores.append(_parse_score(response.text))

        # Stable secondary sort by original rank so ties are deterministic —
        # mirrors `CrossEncoderReranker` so the two backends produce the same
        # ordering when fed identical scores.
        order = sorted(
            range(len(scored_chunks)),
            key=lambda i: (-raw_scores[i], i),
        )
        limit = max(0, top_k)
        return [
            RerankedChunk(
                chunk=scored_chunks[idx].chunk,
                similarity_score=scored_chunks[idx].similarity_score,
                rerank_score=raw_scores[idx],
                final_rank=final,
            )
            for final, idx in enumerate(order[:limit])
        ]

    def get_model_id(self) -> str:
        return self._model_name


def _parse_score(text: str) -> float:
    """Extract the first float-like token from an LLM response. Defaults to 0.0."""
    match = _SCORE_PATTERN.search(text)
    if match is None:
        return 0.0
    try:
        return float(match.group(0))
    except ValueError:
        return 0.0
