import { useCallback, useEffect, useMemo, useState } from "react";
import { audit, ApiError } from "../api/client";
import type { AuditQueryParams } from "../api/types";

// Audit log viewer.
//
// The audit backend returns whatever JSON shape `query_logs` produced —
// `query`, `ingest_event`, and `admin_event` rows are all valid. Rather
// than dump the raw payload like a debug dashboard, this view promotes
// the fields the operator cares about (timestamp, type, status,
// api_key_id, query, tokens) into structured columns and tucks the
// rest into a click-to-expand row.
//
// Filters:
//   - Type: dropdown driving the backend `type` query param.
//   - API key id / dates: text input driving the matching query params.
//   - Status: client-side multi-select. The backend filter accepts a
//     single value, but checkboxes naturally encode multi-select, so
//     we fetch with no status filter and narrow the visible rows
//     against the ticked statuses in-memory.

type AuditRow = Record<string, unknown> & {
  type?: string;
  timestamp?: string;
  api_key_id?: string;
  status?: string;
  query?: string;
  response_text?: string | null;
  error_message?: string | null;
  usage?: { prompt_tokens?: number; completion_tokens?: number } | null;
  // ingest_event fields
  event_type?: string;
  reference?: { document_id?: string; filename?: string } | null;
  chunk_count?: number;
  // admin_event fields
  action?: string;
  actor?: string;
};

const TYPE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "All types" },
  { value: "query", label: "query" },
  { value: "ingest_event", label: "ingest_event" },
  { value: "admin_event", label: "admin_event" },
];

const STATUS_OPTIONS = ["success", "partial", "failed"] as const;
type StatusOption = (typeof STATUS_OPTIONS)[number];

export function AuditView(): JSX.Element {
  const [filters, setFilters] = useState<AuditQueryParams>({});
  const [statusSelection, setStatusSelection] = useState<Set<StatusOption>>(
    new Set(),
  );
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState<number | null>(null);

  const run = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const response = await audit.query(filters);
      setRows(response.results as AuditRow[]);
      setExpanded(null);
    } catch (e) {
      setError(formatError(e));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void run();
    // initial fetch only; subsequent runs go through Apply
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateFilter = (key: keyof AuditQueryParams, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }));
  };

  const toggleStatus = (status: StatusOption) => {
    setStatusSelection((prev) => {
      const next = new Set(prev);
      if (next.has(status)) next.delete(status);
      else next.add(status);
      return next;
    });
  };

  const visibleRows = useMemo(() => {
    if (statusSelection.size === 0) return rows;
    // Status pills filter `query` rows only. Ingest and admin events have
    // their own status semantics (event_type / action) so leaving them
    // visible matches the operator's intent: "show me the query results
    // with these statuses", not "hide every non-query event".
    return rows.filter((row) => {
      if (row.type !== "query") return true;
      return (
        typeof row.status === "string" &&
        statusSelection.has(row.status as StatusOption)
      );
    });
  }, [rows, statusSelection]);

  return (
    <section>
      <header className="view-header">
        <h2>Audit log</h2>
        <p className="view-subtitle">
          Every query, ingest event, and admin write the backend records — driven by
          the <code className="mono">AuditLogger</code> contract.
        </p>
      </header>

      {error && <div className="error" style={{ marginTop: "0.75rem" }}>{error}</div>}

      <div className="card" style={{ marginTop: "1rem" }}>
        <div className="card__body">
          <div className="audit-filters">
            <div className="field">
              <label htmlFor="audit-type">Type</label>
              <select
                id="audit-type"
                value={filters.type ?? ""}
                onChange={(e) => updateFilter("type", e.target.value)}
              >
                {TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="audit-api-key">API key id</label>
              <input
                id="audit-api-key"
                type="text"
                placeholder="key-…"
                value={filters.api_key_id ?? ""}
                onChange={(e) => updateFilter("api_key_id", e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="audit-from">From (ISO)</label>
              <input
                id="audit-from"
                type="text"
                placeholder="2026-03-01T00:00:00"
                value={filters.date_from ?? ""}
                onChange={(e) => updateFilter("date_from", e.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="audit-to">To (ISO)</label>
              <input
                id="audit-to"
                type="text"
                placeholder="2026-03-31T23:59:59"
                value={filters.date_to ?? ""}
                onChange={(e) => updateFilter("date_to", e.target.value)}
              />
            </div>
            <div className="field field--actions">
              <label>&nbsp;</label>
              <button onClick={() => void run()}>Apply</button>
            </div>
          </div>

          <div className="status-filter">
            <span className="status-filter__label">Status</span>
            {STATUS_OPTIONS.map((status) => {
              const active = statusSelection.has(status);
              return (
                <label
                  key={status}
                  className={`status-toggle status-toggle--${status}${active ? " is-active" : ""}`}
                >
                  <input
                    type="checkbox"
                    checked={active}
                    onChange={() => toggleStatus(status)}
                  />
                  <span>{status}</span>
                </label>
              );
            })}
            {statusSelection.size > 0 && (
              <button
                type="button"
                className="ghost status-filter__clear"
                onClick={() => setStatusSelection(new Set())}
              >
                Clear
              </button>
            )}
          </div>
        </div>

        <div className="card__body card__body--flush">
          <div className="table-wrap">
            <table aria-label="Audit log">
              <thead>
                <tr>
                  <th style={{ width: "12rem" }}>Timestamp</th>
                  <th style={{ width: "7rem" }}>Type</th>
                  <th style={{ width: "6.5rem" }}>Status</th>
                  <th style={{ width: "8rem" }}>API key</th>
                  <th>Details</th>
                  <th style={{ width: "5.5rem", textAlign: "right" }}>Tokens</th>
                  <th style={{ width: "2rem" }}></th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan={7} className="empty-state">Loading…</td>
                  </tr>
                )}
                {!loading && visibleRows.length === 0 && (
                  <tr>
                    <td colSpan={7} className="empty-state">
                      <EmptyIcon />
                      No events match the current filters.
                    </td>
                  </tr>
                )}
                {!loading &&
                  visibleRows.map((row, index) => (
                    <AuditRowView
                      key={index}
                      row={row}
                      isOpen={expanded === index}
                      onToggle={() =>
                        setExpanded((curr) => (curr === index ? null : index))
                      }
                    />
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}

// --- Row + expanded details -----------------------------------------------

function AuditRowView({
  row,
  isOpen,
  onToggle,
}: {
  row: AuditRow;
  isOpen: boolean;
  onToggle: () => void;
}): JSX.Element {
  const promptTokens = row.usage?.prompt_tokens ?? null;
  const completionTokens = row.usage?.completion_tokens ?? null;

  const details = describeEvent(row);

  return (
    <>
      <tr className="audit-row" onClick={onToggle}>
        <td className="mono">{formatTimestamp(String(row.timestamp ?? ""))}</td>
        <td>
          <span className="badge badge--neutral">{String(row.type ?? "—")}</span>
        </td>
        <td><TypeStatusBadge row={row} /></td>
        <td className="mono">
          {row.api_key_id ? (
            String(row.api_key_id)
          ) : (
            <span className="muted">—</span>
          )}
        </td>
        <td>
          <span className="audit-query" title={details.text}>
            {details.text ? details.text : <span className="muted">—</span>}
          </span>
        </td>
        <td className="tokens" style={{ textAlign: "right" }}>
          {promptTokens !== null || completionTokens !== null ? (
            <>
              <span>{promptTokens ?? 0}</span>
              <span className="tokens__sep">→</span>
              <span>{completionTokens ?? 0}</span>
            </>
          ) : (
            <span className="muted">—</span>
          )}
        </td>
        <td>
          <span className={`caret${isOpen ? " is-open" : ""}`}>▶</span>
        </td>
      </tr>
      {isOpen && (
        <tr className="audit-row__details">
          <td colSpan={7}>
            <AuditDetails row={row} />
          </td>
        </tr>
      )}
    </>
  );
}

function describeEvent(row: AuditRow): { text: string } {
  // What goes into the Details column. Per type:
  //   query        → the user's query text
  //   ingest_event → reference.document_id (path-style, more identifying
  //                  than just filename when documents share basenames)
  //   admin_event  → the action string (e.g. "PUT /v1/config/generation")
  if (row.type === "query") return { text: String(row.query ?? "") };
  if (row.type === "ingest_event") {
    const ref = row.reference ?? null;
    const text = ref?.document_id ?? ref?.filename ?? "";
    return { text };
  }
  if (row.type === "admin_event") return { text: String(row.action ?? "") };
  return { text: "" };
}

function AuditDetails({ row }: { row: AuditRow }): JSX.Element {
  const fullJson = useMemo(() => JSON.stringify(row, null, 2), [row]);

  return (
    <dl className="audit-details-grid">
      {row.response_text && (
        <>
          <dt>Response</dt>
          <dd className="mono-block">{String(row.response_text)}</dd>
        </>
      )}
      {row.error_message && (
        <>
          <dt>Error</dt>
          <dd className="mono-block" style={{ color: "var(--c-danger)" }}>
            {String(row.error_message)}
          </dd>
        </>
      )}
      <dt>Raw event</dt>
      <dd className="mono-block">{fullJson}</dd>
    </dl>
  );
}

// --- Bits -----------------------------------------------------------------

function TypeStatusBadge({ row }: { row: AuditRow }): JSX.Element {
  // Status column adapts to event type:
  //   query        → row.status (success / partial / failed)
  //   ingest_event → row.event_type, mapped to a semantic colour
  //   admin_event  → neutral "applied" — the audit logger records
  //                  actions that have already happened
  if (row.type === "query" && row.status) {
    return <span className={queryStatusClass(row.status)}>{row.status}</span>;
  }
  if (row.type === "ingest_event" && row.event_type) {
    return (
      <span className={ingestEventClass(row.event_type)}>
        {row.event_type}
      </span>
    );
  }
  if (row.type === "admin_event") {
    return <span className="badge badge--accent">applied</span>;
  }
  return <span className="muted">—</span>;
}

function queryStatusClass(status: string): string {
  if (status === "success") return "badge badge--success";
  if (status === "failed") return "badge badge--failed";
  if (status === "partial") return "badge badge--partial";
  return "badge badge--neutral";
}

function ingestEventClass(eventType: string): string {
  // Map IngestEventType values to the same colour vocabulary as the
  // query-status palette so the operator can scan the column in one go.
  if (eventType === "ingested") return "badge badge--success";
  if (eventType === "updated") return "badge badge--accent";
  if (eventType === "deleted") return "badge badge--neutral";
  if (eventType === "skipped") return "badge badge--partial";
  if (eventType === "failed") return "badge badge--failed";
  return "badge badge--neutral";
}

function formatTimestamp(iso: string): string {
  if (!iso) return "";
  // Render as `YYYY-MM-DD HH:MM:SS` for thesis-screenshot clarity; drop
  // the trailing fractional seconds and timezone so the column doesn't
  // overflow. The expanded view still shows the full raw timestamp.
  return iso.replace("T", " ").replace(/\..*$/, "");
}

function EmptyIcon(): JSX.Element {
  return (
    <svg
      className="empty-state__icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      aria-hidden="true"
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M9 7h6m-6 4h6m-6 4h3M5 4h14a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z" />
    </svg>
  );
}

function formatError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 401) {
      return "Admin key missing or rejected. Set it in the bar above.";
    }
    return `${e.message}: ${JSON.stringify(e.detail)}`;
  }
  return String(e);
}
