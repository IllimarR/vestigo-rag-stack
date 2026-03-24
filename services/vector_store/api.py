"""Public boundary of the Vector Store service — in-process library only."""

from __future__ import annotations

from services.vector_store.application.in_memory_vector_store import (
    InMemoryVectorStoreRepository,
)

__all__ = ["InMemoryVectorStoreRepository"]
