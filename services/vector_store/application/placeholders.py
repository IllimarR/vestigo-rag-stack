"""Placeholder implementation of VectorStoreRepository."""

from __future__ import annotations

from contracts import ChunkWithEmbedding, HealthStatus, MetadataFilter, ScoredChunk

__all__ = ["NotImplementedVectorStoreRepository"]


def _not_implemented() -> NotImplementedError:
    return NotImplementedError(
        "VectorStoreRepository is a Phase 1 placeholder. Bind a concrete "
        "implementation (ChromaDB, pgvector, ...) in the composition root."
    )


class NotImplementedVectorStoreRepository:
    def store_chunks(
        self,
        items: list[ChunkWithEmbedding],
        collection: str,
    ) -> None:
        raise _not_implemented()

    def query_similar(
        self,
        query_embedding: list[float],
        top_k: int,
        collection: str,
        filters: list[MetadataFilter] | None = None,
    ) -> list[ScoredChunk]:
        raise _not_implemented()

    def delete_by_document(self, document_id: str, collection: str) -> int:
        raise _not_implemented()

    def delete_by_source(self, source_id: str, collection: str) -> int:
        raise _not_implemented()

    def list_collections(self) -> list[str]:
        raise _not_implemented()

    def create_collection(self, name: str, dimension: int) -> None:
        raise _not_implemented()

    def delete_collection(self, name: str) -> None:
        raise _not_implemented()

    def health_check(self) -> HealthStatus:
        # Phase 1: report unhealthy rather than raising, so /health endpoints
        # upstream can surface the placeholder state without crashing.
        return HealthStatus(
            healthy=False,
            detail="VectorStoreRepository placeholder — no backend bound.",
        )
