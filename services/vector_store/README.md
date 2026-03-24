# Vector Store Service

## Contract owned

| Contract | Protocol | Implementation |
|---|---|---|
| `VectorStoreRepository` | `contracts.VectorStoreRepository` | `application/in_memory_vector_store.py::InMemoryVectorStoreRepository` (Phase 1 ✓) |

This service owns the **sole access point** to the vector database. No other
module may bypass it — enforced by `import-linter` (no direct imports of
database drivers outside this service).

## Public surface

In-process library; no HTTP boundary. The composition root binds a concrete
implementation and passes it to consumers.

## Phase 1 status

- ✓ `InMemoryVectorStoreRepository` — `dict[collection, list[(Chunk,
  embedding)]]` with cosine-similarity retrieval in pure Python.
  Thread-safe (one lock per store). Supports all nine contract methods
  including `MetadataFilter` evaluation (eq/ne/in/contains/gte/lte/range).

**Purpose of the in-memory impl**: validates that the `VectorStoreRepository`
contract isn't accidentally coupled to any specific database's semantics
before the real backend is wired up (`docs/phases.md` Phase 1 early
contract validation). Also doubles as thesis evidence for the Modularity
Proof Criteria in `docs/architecture.md` §2 — two radically different
backends (in-memory ↔ ChromaDB) swappable with zero consumer changes.

## What is still missing

Phase 2:

- ChromaDB adapter (primary real backend).
- pgvector adapter (swap-test evidence).
- Metadata filter translation layer per backend.
