# Ingest Service

## Contracts owned

| Contract | Protocol | Placeholder |
|---|---|---|
| `SourceConnector` | `contracts.SourceConnector` | `application/placeholders.py::NotImplementedSourceConnector` |
| `DocumentConverter` | `contracts.DocumentConverter` | `application/placeholders.py::NotImplementedDocumentConverter` |
| `Chunker` | `contracts.Chunker` | `application/placeholders.py::NotImplementedChunker` |

## Public surface

`api.py::create_app()` — FastAPI app. Phase 1 exposes only `/health`.

The Ingest API is architecturally an `ApiPushSourceConnector` implementation
(see `docs/architecture.md` §1 and §5.1). Documents submitted via HTTP will
be adapted to `ChangeEvent` flow through the `SourceConnector` contract rather
than bypassing it.

## Phase 1 status — what is missing

- Concrete `SourceConnector` implementation (filesystem watcher in Phase 2).
- Concrete `DocumentConverter` (Pandoc-based or similar, Phase 2).
- Concrete `Chunker` (recursive / semantic, Phase 2).
- Document lifecycle handler coordinating convert → chunk → embed → store
  via the contracts in `application/`. Phase 2.
- HTTP routes that materialize the `ApiPushSourceConnector`. Phase 4.

## Private packages

`application/`, `domain/`, `infrastructure/` are not to be imported from
other services. Enforced by `import-linter`.
