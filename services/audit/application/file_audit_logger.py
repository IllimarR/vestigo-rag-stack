"""File-based AuditLogger writing JSONL events to a single log file.

Phase 1 stub per `docs/phases.md`:
> Implement file-based AuditLogger stub — writes audit events to a
> structured log file. Enables auditability from the start without
> database infrastructure.

Each event is one JSON object per line. The shape is intentionally flat
(all contract fields + a `type` discriminator) so `query_logs` can scan
linearly and filter. Good enough for hundreds-to-low-thousands of events;
Phase 4 replaces this with a database-backed implementation.
"""

from __future__ import annotations

import json
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

__all__ = ["FileAuditLogger"]


class FileAuditLogger:
    """Append-only JSONL audit log."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)

    def _append(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")

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
        self._append(
            {
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
        self._append(
            {
                "type": "ingest_event",
                "timestamp": timestamp.isoformat(),
                "event_type": event_type.value,
                "reference": reference.model_dump(mode="json"),
                "chunk_count": chunk_count,
                "error_message": error_message,
            }
        )

    def log_admin_event(
        self,
        *,
        action: str,
        actor: str,
        timestamp: datetime,
    ) -> None:
        self._append(
            {
                "type": "admin_event",
                "timestamp": timestamp.isoformat(),
                "action": action,
                "actor": actor,
            }
        )

    def query_logs(
        self,
        *,
        filters: dict[str, Any],
        offset: int = 0,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        with self._lock:
            with self._path.open("r", encoding="utf-8") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    entry: dict[str, Any] = json.loads(raw)
                    if _matches(entry, filters):
                        results.append(entry)
        return results[offset : offset + limit]


def _matches(entry: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Minimal filter support covering the fields named in `docs/contracts.md`."""

    for key, value in filters.items():
        if key in ("type", "event_type"):
            # Accept both a top-level event type (query/ingest_event/admin_event)
            # and an ingest-specific event_type (ingested/updated/deleted/skipped).
            if entry.get(key) != value and entry.get("event_type") != value:
                return False
        elif key == "api_key_id":
            if entry.get("api_key_id") != value:
                return False
        elif key == "status":
            if entry.get("status") != value:
                return False
        elif key == "date_from":
            if entry.get("timestamp", "") < value:
                return False
        elif key == "date_to":
            if entry.get("timestamp", "") > value:
                return False
        # Unknown filter keys are ignored rather than erroring — consistent
        # with prototype-scope forgiveness.
    return True
