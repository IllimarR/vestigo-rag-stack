# Config Service

## Contract owned

| Contract | Protocol | Placeholder |
|---|---|---|
| `ConfigProvider` | `contracts.ConfigProvider` | `application/placeholders.py::NotImplementedConfigProvider` |

## Scope reminder

`ConfigProvider` owns **application-level** configuration only — embedding,
reranking, generation, chunking, prompt template, default collection.
Infrastructure bindings (which backend to instantiate) live in `.env` and are
read by the composition root, not by this service.

## Public surface

In-process library.

## Phase 1 status — what is missing

- File-based `ConfigProvider` reading YAML/JSON (Phase 1 exit criterion in
  `docs/phases.md`, but out of scope for this framework-only task).
- Database-backed `ConfigProvider` (Phase 4, replaces the file-based stub;
  migration: seed the database from the existing config file on first run).

**Config changes take effect on the next pipeline run** (see `docs/contracts.md`
§9). Running jobs continue with the previous configuration.
