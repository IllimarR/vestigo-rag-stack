# Ingest Service

## Contracts owned

| Contract | Protocol | Implementation |
|---|---|---|
| `SourceConnector` | `contracts.SourceConnector` | `application/filesystem_source_connector.py::FilesystemSourceConnector` (Phase 2 ✓) |
| `DocumentConverter` | `contracts.DocumentConverter` | `application/markitdown_document_converter.py::MarkitdownDocumentConverter` (Phase 2 ✓) |
| `Chunker` | `contracts.Chunker` | `application/recursive_chunker.py::RecursiveChunker` (Phase 2 ✓) |

## Public surface

`api.py::create_app(ingest_orchestrator)` — FastAPI app. Today exposes
only `/health`; the `IngestPipelineOrchestrator` is bound on
`app.state.ingest_orchestrator` so Phase 4 routes can drive a real
ingest run without rewiring the composition root.

The Ingest API is architecturally an `ApiPushSourceConnector` implementation
(see `docs/architecture.md` §1 and §5.1). Documents submitted via HTTP will
be adapted to `ChangeEvent` flow through the `SourceConnector` contract
rather than bypassing it.

## Implementations

### `FilesystemSourceConnector` (Phase 2)

- Recursive scan of a configured root directory. The path relative to the
  root is the `document_id`; mtime drives `last_modified`.
- `detect_changes(since)` diffs the current scan against an in-memory
  snapshot from the previous call and emits ADDED / MODIFIED / DELETED
  `ChangeEvent`s. ADDED and MODIFIED additionally honour the `since`
  watermark (deletions are always reported).
- `fetch_document` reads file bytes; `file_type` is the lower-cased file
  extension (no leading dot).
- `source_id` is constructor-configurable so multiple filesystem
  connectors can coexist in one deployment with distinct ids.
- Composition root dispatches this adapter when `SOURCE_CONNECTORS`
  contains `filesystem`.

### `IngestPipelineOrchestrator` (Phase 2)

- Applies a batch of `ChangeEvent`s to the vector store per
  `docs/pipeline.md` §Document Lifecycle:
  - **ADDED**: fetch → convert → chunk → embed → store, log INGESTED.
  - **MODIFIED**: delete_by_document → fetch → convert → chunk → embed →
    store, log UPDATED. (Delete-then-store is non-atomic — see
    `docs/pipeline.md` §Non-Atomic Update Caveat.)
  - **DELETED**: delete_by_document, log DELETED.
- Skip-and-log behaviour: unsupported file types, empty Markdown, and
  any per-document exception are caught and surfaced as
  `IngestEventType.SKIPPED` audit entries with `error_message`. A bad
  document never stalls the rest of the batch.
- Returns an `IngestResult` (counts of ingested / updated / deleted /
  skipped / failed) so callers can report what happened.
- Depends only on Protocols (`SourceConnector`, `DocumentConverter`,
  `Chunker`, `EmbeddingProvider`, `VectorStoreRepository`,
  `ConfigProvider`, `AuditLogger`); swapping any stage is a composition
  root concern.

### `MarkitdownDocumentConverter` (Phase 2)

- Delegates to Microsoft's `markitdown` library to produce Markdown
  from PDF, DOCX, PPTX, XLSX, HTML, CSV, JSON, XML, plain text, and a
  handful of other office formats.
- Writes `RawDocument.content` to a temporary file because
  `MarkItDown.convert` keys off the extension for some converters;
  the temp file is cleaned up regardless of success.
- `supported_types()` returns a conservative whitelist — anything not
  on it raises `UnsupportedFileTypeError`, which the ingest
  orchestrator catches to skip-and-log the file instead of crashing
  the pipeline.
- Composition root dispatches this adapter when `DOCUMENT_CONVERTER`
  is `markitdown`.

### `RecursiveChunker` (Phase 2)

- Boundary-aware character chunker. Sliding window with lookahead for natural
  separators (paragraph → line → sentence → word) so chunks end at the
  coarsest available break within a ~25 % lookback window of the hard cap.
- `Chunk.start` / `Chunk.end` reference positions in the original Markdown;
  `Chunk.text` is the verbatim slice. Overlap is a natural consequence of
  the start offset, not a text duplication.
- Accepts only `ChunkConfig.method == "recursive"` — the composition root
  dispatches other methods to other implementations.

## Contract compliance

- `tests/test_chunker_contracts.py` — parameterized over every registered
  chunker via `_CHUNKERS`. Current entries: `recursive`.
- `tests/test_source_connector_contracts.py` — parameterized over every
  registered connector via `_CONNECTORS`. Current entries: `filesystem`.
  The harness abstracts write/delete so future connectors (SharePoint,
  DMS, etc.) reuse every assertion.
- `tests/test_document_converter_contracts.py` — parameterized over every
  registered converter via `_CONVERTERS`. Current entries: `markitdown`.
- `tests/test_ingest_pipeline_orchestrator.py` — orchestrator behaviour
  against in-test fake adapters: ADDED/MODIFIED/DELETED flows, batch
  continuity after failure, empty-Markdown skip, unsupported-type skip,
  and accumulated `IngestResult` counts.

## What is still missing

- HTTP routes materializing the `ApiPushSourceConnector` (Phase 4).

## Private packages

`application/`, `domain/`, `infrastructure/` must not be imported across
service boundaries. Enforced by `import-linter`.
