"""Immutable data transfer objects shared across all nine contracts.

Every DTO is a frozen Pydantic v2 model so instances are hashable, thread-safe
to pass across module boundaries, and cannot be mutated by consumers.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
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


class _FrozenModel(BaseModel):
    """Base for every DTO — frozen, strict, arbitrary types allowed for bytes."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True, extra="forbid")


# --- Documents ----------------------------------------------------------------


class DocumentReference(_FrozenModel):
    source_id: str
    document_id: str
    filename: str
    last_modified: datetime
    source_url: str | None = None


class ChangeType(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"


class ChangeEvent(_FrozenModel):
    reference: DocumentReference
    change_type: ChangeType


class RawDocument(_FrozenModel):
    reference: DocumentReference
    content: bytes
    file_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConvertedDocument(_FrozenModel):
    reference: DocumentReference
    markdown: str
    converter_id: str
    warnings: tuple[str, ...] = ()


# --- Chunks -------------------------------------------------------------------


class ChunkConfig(_FrozenModel):
    method: str
    size: int
    overlap: int
    parameters: dict[str, Any] = Field(default_factory=dict)


class Chunk(_FrozenModel):
    text: str
    index: int
    start: int
    end: int
    parent: DocumentReference
    metadata: dict[str, Any] = Field(default_factory=dict)


class ScoredChunk(_FrozenModel):
    chunk: Chunk
    similarity_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class RerankedChunk(_FrozenModel):
    chunk: Chunk
    similarity_score: float
    rerank_score: float
    final_rank: int
    metadata: dict[str, Any] = Field(default_factory=dict)


# --- Generation ---------------------------------------------------------------


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ChatMessage(_FrozenModel):
    role: Role
    content: str


class ModelParameters(_FrozenModel):
    temperature: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class GenerationRequest(_FrozenModel):
    system_prompt: str | None
    messages: tuple[ChatMessage, ...]
    parameters: ModelParameters


class TokenUsage(_FrozenModel):
    prompt_tokens: int
    completion_tokens: int


class GenerationResponse(_FrozenModel):
    text: str
    usage: TokenUsage
    model_id: str


class GenerationChunk(_FrozenModel):
    delta: str
    usage: TokenUsage | None = None


# --- Filters and health -------------------------------------------------------


class MetadataFilter(_FrozenModel):
    """A single field filter. `op` controls how `value` is compared."""

    field: str
    op: Literal["eq", "ne", "in", "contains", "gte", "lte", "range"]
    value: Any


class HealthStatus(_FrozenModel):
    healthy: bool
    detail: str | None = None


# --- Application-level configuration DTOs (owned by ConfigProvider) ----------


class EmbeddingConfig(_FrozenModel):
    endpoint: str
    api_type: str
    model_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class RerankerConfig(_FrozenModel):
    type: str
    endpoint: str | None
    model_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class GenerationConfig(_FrozenModel):
    endpoint: str
    api_type: str
    model_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
