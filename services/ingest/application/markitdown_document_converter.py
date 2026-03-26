"""Markitdown-backed `DocumentConverter` — Phase 2 first real implementation.

`markitdown` (Microsoft, MIT) is a pure-Python conversion library that
produces Markdown from a wide range of common office and document
formats. Markdown is the canonical intermediate format the pipeline
chunks and embeds on, so this converter sits between
`SourceConnector.fetch_document` and `Chunker.chunk`.

Behaviour
---------
* `convert(raw)` writes `raw.content` to a temporary file (markitdown's
  stable entrypoint takes a path, and some converters key off the
  extension), runs `MarkItDown.convert`, and returns the produced
  Markdown wrapped in a `ConvertedDocument`. Empty results are
  surfaced as an empty-string body rather than `None`.
* `supported_types()` reports the conservative whitelist below. The
  orchestrator should query this list and skip-and-log unsupported
  files *before* calling `convert`. `convert` still raises
  `UnsupportedFileTypeError` for unknown types as a defensive check.

Selection
---------
Composition root dispatches this adapter when `DOCUMENT_CONVERTER` is
`markitdown`.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from contracts import ConvertedDocument, RawDocument
from markitdown import MarkItDown

__all__ = ["CONVERTER_ID", "MarkitdownDocumentConverter", "UnsupportedFileTypeError"]

CONVERTER_ID = "markitdown"

# Conservative whitelist of extensions markitdown produces sensible Markdown
# for in this prototype. Add a new entry only after verifying the output
# manually — anything not here is skip-and-logged by the orchestrator.
SUPPORTED_EXTENSIONS: tuple[str, ...] = (
    "pdf",
    "docx",
    "pptx",
    "xlsx",
    "html",
    "htm",
    "csv",
    "json",
    "xml",
    "txt",
    "md",
    "markdown",
    "epub",
    "msg",
)


class UnsupportedFileTypeError(ValueError):
    """Raised by `convert` when `RawDocument.file_type` is not in the whitelist."""


class MarkitdownDocumentConverter:
    """`DocumentConverter` that delegates to markitdown."""

    def __init__(self, md: MarkItDown | None = None) -> None:
        self._md = md or MarkItDown()

    def convert(self, document: RawDocument) -> ConvertedDocument:
        ext = _normalise_ext(document.file_type)
        if ext not in SUPPORTED_EXTENSIONS:
            raise UnsupportedFileTypeError(
                f"file_type={document.file_type!r} is not in the markitdown "
                "whitelist. Query `supported_types()` first or add the "
                "extension to SUPPORTED_EXTENSIONS after verifying output."
            )

        with tempfile.NamedTemporaryFile(suffix=f".{ext}", delete=False) as handle:
            handle.write(document.content)
            tmp_path = Path(handle.name)
        try:
            result = self._md.convert(str(tmp_path))
        finally:
            tmp_path.unlink(missing_ok=True)

        return ConvertedDocument(
            reference=document.reference,
            markdown=result.text_content or "",
            converter_id=CONVERTER_ID,
            warnings=(),
        )

    def supported_types(self) -> list[str]:
        return list(SUPPORTED_EXTENSIONS)


def _normalise_ext(raw: str) -> str:
    return raw.lower().lstrip(".")
