"""Shared contracts package — the single dependency hub.

All nine contracts and every DTO they reference are re-exported here so
consumers can write `from contracts import EmbeddingProvider, Chunk`
without reaching into submodules.
"""

from contracts.audit_logger import AuditLogger, IngestEventType, QueryStatus
from contracts.chunker import Chunker
from contracts.config_provider import ConfigProvider
from contracts.document_converter import DocumentConverter
from contracts.dto import (
    ChangeEvent,
    ChangeType,
    ChatMessage,
    Chunk,
    ChunkConfig,
    ConvertedDocument,
    DocumentReference,
    EmbeddingConfig,
    GenerationChunk,
    GenerationConfig,
    GenerationRequest,
    GenerationResponse,
    HealthStatus,
    MetadataFilter,
    ModelParameters,
    RawDocument,
    RerankedChunk,
    RerankerConfig,
    Role,
    ScoredChunk,
    TokenUsage,
)
from contracts.embedding_provider import EmbeddingProvider
from contracts.generation_provider import GenerationProvider
from contracts.reranker import Reranker
from contracts.source_connector import SourceConnector
from contracts.vector_store import ChunkWithEmbedding, VectorStoreRepository

__all__ = [
    # Contracts (nine)
    "AuditLogger",
    "Chunker",
    "ConfigProvider",
    "DocumentConverter",
    "EmbeddingProvider",
    "GenerationProvider",
    "Reranker",
    "SourceConnector",
    "VectorStoreRepository",
    # Supporting types
    "ChunkWithEmbedding",
    "IngestEventType",
    "QueryStatus",
    # DTOs
    "ChangeEvent",
    "ChangeType",
    "ChatMessage",
    "Chunk",
    "ChunkConfig",
    "ConvertedDocument",
    "DocumentReference",
    "EmbeddingConfig",
    "GenerationChunk",
    "GenerationConfig",
    "GenerationRequest",
    "GenerationResponse",
    "HealthStatus",
    "MetadataFilter",
    "ModelParameters",
    "RawDocument",
    "RerankedChunk",
    "RerankerConfig",
    "Role",
    "ScoredChunk",
    "TokenUsage",
]
