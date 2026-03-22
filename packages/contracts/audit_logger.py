"""AuditLogger contract — structured audit trail for all services."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from contracts.dto import DocumentReference, RerankedChunk, TokenUsage

__all__ = ["AuditLogger", "IngestEventType", "QueryStatus"]


class QueryStatus(str, Enum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class IngestEventType(str, Enum):
    INGESTED = "ingested"
    UPDATED = "updated"
    DELETED = "deleted"
    SKIPPED = "skipped"


class AuditLogger(Protocol):
    """Every service emits events through this contract. Backend is swappable
    (file, database, external log system). Deployment-time binding.
    """

    def log_query(
        self,
        *,
        query: str,
        retrieved: list[RerankedChunk],
        response_text: str,
        usage: TokenUsage,
        timestamp: datetime,
        api_key_id: str,
        status: QueryStatus,
        error_message: str | None = None,
    ) -> None:
        """Record a full RAG query cycle (success, partial, or failure)."""
        ...

    def log_ingest_event(
        self,
        *,
        reference: DocumentReference,
        event_type: IngestEventType,
        chunk_count: int,
        timestamp: datetime,
        error_message: str | None = None,
    ) -> None:
        """Record a document lifecycle event, including skipped unsupported files."""
        ...

    def log_admin_event(
        self,
        *,
        action: str,
        actor: str,
        timestamp: datetime,
    ) -> None:
        """Record an administrative action."""
        ...

    def query_logs(
        self,
        *,
        filters: dict[str, Any],
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Retrieve audit logs for the Admin UI (shape is backend-defined)."""
        ...
