"""Placeholder implementation of AuditLogger."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from contracts import (
    DocumentReference,
    IngestEventType,
    QueryStatus,
    RerankedChunk,
    TokenUsage,
)

__all__ = ["NotImplementedAuditLogger"]


def _not_implemented() -> NotImplementedError:
    return NotImplementedError(
        "AuditLogger is a Phase 1 placeholder. Bind a concrete implementation "
        "(file-based or database-backed) in the composition root."
    )


class NotImplementedAuditLogger:
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
        raise _not_implemented()

    def log_ingest_event(
        self,
        *,
        reference: DocumentReference,
        event_type: IngestEventType,
        chunk_count: int,
        timestamp: datetime,
        error_message: str | None = None,
    ) -> None:
        raise _not_implemented()

    def log_admin_event(
        self,
        *,
        action: str,
        actor: str,
        timestamp: datetime,
    ) -> None:
        raise _not_implemented()

    def query_logs(
        self,
        *,
        filters: dict[str, Any],
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        raise _not_implemented()
