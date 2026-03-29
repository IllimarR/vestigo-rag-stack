"""SQLite-backed AuditLogger — Phase 4 replacement for the file stub.

Same observable surface as `FileAuditLogger`: `query_logs` returns the
same JSON record shape, the file backend just stores it line-by-line in
JSONL while sqlite stores it as a JSON column.

Old JSONL logs are not migrated. Operators flipping `AUDIT_BACKEND` from
`file` to `sqlite` start with an empty audit table; the JSONL file
stays on disk as a historical artefact. The migration story is
documented in `docs/phases.md` Phase 4 — adequate for a prototype, and
real installations can either tail the JSONL or replay it as a one-off
script if they care.
"""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path
from typing import Any

from contracts import (
    DocumentReference,
    IngestEventType,
    QueryStatus,
    RerankedChunk,
    TokenUsage,
)
from control_plane import Base, get_engine, make_session_factory
from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from services.audit.application.persistence.models import AuditEvent

__all__ = ["SqliteAuditLogger"]


class SqliteAuditLogger:
    """SQLite implementation of the `AuditLogger` contract."""

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine
        self._session_factory: sessionmaker[Any] = make_session_factory(engine)
        self._lock = threading.Lock()
        Base.metadata.create_all(engine)

    @classmethod
    def from_path(cls, path: Path) -> SqliteAuditLogger:
        return cls(engine=get_engine(path))

    # --- internal write helper ------------------------------------------------

    def _append(
        self,
        *,
        type_: str,
        timestamp: datetime,
        payload: dict[str, Any],
        api_key_id: str | None = None,
        status: str | None = None,
        event_type: str | None = None,
    ) -> None:
        with self._lock, self._session_factory() as session:
            session.add(
                AuditEvent(
                    type=type_,
                    timestamp=timestamp,
                    api_key_id=api_key_id,
                    status=status,
                    event_type=event_type,
                    payload=payload,
                )
            )
            session.commit()

    # --- log_* methods --------------------------------------------------------

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
        payload = {
            "type": "query",
            "timestamp": timestamp.isoformat(),
            "api_key_id": api_key_id,
            "status": status.value,
            "query": query,
            "retrieved": [rc.model_dump(mode="json") for rc in retrieved],
            "response_text": response_text,
            "usage": usage.model_dump(mode="json"),
            "error_message": error_message,
        }
        self._append(
            type_="query",
            timestamp=timestamp,
            payload=payload,
            api_key_id=api_key_id,
            status=status.value,
        )

    def log_ingest_event(
        self,
        *,
        reference: DocumentReference,
        event_type: IngestEventType,
        chunk_count: int,
        timestamp: datetime,
        error_message: str | None = None,
    ) -> None:
        payload = {
            "type": "ingest_event",
            "timestamp": timestamp.isoformat(),
            "event_type": event_type.value,
            "reference": reference.model_dump(mode="json"),
            "chunk_count": chunk_count,
            "error_message": error_message,
        }
        self._append(
            type_="ingest_event",
            timestamp=timestamp,
            payload=payload,
            event_type=event_type.value,
        )

    def log_admin_event(
        self,
        *,
        action: str,
        actor: str,
        timestamp: datetime,
    ) -> None:
        payload = {
            "type": "admin_event",
            "timestamp": timestamp.isoformat(),
            "action": action,
            "actor": actor,
        }
        self._append(type_="admin_event", timestamp=timestamp, payload=payload)

    # --- query_logs -----------------------------------------------------------

    def query_logs(
        self,
        *,
        filters: dict[str, Any],
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Apply the filter set used by `FileAuditLogger` to its JSONL rows,
        but on indexed SQL columns instead of a linear scan.

        Filter keys: `type`, `event_type`, `api_key_id`, `status`,
        `date_from`, `date_to`. Unknown keys are ignored to match the
        prototype-scope forgiveness of the file backend. The `type`
        filter additionally matches `event_type` (e.g. `type=ingested`
        finds ingest events with that variant) — same fallback the file
        backend implements.
        """

        stmt = select(AuditEvent).order_by(AuditEvent.id)
        type_filter = filters.get("type") or filters.get("event_type")
        if type_filter:
            stmt = stmt.where(
                (AuditEvent.type == type_filter)
                | (AuditEvent.event_type == type_filter)
            )
        if "api_key_id" in filters:
            stmt = stmt.where(AuditEvent.api_key_id == filters["api_key_id"])
        if "status" in filters:
            stmt = stmt.where(AuditEvent.status == filters["status"])
        date_from = _parse_iso(filters.get("date_from"))
        date_to = _parse_iso(filters.get("date_to"))
        if date_from is not None:
            stmt = stmt.where(AuditEvent.timestamp >= date_from)
        if date_to is not None:
            stmt = stmt.where(AuditEvent.timestamp <= date_to)

        stmt = stmt.offset(offset).limit(limit)
        with self._session_factory() as session:
            rows = session.execute(stmt).scalars().all()
        return [row.payload for row in rows]


def _parse_iso(value: Any) -> datetime | None:
    """Accept an ISO-8601 string or a `datetime` as a date-range filter input.

    File backend filters expect ISO strings; SQL backend needs typed
    datetimes for portable comparison. This adapter accepts either so
    `query_logs` filters look identical regardless of backend choice.
    """

    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise TypeError(
        f"date_from/date_to must be ISO string or datetime, got {type(value).__name__}"
    )
