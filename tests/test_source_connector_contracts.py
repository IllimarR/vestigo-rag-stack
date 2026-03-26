"""Contract compliance suite for every registered `SourceConnector`.

New connector? Add a factory to `_CONNECTORS` that yields a
`(connector, harness)` tuple. The harness drives backend-specific
write/delete operations so the same test bodies cover every backend
without leaking filesystem assumptions.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from contracts import ChangeType, SourceConnector

from services.ingest.application.filesystem_source_connector import (
    FilesystemSourceConnector,
)


@dataclass
class _Harness:
    """Backend-agnostic helpers used by the parameterized test bodies."""

    write: Callable[[str, bytes], None]
    delete: Callable[[str], None]


Fixture = tuple[SourceConnector, _Harness]
_ConnectorFactory = Callable[[Path], Fixture]


def _filesystem_factory(tmp_path: Path) -> tuple[SourceConnector, _Harness]:
    connector = FilesystemSourceConnector(root=tmp_path, source_id="filesystem")

    def write(doc_id: str, content: bytes) -> None:
        path = tmp_path / doc_id
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def delete(doc_id: str) -> None:
        (tmp_path / doc_id).unlink()

    return connector, _Harness(write=write, delete=delete)


_CONNECTORS: dict[str, _ConnectorFactory] = {
    "filesystem": _filesystem_factory,
}


@pytest.fixture(params=list(_CONNECTORS))
def fixture(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Fixture]:
    factory = _CONNECTORS[request.param]
    yield factory(tmp_path)


def _bump_mtime(harness: _Harness, doc_id: str, content: bytes) -> None:
    """Rewrite a file so its mtime advances past 1-second filesystem resolution."""
    time.sleep(1.05)
    harness.write(doc_id, content)


def test_get_source_id_is_stable(fixture: Fixture) -> None:
    connector, _ = fixture
    assert connector.get_source_id()
    assert connector.get_source_id() == connector.get_source_id()


def test_empty_source_has_no_documents(fixture: Fixture) -> None:
    connector, _ = fixture
    assert connector.list_documents() == []


def test_list_documents_returns_written_files(fixture: Fixture) -> None:
    connector, harness = fixture
    harness.write("alpha.md", b"# alpha\n")
    harness.write("beta.txt", b"plain\n")

    refs = connector.list_documents()
    doc_ids = {ref.document_id for ref in refs}

    assert doc_ids == {"alpha.md", "beta.txt"}
    assert all(ref.source_id == connector.get_source_id() for ref in refs)
    assert all(ref.filename == ref.document_id.split("/")[-1] for ref in refs)


def test_detect_changes_first_call_emits_added(fixture: Fixture) -> None:
    connector, harness = fixture
    harness.write("a.md", b"hi")
    harness.write("nested/b.md", b"bye")

    events = connector.detect_changes(_distant_past())

    types = {(e.reference.document_id, e.change_type) for e in events}
    assert types == {("a.md", ChangeType.ADDED), ("nested/b.md", ChangeType.ADDED)}


def test_detect_changes_idempotent_when_no_changes(fixture: Fixture) -> None:
    connector, harness = fixture
    harness.write("a.md", b"hi")
    connector.detect_changes(_distant_past())

    assert connector.detect_changes(_distant_past()) == []


def test_detect_changes_emits_modified_on_rewrite(fixture: Fixture) -> None:
    connector, harness = fixture
    harness.write("a.md", b"v1")
    connector.detect_changes(_distant_past())

    _bump_mtime(harness, "a.md", b"v2")
    events = connector.detect_changes(_distant_past())

    assert len(events) == 1
    assert events[0].reference.document_id == "a.md"
    assert events[0].change_type == ChangeType.MODIFIED


def test_detect_changes_emits_deleted(fixture: Fixture) -> None:
    connector, harness = fixture
    harness.write("a.md", b"hi")
    connector.detect_changes(_distant_past())

    harness.delete("a.md")
    events = connector.detect_changes(_distant_past())

    assert len(events) == 1
    assert events[0].reference.document_id == "a.md"
    assert events[0].change_type == ChangeType.DELETED


def test_detect_changes_picks_up_new_file_after_first_scan(
    fixture: Fixture,
) -> None:
    connector, harness = fixture
    harness.write("a.md", b"hi")
    connector.detect_changes(_distant_past())

    harness.write("b.md", b"new")
    events = connector.detect_changes(_distant_past())

    types = {(e.reference.document_id, e.change_type) for e in events}
    assert types == {("b.md", ChangeType.ADDED)}


def test_detect_changes_since_filter_skips_older_files(
    fixture: Fixture,
) -> None:
    connector, harness = fixture
    harness.write("old.md", b"hi")

    future = datetime.now(UTC) + timedelta(hours=1)
    assert connector.detect_changes(future) == []


def test_fetch_document_round_trips_bytes(fixture: Fixture) -> None:
    connector, harness = fixture
    payload = "üäö unicode and bytes".encode()
    harness.write("doc.md", payload)

    ref = connector.list_documents()[0]
    raw = connector.fetch_document(ref)

    assert raw.content == payload
    assert raw.reference == ref
    assert raw.file_type == "md"


def test_fetch_document_lowercases_file_type(fixture: Fixture) -> None:
    connector, harness = fixture
    harness.write("paper.PDF", b"%PDF-1.4")

    ref = connector.list_documents()[0]
    raw = connector.fetch_document(ref)

    assert raw.file_type == "pdf"


def test_fetch_document_raises_when_missing(fixture: Fixture) -> None:
    connector, harness = fixture
    harness.write("a.md", b"hi")
    ref = connector.list_documents()[0]

    harness.delete("a.md")

    with pytest.raises(FileNotFoundError):
        connector.fetch_document(ref)


def test_two_connector_instances_have_independent_state(tmp_path: Path) -> None:
    """Constructing a second connector against the same root must not share state.

    Filesystem-specific because state lives on the connector instance, not the
    backend.
    """
    (tmp_path / "a.md").write_text("hi")
    first = FilesystemSourceConnector(root=tmp_path)
    second = FilesystemSourceConnector(root=tmp_path)

    first.detect_changes(_distant_past())

    events = second.detect_changes(_distant_past())
    types = {(e.reference.document_id, e.change_type) for e in events}
    assert types == {("a.md", ChangeType.ADDED)}


def _distant_past() -> datetime:
    return datetime(1970, 1, 1, tzinfo=UTC)
