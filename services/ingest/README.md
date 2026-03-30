# Ingest Service

## Contracts owned

| Contract | Protocol | Implementation |
|---|---|---|
| `SourceConnector` | `contracts.SourceConnector` | `application/filesystem_source_connector.py::FilesystemSourceConnector` (Phase 2 ✓), `application/api_push_source_connector.py::ApiPushSourceConnector` (Phase 4 ✓) |
| `DocumentConverter` | `contracts.DocumentConverter` | `application/markitdown_document_converter.py::MarkitdownDocumentConverter` (Phase 2 ✓) |
| `Chunker` | `contracts.Chunker` | `application/recursive_chunker.py::RecursiveChunker` (Phase 2 ✓), `application/fixed_size_chunker.py::FixedSizeChunker` (Phase 5 ✓) |

## Public surface

`api.py::create_app(ingest_orchestrator, source_connector, config_provider)`
— FastAPI app on port 8002.

| Route | Method | Purpose |
|---|---|---|
| `/health` | GET | Liveness probe |
| `/v1/documents` | POST | Push a single document (ADDED / MODIFIED / DELETED) |
| `/v1/documents/batch` | POST | Push an array of documents in one request |

Push routes only function when `SOURCE_CONNECTORS=api`; pushing to a
filesystem-backed deployment returns `409`. Bearer auth via the
`INGEST_API_KEY` env variable; empty env = dev-mode unauthenticated.

The Ingest API is architecturally an `ApiPushSourceConnector`
implementation (see `docs/architecture.md` §1 and §5.1). Documents
submitted via HTTP are staged on the connector, drained as standard
`ChangeEvent`s, and flow through the same `IngestPipelineOrchestrator`
the filesystem connector does — preserving contract isolation at the
external boundary.

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

### `ApiPushSourceConnector` (Phase 4)

- In-memory push connector. The Ingest API routes call
  `push_document(...)` or `push_deletion(...)`, which stage the
  document and queue a `ChangeEvent`. `detect_changes(...)` drains the
  queue; `fetch_document(...)` returns the staged bytes.
- ADDED vs MODIFIED is decided by whether `document_id` has been seen
  before; callers may force MODIFIED in the route body.
- `drop(document_id)` releases the staged bytes after the orchestrator
  has finished. The Phase 4 routes always drop after processing so
  memory does not accumulate.
- Composition root dispatches this adapter when `SOURCE_CONNECTORS=api`.
  Source id is configurable via `API_PUSH_SOURCE_ID` (default `api`).

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

### `FixedSizeChunker` (Phase 5)

- The simplest possible chunker: pure sliding window with stride
  `size - overlap` and no boundary heuristics. Cuts mid-word if that's
  where the window ends.
- Same `Chunk.start` / `Chunk.end` / verbatim-slice invariant as the
  recursive chunker, so downstream stages can't tell which backend
  produced a chunk.
- Exists for the Phase 5 modularity proof: it makes the
  `ChunkConfig.method` dispatch story visually obvious by parking the
  two chunkers side by side. Same orchestrator, same config DTO,
  different behaviour driven entirely by one string.
- Composition root dispatches this adapter when
  `ChunkConfig.method == "fixed_size"`.

## Contract compliance

- `tests/test_chunker_contracts.py` — parameterized over every registered
  chunker via `_CHUNKERS`. Current entries: `recursive`, `fixed_size`.
  The same 12 expectations (empty input, monotonic ordering, full
  coverage, overlap, config validation, method dispatch, ...) run
  against both backends.
- `tests/test_source_connector_contracts.py` — parameterized over every
  registered connector via `_CONNECTORS`. Current entries: `filesystem`,
  `api_push`. The harness abstracts write/delete so future connectors
  (SharePoint, DMS, etc.) reuse every assertion.
- `tests/test_ingest_api_routes.py` — HTTP-level tests covering the
  push routes' validation, auth, batch shape, and the 409 fail-loud
  guard when the configured connector backend isn't `api`.
- `tests/test_document_converter_contracts.py` — parameterized over every
  registered converter via `_CONVERTERS`. Current entries: `markitdown`.
- `tests/test_ingest_pipeline_orchestrator.py` — orchestrator behaviour
  against in-test fake adapters: ADDED/MODIFIED/DELETED flows, batch
  continuity after failure, empty-Markdown skip, unsupported-type skip,
  and accumulated `IngestResult` counts.

## What is still missing

- Multi-source orchestration (running filesystem + api connectors in
  the same deployment) — today `SOURCE_CONNECTORS` picks one. A
  composing wrapper that routes `fetch_document` by `source_id` is the
  natural follow-up.

## Private packages

`application/`, `domain/`, `infrastructure/` must not be imported across
service boundaries. Enforced by `import-linter`.
