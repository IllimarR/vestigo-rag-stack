# Ingest Service

## Contracts owned

| Contract | Protocol | Implementation |
|---|---|---|
| `SourceConnector` | `contracts.SourceConnector` | `application/filesystem_source_connector.py::FilesystemSourceConnector` (Phase 2 ✓) |
| `DocumentConverter` | `contracts.DocumentConverter` | `application/placeholders.py::NotImplementedDocumentConverter` |
| `Chunker` | `contracts.Chunker` | `application/recursive_chunker.py::RecursiveChunker` (Phase 2 ✓) |

## Public surface

`api.py::create_app()` — FastAPI app. Phase 1 exposes only `/health`.

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

## Phase 2 status — what is still missing

- Concrete `DocumentConverter` (e.g. markitdown, Pandoc).
- Ingest orchestrator wiring `SourceConnector.detect_changes → convert →
  chunk → embed → store`.
- Skip-and-log for unsupported file types.
- HTTP routes materializing the `ApiPushSourceConnector` (Phase 4).

## Private packages

`application/`, `domain/`, `infrastructure/` must not be imported across
service boundaries. Enforced by `import-linter`.
