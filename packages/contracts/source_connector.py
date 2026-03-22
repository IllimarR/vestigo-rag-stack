"""SourceConnector contract — abstracts the origin of documents."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from contracts.dto import ChangeEvent, DocumentReference, RawDocument

__all__ = ["SourceConnector"]


class SourceConnector(Protocol):
    """Each data source (filesystem, SharePoint, DB, API push) implements this.

    The Ingest API itself is an `ApiPushSourceConnector` implementation, which
    preserves contract isolation at the external HTTP boundary.
    """

    def list_documents(self) -> list[DocumentReference]:
        """Return all known documents from this source."""
        ...

    def detect_changes(self, since: datetime) -> list[ChangeEvent]:
        """Return documents added / modified / deleted since `since`."""
        ...

    def fetch_document(self, reference: DocumentReference) -> RawDocument:
        """Retrieve actual document bytes + metadata for a reference."""
        ...

    def get_source_id(self) -> str:
        """Unique identifier for this source connector instance."""
        ...
