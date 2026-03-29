"""SQLAlchemy table for audit events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from control_plane import Base
from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

__all__ = ["AuditEvent"]


class AuditEvent(Base):
    """One row per audit event.

    Layout choice — single-table with discriminator + JSON payload —
    mirrors how `FileAuditLogger` stores events in JSONL:

      * `type` ('query' / 'ingest_event' / 'admin_event')
        discriminates the variant. Top-level filter for the audit-log
        viewer.
      * `event_type` (ingested / updated / deleted / skipped) is only
        meaningful for ingest events; nullable for query and admin events.
      * `api_key_id` and `status` are only set on query events.
      * `payload` holds the full event dict, identical to the JSONL row
        the file backend writes. `query_logs` deserialises and returns
        it as-is, so the file and sqlite backends produce
        indistinguishable output.

    Filterable columns are indexed; the payload column is opaque to the
    filter logic. Adding a new event variant means adding a new `type`
    value and (optionally) one or two indexed columns — no migration if
    the new variant reuses existing filter columns.
    """

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    api_key_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    status: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    event_type: Mapped[str | None] = mapped_column(String(16), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
