"""GenerationProvider contract — generates natural-language responses."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from contracts.dto import GenerationChunk, GenerationRequest, GenerationResponse

__all__ = ["GenerationProvider"]


class GenerationProvider(Protocol):
    """Supports both one-shot and streaming generation.

    Implementations wrap OpenAI (legacy + current), Anthropic, or any other
    provider behind a single surface.
    """

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Return the complete generated response."""
        ...

    def generate_stream(self, request: GenerationRequest) -> Iterator[GenerationChunk]:
        """Yield partial deltas; usage is populated on the final chunk."""
        ...

    def get_model_id(self) -> str:
        """Identifier of the generation model in use."""
        ...
