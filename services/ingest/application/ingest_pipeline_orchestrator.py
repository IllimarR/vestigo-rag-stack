"""IngestPipelineOrchestrator — coordinates the change-event → vector-store flow.

Depends exclusively on Protocols from `contracts`; swapping any stage is
a composition-root concern. This is the ingest-side counterpart of
`RAGPipelineOrchestrator` and follows the same contract-only dependency
direction.

Flow per `docs/pipeline.md` §Document Lifecycle:
  * ADDED    — fetch → convert → chunk → embed → store; log INGESTED
  * MODIFIED — delete_by_document → fetch → convert → chunk → embed →
               store; log UPDATED
  * DELETED  — delete_by_document; log DELETED
  * Unsupported file type — skip, log SKIPPED with error_message
  * Any other exception — caught, skip-and-log with error_message; the
    pipeline continues with the next event so a single bad document
    cannot stall the batch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from contracts import (
    AuditLogger,
    ChangeEvent,
    ChangeType,
    Chunker,
    ConfigProvider,
    DocumentConverter,
    DocumentReference,
    EmbeddingProvider,
    IngestEventType,
    RawDocument,
    SourceConnector,
    VectorStoreRepository,
)

__all__ = ["IngestPipelineOrchestrator", "IngestResult"]


@dataclass(frozen=True)
class IngestResult:
    """Per-batch summary returned by `process_changes`."""

    ingested: int = 0
    updated: int = 0
    deleted: int = 0
    skipped: int = 0
    failed: int = 0


class IngestPipelineOrchestrator:
    """Applies a batch of `ChangeEvent`s to the vector store."""

    def __init__(
        self,
        *,
        source_connector: SourceConnector,
        document_converter: DocumentConverter,
        chunker: Chunker,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStoreRepository,
        config_provider: ConfigProvider,
        audit_logger: AuditLogger,
    ) -> None:
        self._source_connector = source_connector
        self._document_converter = document_converter
        self._chunker = chunker
        self._embedding_provider = embedding_provider
        self._vector_store = vector_store
        self._config_provider = config_provider
        self._audit_logger = audit_logger

    def process_changes(
        self,
        events: list[ChangeEvent],
        *,
        collection: str,
    ) -> IngestResult:
        chunk_config = self._config_provider.get_chunking_config()
        supported = {ext.lower().lstrip(".") for ext in self._document_converter.supported_types()}

        counts = {"ingested": 0, "updated": 0, "deleted": 0, "skipped": 0, "failed": 0}

        for event in events:
            ref = event.reference
            try:
                if event.change_type is ChangeType.DELETED:
                    self._vector_store.delete_by_document(ref.document_id, collection)
                    self._log(ref, IngestEventType.DELETED, chunk_count=0)
                    counts["deleted"] += 1
                    continue

                raw = self._fetch(ref)
                file_type = raw.file_type.lower().lstrip(".")
                if file_type not in supported:
                    self._log(
                        ref,
                        IngestEventType.SKIPPED,
                        chunk_count=0,
                        error_message=f"unsupported file_type={raw.file_type!r}",
                    )
                    counts["skipped"] += 1
                    continue

                converted = self._document_converter.convert(raw)
                chunks = self._chunker.chunk(converted.markdown, ref, chunk_config)

                if not chunks:
                    self._log(
                        ref,
                        IngestEventType.SKIPPED,
                        chunk_count=0,
                        error_message="converter produced empty Markdown",
                    )
                    counts["skipped"] += 1
                    continue

                embeddings = self._embedding_provider.embed([chunk.text for chunk in chunks])
                items = list(zip(chunks, embeddings, strict=True))

                if event.change_type is ChangeType.MODIFIED:
                    self._vector_store.delete_by_document(ref.document_id, collection)

                self._vector_store.store_chunks(items, collection)

                if event.change_type is ChangeType.ADDED:
                    self._log(ref, IngestEventType.INGESTED, chunk_count=len(chunks))
                    counts["ingested"] += 1
                else:
                    self._log(ref, IngestEventType.UPDATED, chunk_count=len(chunks))
                    counts["updated"] += 1
            except Exception as exc:  # noqa: BLE001 — orchestrator must keep batch going
                self._log(
                    ref,
                    IngestEventType.SKIPPED,
                    chunk_count=0,
                    error_message=f"{type(exc).__name__}: {exc}",
                )
                counts["failed"] += 1

        return IngestResult(**counts)

    # --- Internals ------------------------------------------------------------

    def _fetch(self, ref: DocumentReference) -> RawDocument:
        return self._source_connector.fetch_document(ref)

    def _log(
        self,
        ref: DocumentReference,
        event_type: IngestEventType,
        *,
        chunk_count: int,
        error_message: str | None = None,
    ) -> None:
        self._audit_logger.log_ingest_event(
            reference=ref,
            event_type=event_type,
            chunk_count=chunk_count,
            timestamp=datetime.now(UTC),
            error_message=error_message,
        )
