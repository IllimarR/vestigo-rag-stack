# Ingest Service

## Contracts owned

| Contract | Protocol | Implementation |
|---|---|---|
| `SourceConnector` | `contracts.SourceConnector` | `application/placeholders.py::NotImplementedSourceConnector` |
| `DocumentConverter` | `contracts.DocumentConverter` | `application/placeholders.py::NotImplementedDocumentConverter` |
| `Chunker` | `contracts.Chunker` | `application/recursive_chunker.py::RecursiveChunker` (Phase 2 ✓) |

## Public surface

`api.py::create_app()` — FastAPI app. Phase 1 exposes only `/health`.

The Ingest API is architecturally an `ApiPushSourceConnector` implementation
(see `docs/architecture.md` §1 and §5.1). Documents submitted via HTTP will
be adapted to `ChangeEvent` flow through the `SourceConnector` contract
rather than bypassing it.

## Implementations

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

`tests/test_chunker_contracts.py` — parameterized over every registered
chunker. Current backends: `recursive`. A second method (`semantic`,
markdown-heading-aware, …) plugs in by adding the factory to `_CHUNKERS`.

## Phase 2 status — what is still missing

- Concrete `SourceConnector` implementation (filesystem watcher).
- Concrete `DocumentConverter` (e.g. markitdown, Pandoc).
- Ingest orchestrator wiring `SourceConnector.detect_changes → convert →
  chunk → embed → store`.
- Skip-and-log for unsupported file types.
- HTTP routes materializing the `ApiPushSourceConnector` (Phase 4).

## Private packages

`application/`, `domain/`, `infrastructure/` must not be imported across
service boundaries. Enforced by `import-linter`.
