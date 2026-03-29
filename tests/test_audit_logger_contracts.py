"""Contract-compliance suite for every `AuditLogger` implementation.

One test body, one contract, N backends. The shape `query_logs`
returns is the same for both file and sqlite — assertions inspect
exactly that observable surface, so a new backend (Postgres, OpenSearch,
...) plugs into `_LOGGERS` and inherits the whole suite.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

import pytest
from contracts import (
    AuditLogger,
    DocumentReference,
    IngestEventType,
    QueryStatus,
    TokenUsage,
)

from services.audit.application.file_audit_logger import FileAuditLogger
from services.audit.application.sqlite_audit_logger import SqliteAuditLogger

LoggerFactory = Callable[[Path], AuditLogger]


def _file_backend(tmp_path: Path) -> AuditLogger:
    return FileAuditLogger(tmp_path / "audit.log")


def _sqlite_backend(tmp_path: Path) -> AuditLogger:
    return SqliteAuditLogger.from_path(tmp_path / "control_plane.db")


_LOGGERS: dict[str, LoggerFactory] = {
    "file": _file_backend,
    "sqlite": _sqlite_backend,
}


@pytest.fixture(params=sorted(_LOGGERS), ids=sorted(_LOGGERS))
def logger(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[AuditLogger]:
    factory = _LOGGERS[request.param]
    yield factory(tmp_path)


# --- helpers ---------------------------------------------------------------


def _ref(doc_id: str = "1", *, src: str = "fs", at: datetime | None = None) -> DocumentReference:
    return DocumentReference(
        source_id=src,
        document_id=doc_id,
        filename=f"{doc_id}.md",
        last_modified=at or datetime(2026, 4, 25, 10, 0, 0),
    )


_NOW = datetime(2026, 4, 25, 10, 0, 0)
_LATER = datetime(2026, 4, 26, 10, 0, 0)
_USAGE = TokenUsage(prompt_tokens=10, completion_tokens=20)


# --- Write methods produce queryable rows ----------------------------------


def test_log_admin_event_roundtrip(logger: AuditLogger) -> None:
    logger.log_admin_event(action="api_key.create", actor="admin", timestamp=_NOW)
    rows = logger.query_logs(filters={"type": "admin_event"})
    assert len(rows) == 1
    assert rows[0]["action"] == "api_key.create"
    assert rows[0]["actor"] == "admin"


def test_log_ingest_event_roundtrip(logger: AuditLogger) -> None:
    logger.log_ingest_event(
        reference=_ref("doc-1"),
        event_type=IngestEventType.INGESTED,
        chunk_count=7,
        timestamp=_NOW,
    )
    rows = logger.query_logs(filters={"type": "ingest_event"})
    assert len(rows) == 1
    assert rows[0]["event_type"] == "ingested"
    assert rows[0]["chunk_count"] == 7
    assert rows[0]["reference"]["document_id"] == "doc-1"


def test_log_query_roundtrip(logger: AuditLogger) -> None:
    logger.log_query(
        query="what is X?",
        retrieved=[],
        response_text="X is...",
        usage=_USAGE,
        timestamp=_NOW,
        api_key_id="key-abc",
        status=QueryStatus.SUCCESS,
    )
    rows = logger.query_logs(filters={"type": "query"})
    assert len(rows) == 1
    row = rows[0]
    assert row["api_key_id"] == "key-abc"
    assert row["status"] == "success"
    assert row["query"] == "what is X?"
    assert row["response_text"] == "X is..."
    assert row["usage"]["prompt_tokens"] == 10


def test_query_logs_returns_all_when_filters_empty(logger: AuditLogger) -> None:
    logger.log_admin_event(action="a", actor="u", timestamp=_NOW)
    logger.log_ingest_event(
        reference=_ref(),
        event_type=IngestEventType.DELETED,
        chunk_count=0,
        timestamp=_NOW,
    )
    logger.log_query(
        query="q",
        retrieved=[],
        response_text="r",
        usage=_USAGE,
        timestamp=_NOW,
        api_key_id="k",
        status=QueryStatus.SUCCESS,
    )
    rows = logger.query_logs(filters={})
    assert len(rows) == 3


# --- Filters --------------------------------------------------------------


def test_filter_by_api_key_id(logger: AuditLogger) -> None:
    logger.log_query(
        query="a",
        retrieved=[],
        response_text="",
        usage=_USAGE,
        timestamp=_NOW,
        api_key_id="key-A",
        status=QueryStatus.SUCCESS,
    )
    logger.log_query(
        query="b",
        retrieved=[],
        response_text="",
        usage=_USAGE,
        timestamp=_NOW,
        api_key_id="key-B",
        status=QueryStatus.SUCCESS,
    )
    rows = logger.query_logs(filters={"api_key_id": "key-A"})
    assert len(rows) == 1
    assert rows[0]["api_key_id"] == "key-A"


def test_filter_by_status(logger: AuditLogger) -> None:
    logger.log_query(
        query="ok",
        retrieved=[],
        response_text="",
        usage=_USAGE,
        timestamp=_NOW,
        api_key_id="k",
        status=QueryStatus.SUCCESS,
    )
    logger.log_query(
        query="bad",
        retrieved=[],
        response_text="",
        usage=_USAGE,
        timestamp=_NOW,
        api_key_id="k",
        status=QueryStatus.FAILED,
        error_message="boom",
    )
    rows = logger.query_logs(filters={"status": "failed"})
    assert len(rows) == 1
    assert rows[0]["status"] == "failed"


def test_filter_by_event_type_via_type_key(logger: AuditLogger) -> None:
    """`type=ingested` looks up the inner ingest variant — same fallback
    `FileAuditLogger` provides for operator convenience."""

    logger.log_ingest_event(
        reference=_ref("a"),
        event_type=IngestEventType.INGESTED,
        chunk_count=1,
        timestamp=_NOW,
    )
    logger.log_ingest_event(
        reference=_ref("b"),
        event_type=IngestEventType.DELETED,
        chunk_count=0,
        timestamp=_NOW,
    )
    rows = logger.query_logs(filters={"type": "deleted"})
    assert len(rows) == 1
    assert rows[0]["event_type"] == "deleted"


def test_filter_by_date_range(logger: AuditLogger) -> None:
    logger.log_admin_event(action="early", actor="u", timestamp=_NOW)
    logger.log_admin_event(action="late", actor="u", timestamp=_LATER)
    rows = logger.query_logs(filters={"date_from": _LATER.isoformat()})
    assert len(rows) == 1
    assert rows[0]["action"] == "late"


def test_unknown_filter_keys_are_ignored(logger: AuditLogger) -> None:
    """Both backends silently drop filters they don't recognise — prototype-scope
    forgiveness so admins can pass through query strings without us
    erroring on every new field they add."""

    logger.log_admin_event(action="a", actor="u", timestamp=_NOW)
    rows = logger.query_logs(filters={"this_is_made_up": 42})
    assert len(rows) == 1


# --- Pagination -----------------------------------------------------------


def test_offset_and_limit(logger: AuditLogger) -> None:
    for i in range(5):
        logger.log_admin_event(action=f"a{i}", actor="u", timestamp=_NOW)

    page1 = logger.query_logs(filters={}, limit=2)
    assert len(page1) == 2
    page2 = logger.query_logs(filters={}, offset=2, limit=2)
    assert len(page2) == 2
    assert page1 != page2

    everything = logger.query_logs(filters={}, limit=100)
    assert len(everything) == 5
