"""Recursive character text splitter — Phase 2 first `Chunker` implementation.

Algorithm
---------
A sliding window over the source text that prefers to end each chunk at a
natural boundary. For each position:
  1. Tentatively close the chunk at `start + size`.
  2. Search backward from that endpoint (up to `size // 4` chars) for the
     highest-priority separator in the `separators` list.
  3. If a separator is found, close the chunk just after it; otherwise
     close at the hard character cap.
  4. Next chunk starts at `end - overlap` so adjacent chunks share context.

The resulting `Chunk.start` / `Chunk.end` are positions in the *original*
Markdown, and `Chunk.text` is the verbatim slice at those positions —
overlap is a natural consequence of offset, not a duplication of text.

Only `ChunkConfig.method == "recursive"` is supported; other methods would
live in sibling implementations (`SemanticChunker`, etc.) bound to the
`Chunker` contract by the composition root based on `ChunkConfig.method`.
"""

from __future__ import annotations

from contracts import Chunk, ChunkConfig, DocumentReference

__all__ = ["RecursiveChunker"]

SUPPORTED_METHOD = "recursive"

# Separators in descending priority — coarsest first, character last.
DEFAULT_SEPARATORS: tuple[str, ...] = (
    "\n\n",    # Paragraph break
    "\n",      # Line break
    ". ",      # Sentence
    "? ",
    "! ",
    "; ",
    ", ",
    " ",       # Word boundary
)


class RecursiveChunker:
    """Boundary-aware recursive character chunker."""

    def __init__(self, separators: tuple[str, ...] | None = None) -> None:
        self._separators = separators if separators is not None else DEFAULT_SEPARATORS

    def chunk(
        self,
        markdown: str,
        parent: DocumentReference,
        config: ChunkConfig,
    ) -> list[Chunk]:
        if config.method != SUPPORTED_METHOD:
            raise ValueError(
                f"RecursiveChunker only supports method={SUPPORTED_METHOD!r}, "
                f"got {config.method!r}. Bind a different `Chunker` implementation "
                "for other methods."
            )
        if config.size <= 0:
            raise ValueError("ChunkConfig.size must be positive.")
        if config.overlap < 0 or config.overlap >= config.size:
            raise ValueError(
                f"ChunkConfig.overlap must be in [0, size); got overlap={config.overlap}, "
                f"size={config.size}."
            )

        if not markdown:
            return []

        positions = _split_with_positions(
            markdown,
            size=config.size,
            overlap=config.overlap,
            separators=self._separators,
        )
        chunks: list[Chunk] = []
        for index, (start, end) in enumerate(positions):
            chunks.append(
                Chunk(
                    text=markdown[start:end],
                    index=index,
                    start=start,
                    end=end,
                    parent=parent,
                    metadata={},
                )
            )
        return chunks


# --- Helpers ---------------------------------------------------------------


def _split_with_positions(
    text: str,
    *,
    size: int,
    overlap: int,
    separators: tuple[str, ...],
) -> list[tuple[int, int]]:
    """Return (start, end) positions for each chunk in `text`."""
    results: list[tuple[int, int]] = []
    start = 0
    length = len(text)

    # How far back from the hard cap we're willing to reach for a separator.
    lookback = max(1, size // 4)

    while start < length:
        hard_end = min(start + size, length)
        if hard_end >= length:
            # No more text after this chunk — take the rest verbatim;
            # no need to hunt for a separator.
            end = length
        else:
            end = _find_boundary(
                text,
                hard_end=hard_end,
                min_end=max(start + 1, hard_end - lookback),
                separators=separators,
            )
        results.append((start, end))

        if end >= length:
            break
        # Advance with overlap; guarantee forward progress.
        next_start = max(start + 1, end - overlap)
        start = next_start

    return results


def _find_boundary(
    text: str,
    *,
    hard_end: int,
    min_end: int,
    separators: tuple[str, ...],
) -> int:
    """Pick the best endpoint ≤ hard_end. Prefer earlier separators."""
    for sep in separators:
        idx = text.rfind(sep, min_end, hard_end)
        if idx != -1:
            return idx + len(sep)
    return hard_end
