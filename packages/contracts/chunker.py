"""Chunker contract — splits Markdown into embeddable chunks."""

from __future__ import annotations

from typing import Protocol

from contracts.dto import Chunk, ChunkConfig, DocumentReference

__all__ = ["Chunker"]


class Chunker(Protocol):
    """Splits Markdown text into chunks suitable for embedding.

    Implementations may use recursive, semantic, sliding-window, or any other
    strategy — selection is driven by `ChunkConfig.method`.
    """

    def chunk(
        self,
        markdown: str,
        parent: DocumentReference,
        config: ChunkConfig,
    ) -> list[Chunk]:
        """Split `markdown` into ordered chunks tied to `parent`."""
        ...
