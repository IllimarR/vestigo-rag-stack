# Audit Service

## Contract owned

| Contract | Protocol | Implementation |
|---|---|---|
| `AuditLogger` | `contracts.AuditLogger` | `application/file_audit_logger.py::FileAuditLogger` (Phase 1 ✓) |

## Public surface

In-process library. No HTTP surface — Admin API calls `query_logs` via the
`AuditLogger` contract passed into its constructor.

## `FileAuditLogger`

- ✓ Append-only JSONL file at `AUDIT_LOG_FILE`. Each event is one JSON
  object per line with a `type` discriminator (`query` / `ingest_event`
  / `admin_event`). `query_logs` scans the file linearly with filter +
  pagination support — fine for prototype scale (hundreds-to-low-thousands
  of events).
- The query orchestrator writes one entry per call with status
  `SUCCESS` / `PARTIAL` / `FAILED`; the ingest orchestrator writes one
  per `ChangeEvent` (`INGESTED` / `UPDATED` / `DELETED` / `SKIPPED`).

## What is still missing

Phase 4:

- Database-backed `AuditLogger` (replaces the file-based implementation;
  historical file-based logs are **not** migrated — acceptable for
  prototype).
- Richer query surface exposed through the Admin API.
