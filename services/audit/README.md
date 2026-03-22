# Audit Service

## Contract owned

| Contract | Protocol | Placeholder |
|---|---|---|
| `AuditLogger` | `contracts.AuditLogger` | `application/placeholders.py::NotImplementedAuditLogger` |

## Public surface

In-process library. No `api.py` yet — a future file-based adapter and a
database-backed adapter will live under `application/` and be bound in the
composition root.

## Phase 1 status — what is missing

- File-based `AuditLogger` (Phase 1 exit criterion in `docs/phases.md`, but
  out of scope for this framework-only task).
- Database-backed `AuditLogger` (Phase 4).
- Query endpoints surfaced via the Admin API.
