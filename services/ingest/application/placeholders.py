"""Placeholder implementations for the three ingest-owned contracts.

Every method raises `NotImplementedError` pointing at which contract still
needs a real implementation. These exist so the composition root compiles
and imports cleanly before any concrete adapter has been written.
"""

from __future__ import annotations

from datetime import datetime

from contracts import (
    ChangeEvent,
    Chunk,
    ChunkConfig,
    ConvertedDocument,
    DocumentReference,
    RawDocument,
)

__all__ = [
    "NotImplementedChunker",
    "NotImplementedDocumentConverter",
    "NotImplementedSourceConnector",
]


def _not_implemented(contract: str) -> NotImplementedError:
    return NotImplementedError(
        f"{contract} is a Phase 1 placeholder. Bind a concrete implementation "
        "in the composition root before invoking this method."
    )


class NotImplementedSourceConnector:
    def list_documents(self) -> list[DocumentReference]:
        raise _not_implemented("SourceConnector")

    def detect_changes(self, since: datetime) -> list[ChangeEvent]:
        raise _not_implemented("SourceConnector")

    def fetch_document(self, reference: DocumentReference) -> RawDocument:
        raise _not_implemented("SourceConnector")

    def get_source_id(self) -> str:
        raise _not_implemented("SourceConnector")


class NotImplementedDocumentConverter:
    def convert(self, document: RawDocument) -> ConvertedDocument:
        raise _not_implemented("DocumentConverter")

    def supported_types(self) -> list[str]:
        raise _not_implemented("DocumentConverter")


class NotImplementedChunker:
    def chunk(
        self,
        markdown: str,
        parent: DocumentReference,
        config: ChunkConfig,
    ) -> list[Chunk]:
        raise _not_implemented("Chunker")
