# Vector Store Service

## Contract owned

| Contract | Protocol | Implementations |
|---|---|---|
| `VectorStoreRepository` | `contracts.VectorStoreRepository` | `InMemoryVectorStoreRepository` (Phase 1 ✓) · `ChromaDbVectorStoreRepository` (Phase 2 ✓) |

Sole access point to the vector database. No other module may bypass this
service — enforced by `import-linter` (only `services.vector_store` may
import database drivers).

## Public surface

In-process library. Composition root picks the backend via
`VECTOR_STORE_BACKEND` (`in_memory` | `chromadb`, default `in_memory`).

## Implementations

### `InMemoryVectorStoreRepository`

- `dict[collection, list[(Chunk, embedding)]]` with pure-Python cosine similarity.
- Full `MetadataFilter` op set including `contains`.
- Contract-design validation stub; not for production.

### `ChromaDbVectorStoreRepository`

- Server-backed ChromaDB through `chromadb.HttpClient`.
- Connection configured with `CHROMADB_HOST`, `CHROMADB_PORT`, and
  `CHROMADB_SSL` when `VECTOR_STORE_BACKEND=chromadb`.
- ChromaDB runs as a separate process/container rather than inside the RAG
  service process.
- Each chunk is serialized to JSON and stored in ChromaDB metadata; user metadata
  fields are additionally flattened as top-level metadata for native
  `where`-clause filtering.
- Filter translation: `eq`, `ne`, `in`, `gte`, `lte`, `range` all map to native
  ChromaDB operators. `contains` has no native equivalent for metadata, so it's
  evaluated in Python after over-fetching (best-effort).
- Cosine *similarity* is surfaced as `1 - distance` to match the in-memory
  backend; perfect matches score 1.0.

## Contract compliance

`tests/test_vector_store_contracts.py` is parameterized over every registered
backend and runs 17 tests × N backends. The same test body passes on both
implementations — concrete evidence of the Modularity Proof Criteria in
`docs/architecture.md` §2.

## What is still missing

Phase 5:

- pgvector adapter for a richer swap test (SQL-native metadata, production
  Postgres surface).

Adding a new backend: drop a file under `application/`, re-export from
`api.py`, add the factory to `_BACKENDS` in `test_vector_store_contracts.py`,
and the whole compliance suite runs against it unchanged.
