"""ApiPushSourceConnector — implements SourceConnector for HTTP-pushed docs.

The Ingest API at port 8002 is the external face of this connector,
per `docs/architecture.md` §1: "the Ingest API is implemented as an
`ApiPushSourceConnector` — an implementation that receives documents
via HTTP and emits them as standard `ChangeEvent` objects, preserving
contract isolation."

Lifecycle of a pushed document
------------------------------
1. The HTTP route calls `push_document(...)` (ADDED/MODIFIED) or
   `push_deletion(...)`. The connector:
     a. stores the `RawDocument` in an in-memory staging dict keyed by
        `document_id` (skipping the body on deletion);
     b. queues a `ChangeEvent` whose `change_type` is decided by whether
        the connector has seen this document before — ADDED on first
        sight, MODIFIED on subsequent pushes.
2. The route calls `IngestPipelineOrchestrator.process_changes(...)`
   with the events drained via `detect_changes(...)`. The orchestrator
   calls back into `fetch_document(...)` to pull the staged bytes.
3. After processing, callers may invoke `drop(document_id)` to release
   the staged bytes. For the prototype's request-scoped HTTP flow we
   always drop after process_changes so memory doesn't accumulate.

Memory cost is bounded by request size + the brief window between push
and process — fine for the documents-at-a-time push pattern Phase 4
ships. Persistent queueing (e.g. for retry on orchestrator failure)
would be a future enhancement.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from typing import Any

from contracts import ChangeEvent, ChangeType, DocumentReference, RawDocument

__all__ = ["ApiPushSourceConnector"]


class ApiPushSourceConnector:
    """In-memory push connector emitting events on stage_* calls."""

    def __init__(self, *, source_id: str = "api") -> None:
        self._source_id = source_id
        self._staged: dict[str, RawDocument] = {}
        self._known: set[str] = set()
        self._queue: list[ChangeEvent] = []
        self._lock = threading.Lock()

    # --- Push API used by ingest routes ---------------------------------------

    def push_document(
        self,
        *,
        document_id: str,
        filename: str,
        file_type: str,
        content: bytes,
        last_modified: datetime | None = None,
        metadata: dict[str, Any] | None = None,
        source_url: str | None = None,
    ) -> ChangeEvent:
        """Stage an upload. Emits MODIFIED if `document_id` is known, else ADDED.

        The connector decides ADDED vs MODIFIED — callers don't need to track
        prior state. Returns the queued event for convenience (test bodies
        often want to assert directly on the event shape).
        """

        modified_at = last_modified or datetime.now(UTC)
        ref = DocumentReference(
            source_id=self._source_id,
            document_id=document_id,
            filename=filename,
            last_modified=modified_at,
            source_url=source_url,
        )
        raw = RawDocument(
            reference=ref,
            content=content,
            file_type=file_type.lower().lstrip("."),
            metadata=dict(metadata or {}),
        )
        with self._lock:
            change_type = (
                ChangeType.MODIFIED if document_id in self._known else ChangeType.ADDED
            )
            self._staged[document_id] = raw
            self._known.add(document_id)
            event = ChangeEvent(reference=ref, change_type=change_type)
            self._queue.append(event)
        return event

    def push_deletion(
        self,
        *,
        document_id: str,
        filename: str | None = None,
        last_modified: datetime | None = None,
    ) -> ChangeEvent:
        """Stage a deletion. No content payload needed."""

        ref = DocumentReference(
            source_id=self._source_id,
            document_id=document_id,
            filename=filename or document_id,
            last_modified=last_modified or datetime.now(UTC),
        )
        with self._lock:
            self._staged.pop(document_id, None)
            self._known.discard(document_id)
            event = ChangeEvent(reference=ref, change_type=ChangeType.DELETED)
            self._queue.append(event)
        return event

    def drop(self, document_id: str) -> None:
        """Release any staged content for `document_id` after the
        orchestrator has finished processing it."""

        with self._lock:
            self._staged.pop(document_id, None)

    # --- SourceConnector contract surface -------------------------------------

    def list_documents(self) -> list[DocumentReference]:
        with self._lock:
            return [raw.reference for raw in self._staged.values()]

    def detect_changes(self, since: datetime) -> list[ChangeEvent]:
        """Drain the queue. `since` filters by `reference.last_modified`."""

        since_aware = since if since.tzinfo is not None else since.replace(tzinfo=UTC)
        with self._lock:
            pending = self._queue
            self._queue = []
        return [e for e in pending if _as_utc(e.reference.last_modified) >= since_aware]

    def fetch_document(self, reference: DocumentReference) -> RawDocument:
        with self._lock:
            raw = self._staged.get(reference.document_id)
        if raw is None:
            raise FileNotFoundError(
                f"document not staged for fetch: {reference.document_id!r}"
            )
        return raw

    def get_source_id(self) -> str:
        return self._source_id


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
