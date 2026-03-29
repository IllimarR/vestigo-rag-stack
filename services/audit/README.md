# Audit Service

## Contract owned

| Contract | Protocol | Implementation |
|---|---|---|
| `AuditLogger` | `contracts.AuditLogger` | `application/file_audit_logger.py::FileAuditLogger` (Phase 1 ✓), `application/sqlite_audit_logger.py::SqliteAuditLogger` (Phase 4 ✓) |

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

## `SqliteAuditLogger` (`AUDIT_BACKEND=sqlite`)

- Single `audit_events` table on the shared control-plane DB
  (`CONTROL_PLANE_DB_PATH`). Indexed `type`, `timestamp`, `api_key_id`,
  `status`, `event_type` columns + opaque JSON `payload`.
- `query_logs` returns the same row shape as `FileAuditLogger` — file
  and sqlite backends are interchangeable from the Admin API's
  perspective.
- Historical JSONL files are **not** migrated when an operator flips
  `AUDIT_BACKEND=file → sqlite`. The JSONL file remains on disk; the
  sqlite audit table starts empty.

## What is still missing

- Richer query surface exposed through the Admin API.
