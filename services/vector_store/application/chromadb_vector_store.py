"""ChromaDB-backed `VectorStoreRepository` — Phase 2 first real backend.

Storage model
-------------
Each `Chunk` is serialized to JSON and stashed in ChromaDB metadata under
a reserved key (`_vrs_chunk_json`), alongside flat bookkeeping fields the
delete-by-document / delete-by-source paths need. The user's
`chunk.metadata` dict is additionally flattened to top-level keys so
ChromaDB's native `where` clause can filter on them.

Similarity score
----------------
Collections are created with `hnsw.space = cosine`, so ChromaDB's query
returns cosine *distance* ∈ [0, 2]. The contract expects a similarity
score; we surface `1 - distance` to match the in-memory backend and put
perfect matches at 1.0.

Server connection
-----------------
The repository connects to a ChromaDB server through `chromadb.HttpClient`.
This keeps ChromaDB as a separate deployment component instead of embedding
the database inside the RAG service process.

Filter translation
------------------
Most `MetadataFilter` ops map to ChromaDB's `where` operators. `contains`
has no native equivalent for metadata, so it's evaluated in Python after
a broader retrieval — documented as best-effort.
"""

from __future__ import annotations

import threading
from typing import Any

import chromadb
from chromadb.api import ClientAPI
from chromadb.errors import NotFoundError
from contracts import (
    Chunk,
    ChunkWithEmbedding,
    HealthStatus,
    MetadataFilter,
    ScoredChunk,
)

__all__ = ["ChromaDbVectorStoreRepository"]


# Reserved metadata keys used internally; `_vrs_` prefix avoids collision
# with user-provided metadata keys.
_CHUNK_PAYLOAD = "_vrs_chunk_json"
_SOURCE_ID = "_vrs_source_id"
_DOCUMENT_ID = "_vrs_document_id"
_CHUNK_INDEX = "_vrs_chunk_index"
_DIMENSION_META = "dimension"


class ChromaDbVectorStoreRepository:
    """ChromaDB implementation of the `VectorStoreRepository` contract."""

    def __init__(
        self,
        *,
        host: str = "localhost",
        port: int = 8000,
        ssl: bool = False,
        headers: dict[str, str] | None = None,
        client: ClientAPI | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._client = client or chromadb.HttpClient(
            host=host,
            port=port,
            ssl=ssl,
            headers=headers,
        )

    # --- Lifecycle ---

    def create_collection(self, name: str, dimension: int) -> None:
        with self._lock:
            try:
                existing = self._client.get_collection(name)
            except NotFoundError:
                self._client.create_collection(
                    name=name,
                    metadata={_DIMENSION_META: dimension},
                    configuration={"hnsw": {"space": "cosine"}},
                )
                return
            existing_dim = (existing.metadata or {}).get(_DIMENSION_META)
            if existing_dim is not None and existing_dim != dimension:
                raise ValueError(
                    f"collection {name!r} already exists with dimension "
                    f"{existing_dim}, cannot recreate with dimension {dimension}."
                )
            # Idempotent when dimensions match.

    def delete_collection(self, name: str) -> None:
        with self._lock:
            try:
                self._client.delete_collection(name)
            except NotFoundError:
                pass  # idempotent

    def list_collections(self) -> list[str]:
        with self._lock:
            return [c.name for c in self._client.list_collections()]

    # --- Writes ---

    def store_chunks(
        self,
        items: list[ChunkWithEmbedding],
        collection: str,
    ) -> None:
        if not items:
            return
        with self._lock:
            try:
                col = self._client.get_collection(collection)
            except NotFoundError as e:
                raise KeyError(f"collection not found: {collection!r}") from e
            expected_dim = (col.metadata or {}).get(_DIMENSION_META)
            ids: list[str] = []
            embeddings: list[list[float]] = []
            documents: list[str] = []
            metadatas: list[dict[str, Any]] = []
            for chunk, embedding in items:
                if expected_dim is not None and len(embedding) != expected_dim:
                    raise ValueError(
                        f"embedding dimension {len(embedding)} does not match "
                        f"collection {collection!r} dimension {expected_dim}."
                    )
                ids.append(_make_id(chunk))
                embeddings.append(list(embedding))
                documents.append(chunk.text)
                metadatas.append(_chunk_to_metadata(chunk))
            col.upsert(
                ids=ids,
                embeddings=embeddings,  # type: ignore[arg-type]
                documents=documents,
                metadatas=metadatas,  # type: ignore[arg-type]
            )

    # --- Reads ---

    def query_similar(
        self,
        query_embedding: list[float],
        top_k: int,
        collection: str,
        filters: list[MetadataFilter] | None = None,
    ) -> list[ScoredChunk]:
        with self._lock:
            try:
                col = self._client.get_collection(collection)
            except NotFoundError:
                return []
            expected_dim = (col.metadata or {}).get(_DIMENSION_META)
            if expected_dim is not None and len(query_embedding) != expected_dim:
                raise ValueError(
                    f"query embedding dimension {len(query_embedding)} does not "
                    f"match collection {collection!r} dimension {expected_dim}."
                )

            native_filters, python_filters = _partition_filters(filters or [])
            where = _translate_filters(native_filters) if native_filters else None

            # Over-fetch when we need to post-filter in Python, so the final
            # top_k isn't starved by post-filtering.
            fetch_k = top_k * 4 if python_filters else top_k

            kwargs: dict[str, Any] = {
                "query_embeddings": [list(query_embedding)],
                "n_results": fetch_k,
            }
            if where is not None:
                kwargs["where"] = where
            result = col.query(**kwargs)

        return _rows_to_scored_chunks(result, python_filters, top_k)

    # --- Deletes ---

    def delete_by_document(self, document_id: str, collection: str) -> int:
        return self._delete_by(_DOCUMENT_ID, document_id, collection)

    def delete_by_source(self, source_id: str, collection: str) -> int:
        return self._delete_by(_SOURCE_ID, source_id, collection)

    def _delete_by(self, field: str, value: str, collection: str) -> int:
        with self._lock:
            try:
                col = self._client.get_collection(collection)
            except NotFoundError:
                return 0
            matches = col.get(where={field: value})
            match_ids = matches.get("ids") or []
            count = len(match_ids)
            if count > 0:
                col.delete(where={field: value})
            return count

    # --- Health ---

    def health_check(self) -> HealthStatus:
        try:
            self._client.heartbeat()
        except Exception as e:  # noqa: BLE001 — surface any failure as unhealthy
            return HealthStatus(healthy=False, detail=f"{type(e).__name__}: {e}")
        return HealthStatus(healthy=True, detail="chromadb operational")


# --- Helpers ---------------------------------------------------------------


def _make_id(chunk: Chunk) -> str:
    return f"{chunk.parent.source_id}:{chunk.parent.document_id}:{chunk.index}"


def _chunk_to_metadata(chunk: Chunk) -> dict[str, Any]:
    meta: dict[str, Any] = {
        _CHUNK_PAYLOAD: chunk.model_dump_json(),
        _SOURCE_ID: chunk.parent.source_id,
        _DOCUMENT_ID: chunk.parent.document_id,
        _CHUNK_INDEX: chunk.index,
    }
    for k, v in chunk.metadata.items():
        if isinstance(v, (str, int, float, bool)) or v is None:
            meta[k] = v
    return meta


def _metadata_to_chunk(metadata: dict[str, Any]) -> Chunk:
    return Chunk.model_validate_json(metadata[_CHUNK_PAYLOAD])


def _partition_filters(
    filters: list[MetadataFilter],
) -> tuple[list[MetadataFilter], list[MetadataFilter]]:
    native: list[MetadataFilter] = []
    python_only: list[MetadataFilter] = []
    for f in filters:
        if f.op == "contains":
            python_only.append(f)
        else:
            native.append(f)
    return native, python_only


def _translate_filters(filters: list[MetadataFilter]) -> dict[str, Any]:
    if len(filters) == 1:
        return _single_filter(filters[0])
    return {"$and": [_single_filter(f) for f in filters]}


def _single_filter(f: MetadataFilter) -> dict[str, Any]:
    if f.op == "eq":
        return {f.field: f.value}
    if f.op == "ne":
        return {f.field: {"$ne": f.value}}
    if f.op == "in":
        return {f.field: {"$in": list(f.value)}}
    if f.op == "gte":
        return {f.field: {"$gte": f.value}}
    if f.op == "lte":
        return {f.field: {"$lte": f.value}}
    if f.op == "range":
        low, high = f.value
        return {"$and": [{f.field: {"$gte": low}}, {f.field: {"$lte": high}}]}
    # contains is handled as a Python post-filter upstream.
    raise ValueError(f"unsupported filter op in native translator: {f.op!r}")


def _python_match(chunk: Chunk, filters: list[MetadataFilter]) -> bool:
    for f in filters:
        value = chunk.metadata.get(f.field)
        if f.op == "contains":
            if not isinstance(value, str) or f.value not in value:
                return False
        else:
            # Should not happen — partitioning routes native ops elsewhere.
            raise ValueError(f"unexpected filter op in python matcher: {f.op!r}")
    return True


def _rows_to_scored_chunks(
    result: Any,
    python_filters: list[MetadataFilter],
    top_k: int,
) -> list[ScoredChunk]:
    id_rows = result.get("ids") or []
    if not id_rows:
        return []
    ids: list[str] = id_rows[0]
    metadata_rows = result.get("metadatas") or []
    distance_rows = result.get("distances") or []
    metadatas: list[dict[str, Any] | None] = metadata_rows[0] if metadata_rows else []
    distances: list[float] = distance_rows[0] if distance_rows else []

    scored: list[ScoredChunk] = []
    for idx in range(len(ids)):
        if idx >= len(metadatas):
            continue
        metadata = metadatas[idx]
        if metadata is None:
            continue
        chunk = _metadata_to_chunk(metadata)
        if python_filters and not _python_match(chunk, python_filters):
            continue
        distance = distances[idx] if idx < len(distances) else 0.0
        similarity = 1.0 - distance
        scored.append(
            ScoredChunk(
                chunk=chunk,
                similarity_score=similarity,
                metadata=dict(chunk.metadata),
            )
        )
        if len(scored) >= top_k:
            break
    return scored
