"""Contract compliance suite for every registered `DocumentConverter`.

Add a new converter by appending its factory to `_CONVERTERS`. The
suite then runs the full body against it — no per-backend assertions
should be necessary, the same Markdown-output expectations apply
regardless of how the conversion is implemented under the hood.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest
from contracts import DocumentConverter, DocumentReference, RawDocument

from services.ingest.application.markitdown_document_converter import (
    CONVERTER_ID as MARKITDOWN_CONVERTER_ID,
)
from services.ingest.application.markitdown_document_converter import (
    MarkitdownDocumentConverter,
    UnsupportedFileTypeError,
)

_ConverterFactory = Callable[[], DocumentConverter]

_CONVERTERS: dict[str, _ConverterFactory] = {
    "markitdown": MarkitdownDocumentConverter,
}


@pytest.fixture(params=list(_CONVERTERS))
def converter(request: pytest.FixtureRequest) -> DocumentConverter:
    return _CONVERTERS[request.param]()


def _raw(content: bytes, file_type: str, *, document_id: str = "doc") -> RawDocument:
    ref = DocumentReference(
        source_id="test",
        document_id=document_id,
        filename=f"{document_id}.{file_type}",
        last_modified=datetime(2026, 3, 26, tzinfo=UTC),
    )
    return RawDocument(reference=ref, content=content, file_type=file_type)


def test_supported_types_is_non_empty(converter: DocumentConverter) -> None:
    types = converter.supported_types()
    assert isinstance(types, list)
    assert len(types) > 0
    assert all(isinstance(t, str) and t for t in types)


def test_plain_text_round_trips(converter: DocumentConverter) -> None:
    raw = _raw(b"hello world\n", "txt")
    result = converter.convert(raw)

    assert "hello world" in result.markdown
    assert result.reference == raw.reference


def test_markdown_round_trips(converter: DocumentConverter) -> None:
    content = b"# Heading\n\nA paragraph with **bold** text.\n"
    raw = _raw(content, "md")

    result = converter.convert(raw)

    assert "Heading" in result.markdown
    assert "bold" in result.markdown


def test_html_is_converted_to_markdown_structure(converter: DocumentConverter) -> None:
    html = (
        b"<html><body>"
        b"<h1>Title</h1>"
        b"<p>Hello <strong>world</strong>.</p>"
        b"</body></html>"
    )
    raw = _raw(html, "html")

    result = converter.convert(raw)

    assert "Title" in result.markdown
    assert "world" in result.markdown
    # Heading should produce a Markdown header (#) somewhere.
    assert "#" in result.markdown


def test_csv_produces_table(converter: DocumentConverter) -> None:
    raw = _raw(b"name,score\nalice,10\nbob,20\n", "csv")

    result = converter.convert(raw)

    assert "alice" in result.markdown
    assert "bob" in result.markdown


def test_json_is_converted(converter: DocumentConverter) -> None:
    raw = _raw(b'{"name": "alice", "score": 10}', "json")

    result = converter.convert(raw)

    assert "alice" in result.markdown


def test_unsupported_type_raises(converter: DocumentConverter) -> None:
    raw = _raw(b"\x00\x01\x02", "exe")

    with pytest.raises(UnsupportedFileTypeError):
        converter.convert(raw)


def test_result_carries_converter_id(converter: DocumentConverter) -> None:
    raw = _raw(b"hi", "txt")
    result = converter.convert(raw)

    assert result.converter_id
    assert isinstance(result.converter_id, str)


def test_result_reference_is_unchanged(converter: DocumentConverter) -> None:
    raw = _raw(b"hi", "txt", document_id="abc")
    result = converter.convert(raw)

    assert result.reference == raw.reference


def test_uppercase_extension_is_accepted(converter: DocumentConverter) -> None:
    raw = _raw(b"hi", "TXT")
    result = converter.convert(raw)

    assert "hi" in result.markdown


def test_markitdown_converter_id_is_stable() -> None:
    """Implementation-specific: every result from MarkitdownDocumentConverter
    must announce the `markitdown` converter id so audit logs can attribute
    conversions back to a backend.
    """
    converter = MarkitdownDocumentConverter()
    result = converter.convert(_raw(b"hi", "txt"))
    assert result.converter_id == MARKITDOWN_CONVERTER_ID
