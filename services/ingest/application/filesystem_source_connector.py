"""Filesystem `SourceConnector` — first real implementation of the contract.

Behaviour
---------
* `list_documents()` recursively scans a configured `root` directory and
  returns one `DocumentReference` per regular file. The path relative to
  the root becomes `document_id`; `filename` is the basename;
  `last_modified` is the file's mtime.
* `detect_changes(since)` rescans and diffs against the connector's
  in-memory snapshot of what it saw on the previous call:
    - ADDED    — path in current scan, not in prior snapshot, mtime ≥ since
    - MODIFIED — path in both, mtime changed, mtime ≥ since
    - DELETED  — path in prior snapshot, missing from current scan
  Snapshot is updated at the end of the call. First call after
  construction treats every file as new (subject to the `since` filter).
* `fetch_document(reference)` reads file bytes; `file_type` is taken from
  the lower-cased extension (no leading dot). Missing files raise
  `FileNotFoundError`.
* `get_source_id()` returns the configured source id (default
  ``"filesystem"``) so multiple filesystem connectors can coexist per
  deployment by passing distinct ids.

Selection
---------
Infrastructure-level contract — composition root dispatches on the
`SOURCE_CONNECTORS` env var. This module is bound when that list
contains ``filesystem``.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path

from contracts import ChangeEvent, ChangeType, DocumentReference, RawDocument

__all__ = ["FilesystemSourceConnector"]


class FilesystemSourceConnector:
    """Recursive filesystem scanner emitting change events from mtime diffs."""

    def __init__(self, root: Path | str, source_id: str = "filesystem") -> None:
        self._root = Path(root).resolve()
        self._source_id = source_id
        # doc_id -> (mtime_posix, filename) snapshot from the previous scan.
        self._known: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    # --- Contract surface -----------------------------------------------------

    def list_documents(self) -> list[DocumentReference]:
        with self._lock:
            current = self._scan()
            self._known = {
                doc_id: (mtime, ref.filename) for doc_id, (mtime, ref) in current.items()
            }
            return [ref for _, ref in current.values()]

    def detect_changes(self, since: datetime) -> list[ChangeEvent]:
        since_ts = _as_utc(since).timestamp()
        with self._lock:
            current = self._scan()
            events: list[ChangeEvent] = []

            for doc_id, (mtime, ref) in current.items():
                prior = self._known.get(doc_id)
                if prior is None:
                    if mtime >= since_ts:
                        events.append(ChangeEvent(reference=ref, change_type=ChangeType.ADDED))
                elif mtime != prior[0]:
                    if mtime >= since_ts:
                        events.append(ChangeEvent(reference=ref, change_type=ChangeType.MODIFIED))

            for doc_id, (_, filename) in self._known.items():
                if doc_id not in current:
                    ref = DocumentReference(
                        source_id=self._source_id,
                        document_id=doc_id,
                        filename=filename,
                        last_modified=datetime.now(UTC),
                    )
                    events.append(ChangeEvent(reference=ref, change_type=ChangeType.DELETED))

            self._known = {
                doc_id: (mtime, ref.filename) for doc_id, (mtime, ref) in current.items()
            }
            return events

    def fetch_document(self, reference: DocumentReference) -> RawDocument:
        path = self._root / reference.document_id
        if not path.is_file():
            raise FileNotFoundError(
                f"document not found under {self._root}: {reference.document_id}"
            )
        content = path.read_bytes()
        file_type = path.suffix.lstrip(".").lower()
        return RawDocument(reference=reference, content=content, file_type=file_type)

    def get_source_id(self) -> str:
        return self._source_id

    # --- Internals ------------------------------------------------------------

    def _scan(self) -> dict[str, tuple[float, DocumentReference]]:
        """Walk `self._root` and return doc_id -> (mtime_posix, DocumentReference)."""
        if not self._root.is_dir():
            return {}
        entries: dict[str, tuple[float, DocumentReference]] = {}
        for path in sorted(self._root.rglob("*")):
            if not path.is_file():
                continue
            doc_id = path.relative_to(self._root).as_posix()
            mtime = path.stat().st_mtime
            ref = DocumentReference(
                source_id=self._source_id,
                document_id=doc_id,
                filename=path.name,
                last_modified=datetime.fromtimestamp(mtime, tz=UTC),
            )
            entries[doc_id] = (mtime, ref)
        return entries


def _as_utc(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
