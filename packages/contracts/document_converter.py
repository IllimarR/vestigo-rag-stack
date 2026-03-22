"""DocumentConverter contract — converts raw documents to Markdown."""

from __future__ import annotations

from typing import Protocol

from contracts.dto import ConvertedDocument, RawDocument

__all__ = ["DocumentConverter"]


class DocumentConverter(Protocol):
    """Converts a `RawDocument` into a `ConvertedDocument` whose body is Markdown.

    Markdown is the canonical intermediate format; all chunking and embedding
    downstream operates on Markdown regardless of original file type.
    """

    def convert(self, document: RawDocument) -> ConvertedDocument:
        """Convert document content to Markdown."""
        ...

    def supported_types(self) -> list[str]:
        """File types (extensions or MIME types) this converter handles."""
        ...
