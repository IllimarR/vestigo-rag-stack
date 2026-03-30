"""Fixed-size character chunker — Phase 5 second `Chunker` implementation.

This is the simplest possible chunker: walk the source text in fixed
windows of `size` characters with a `size - overlap` stride, ignoring
all natural-language boundaries. Where `RecursiveChunker` hunts for
paragraph / sentence / word breaks to keep chunks readable,
`FixedSizeChunker` cuts mid-word if that's where the window ends.

Why this exists
---------------
It's the smallest possible swap target for the `Chunker` contract:
no separator logic, no lookback, no Markdown awareness. Side-by-side
with the recursive chunker it makes the dispatch story easy to see —
both implement `Chunker`, both are picked via `ChunkConfig.method`,
neither leaks into the orchestrator. The same `IngestPipelineOrchestrator`
runs against either, and `ChunkConfig.size` / `ChunkConfig.overlap`
keep their meanings unchanged.

`ChunkConfig.method == "fixed_size"` dispatches this implementation;
any other method value raises so the binding is loud rather than silent.
"""

from __future__ import annotations

from contracts import Chunk, ChunkConfig, DocumentReference

__all__ = ["FixedSizeChunker"]

SUPPORTED_METHOD = "fixed_size"


class FixedSizeChunker:
    """Plain sliding-window chunker — no boundary heuristics."""

    def chunk(
        self,
        markdown: str,
        parent: DocumentReference,
        config: ChunkConfig,
    ) -> list[Chunk]:
        if config.method != SUPPORTED_METHOD:
            raise ValueError(
                f"FixedSizeChunker only supports method={SUPPORTED_METHOD!r}, "
                f"got {config.method!r}. Bind a different `Chunker` "
                "implementation for other methods."
            )
        if config.size <= 0:
            raise ValueError("ChunkConfig.size must be positive.")
        if config.overlap < 0 or config.overlap >= config.size:
            raise ValueError(
                f"ChunkConfig.overlap must be in [0, size); got "
                f"overlap={config.overlap}, size={config.size}."
            )

        if not markdown:
            return []

        length = len(markdown)
        stride = config.size - config.overlap  # validation above guarantees ≥ 1
        chunks: list[Chunk] = []
        start = 0
        index = 0
        while start < length:
            end = min(start + config.size, length)
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
            if end >= length:
                break
            start += stride
            index += 1
        return chunks
