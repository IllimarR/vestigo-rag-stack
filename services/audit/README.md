# Audit Service

## Contract owned

| Contract | Protocol | Implementation |
|---|---|---|
| `AuditLogger` | `contracts.AuditLogger` | `application/file_audit_logger.py::FileAuditLogger` (Phase 1 ✓) |

## Public surface

In-process library. No HTTP surface — Admin API calls `query_logs` via the
`AuditLogger` contract passed into its constructor.

## Phase 1 status

- ✓ `FileAuditLogger` — append-only JSONL file at `AUDIT_LOG_FILE`. Each
  event is one JSON object per line with a `type` discriminator
  (`query` / `ingest_event` / `admin_event`). `query_logs` scans the file
  linearly with filter + pagination support — fine for prototype scale
  (hundreds-to-low-thousands of events).

## What is still missing

Phase 4:

- Database-backed `AuditLogger` (replaces the file-based stub; historical
  file-based logs are **not** migrated — acceptable for prototype).
- Richer query surface exposed through the Admin API.
