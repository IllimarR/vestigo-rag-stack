"""VectorStoreRepository contract — sole access point to the vector database."""

from __future__ import annotations

from typing import Protocol

from contracts.dto import Chunk, HealthStatus, MetadataFilter, ScoredChunk

__all__ = ["ChunkWithEmbedding", "VectorStoreRepository"]


# Kept as a tuple alias to avoid a DTO for a transport-only pair.
ChunkWithEmbedding = tuple[Chunk, list[float]]


class VectorStoreRepository(Protocol):
    """No module may bypass this contract to touch the underlying database.

    Swappable across backends (ChromaDB, pgvector, Milvus, ...) — choosing
    the backend is a deployment-time decision set via `.env`, not an
    application-level `ConfigProvider` setting.
    """

    def store_chunks(
        self,
        items: list[ChunkWithEmbedding],
        collection: str,
    ) -> None:
        """Store chunks together with their embeddings and metadata."""
        ...

    def query_similar(
        self,
        query_embedding: list[float],
        top_k: int,
        collection: str,
        filters: list[MetadataFilter] | None = None,
    ) -> list[ScoredChunk]:
        """Return the most similar chunks by vector distance."""
        ...

    def delete_by_document(self, document_id: str, collection: str) -> int:
        """Remove all chunks belonging to a document; return count removed."""
        ...

    def delete_by_source(self, source_id: str, collection: str) -> int:
        """Remove all chunks from a specific source; return count removed."""
        ...

    def list_collections(self) -> list[str]:
        """Available collections (knowledge bases) in this store."""
        ...

    def create_collection(self, name: str, dimension: int) -> None:
        """Create a new collection with the given embedding dimensionality."""
        ...

    def delete_collection(self, name: str) -> None:
        """Delete a collection and all its data."""
        ...

    def health_check(self) -> HealthStatus:
        """Report whether the vector store backend is reachable."""
        ...
