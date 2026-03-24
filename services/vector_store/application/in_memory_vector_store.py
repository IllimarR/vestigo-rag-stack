"""In-memory `VectorStoreRepository` — contract-design validation stub.

Phase 1 per `docs/phases.md`:
> Implement a simple in-memory VectorStoreRepository as a throwaway test
> implementation. This is not for production use — it validates that the
> contract is not accidentally coupled to any specific database's
> semantics before the real implementation is built.

Also doubles as thesis evidence for the Modularity Proof Criteria in
`docs/architecture.md` §2: a second, radically different implementation
of the same contract that consumers can swap in with zero code changes.

Cosine similarity is computed in pure Python (O(n·d) per query). Fine
for hundreds-to-low-thousands of chunks at single-digit concurrency —
the scale `README.md` describes. Phase 2 replaces this with ChromaDB
or pgvector.
"""

from __future__ import annotations

import math
import threading
from typing import Any

from contracts import (
    Chunk,
    ChunkWithEmbedding,
    HealthStatus,
    MetadataFilter,
    ScoredChunk,
)

__all__ = ["InMemoryVectorStoreRepository"]


class InMemoryVectorStoreRepository:
    """Dictionary-backed vector store with cosine-similarity retrieval."""

    def __init__(self) -> None:
        self._collections: dict[str, list[ChunkWithEmbedding]] = {}
        self._dimensions: dict[str, int] = {}
        self._lock = threading.Lock()

    # --- Lifecycle ---

    def create_collection(self, name: str, dimension: int) -> None:
        with self._lock:
            if name in self._collections:
                if self._dimensions[name] != dimension:
                    raise ValueError(
                        f"collection {name!r} already exists with dimension "
                        f"{self._dimensions[name]}, cannot recreate with "
                        f"dimension {dimension}."
                    )
                return
            self._collections[name] = []
            self._dimensions[name] = dimension

    def delete_collection(self, name: str) -> None:
        with self._lock:
            self._collections.pop(name, None)
            self._dimensions.pop(name, None)

    def list_collections(self) -> list[str]:
        with self._lock:
            return list(self._collections.keys())

    # --- Writes ---

    def store_chunks(
        self,
        items: list[ChunkWithEmbedding],
        collection: str,
    ) -> None:
        with self._lock:
            if collection not in self._collections:
                raise KeyError(f"collection not found: {collection!r}")
            expected_dim = self._dimensions[collection]
            for _, embedding in items:
                if len(embedding) != expected_dim:
                    raise ValueError(
                        f"embedding dimension {len(embedding)} does not match "
                        f"collection {collection!r} dimension {expected_dim}."
                    )
            self._collections[collection].extend(items)

    # --- Reads ---

    def query_similar(
        self,
        query_embedding: list[float],
        top_k: int,
        collection: str,
        filters: list[MetadataFilter] | None = None,
    ) -> list[ScoredChunk]:
        with self._lock:
            if collection not in self._collections:
                return []
            expected_dim = self._dimensions[collection]
            if len(query_embedding) != expected_dim:
                raise ValueError(
                    f"query embedding dimension {len(query_embedding)} does not "
                    f"match collection {collection!r} dimension {expected_dim}."
                )
            snapshot = list(self._collections[collection])

        scored: list[ScoredChunk] = []
        for chunk, embedding in snapshot:
            if filters and not _matches_filters(chunk, filters):
                continue
            score = _cosine(query_embedding, embedding)
            scored.append(
                ScoredChunk(
                    chunk=chunk,
                    similarity_score=score,
                    metadata=dict(chunk.metadata),
                )
            )
        scored.sort(key=lambda s: s.similarity_score, reverse=True)
        return scored[:top_k]

    # --- Deletes ---

    def delete_by_document(self, document_id: str, collection: str) -> int:
        return self._delete_where(
            collection,
            lambda chunk: chunk.parent.document_id == document_id,
        )

    def delete_by_source(self, source_id: str, collection: str) -> int:
        return self._delete_where(
            collection,
            lambda chunk: chunk.parent.source_id == source_id,
        )

    def _delete_where(
        self,
        collection: str,
        predicate: Any,
    ) -> int:
        with self._lock:
            if collection not in self._collections:
                return 0
            before = len(self._collections[collection])
            self._collections[collection] = [
                (c, e) for c, e in self._collections[collection] if not predicate(c)
            ]
            return before - len(self._collections[collection])

    # --- Health ---

    def health_check(self) -> HealthStatus:
        with self._lock:
            collection_count = len(self._collections)
        return HealthStatus(
            healthy=True,
            detail=f"in-memory backend operational ({collection_count} collections)",
        )


# --- Helpers ---------------------------------------------------------------


def _cosine(a: list[float], b: list[float]) -> float:
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b, strict=True):
        dot += x * y
        norm_a += x * x
        norm_b += y * y
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def _matches_filters(chunk: Chunk, filters: list[MetadataFilter]) -> bool:
    for f in filters:
        value = chunk.metadata.get(f.field)
        if f.op == "eq":
            if value != f.value:
                return False
        elif f.op == "ne":
            if value == f.value:
                return False
        elif f.op == "in":
            if value not in f.value:
                return False
        elif f.op == "contains":
            if not isinstance(value, str) or f.value not in value:
                return False
        elif f.op == "gte":
            if value is None or value < f.value:
                return False
        elif f.op == "lte":
            if value is None or value > f.value:
                return False
        elif f.op == "range":
            low, high = f.value
            if value is None or value < low or value > high:
                return False
    return True
