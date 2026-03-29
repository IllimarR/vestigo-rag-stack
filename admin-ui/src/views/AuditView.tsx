import { useCallback, useEffect, useState } from "react";
import { audit, ApiError } from "../api/client";
import type { AuditQueryParams } from "../api/types";

// Audit log viewer. The filter shape is whatever the backend's
// query_logs accepts: type, api_key_id, status, date_from, date_to,
// offset, limit. Rows render the JSON payload `query_logs` returns
// directly — same shape file and sqlite backends produce.

export function AuditView(): JSX.Element {
  const [filters, setFilters] = useState<AuditQueryParams>({});
  const [rows, setRows] = useState<Array<Record<string, unknown>>>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const run = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const response = await audit.query(filters);
      setRows(response.results);
    } catch (e) {
      setError(formatError(e));
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void run();
    // run once on mount; subsequent runs are explicit via the Apply button
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateFilter = (key: keyof AuditQueryParams, value: string) => {
    setFilters((prev) => ({ ...prev, [key]: value || undefined }));
  };

  return (
    <section>
      <h2>Audit log</h2>
      {error && <div className="error">{error}</div>}

      <div className="row">
        <div>
          <label htmlFor="audit-type">Type</label>
          <input
            id="audit-type"
            type="text"
            placeholder="query / ingest_event / admin_event"
            value={filters.type ?? ""}
            onChange={(e) => updateFilter("type", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="audit-api-key">api_key_id</label>
          <input
            id="audit-api-key"
            type="text"
            value={filters.api_key_id ?? ""}
            onChange={(e) => updateFilter("api_key_id", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="audit-status">Status</label>
          <input
            id="audit-status"
            type="text"
            placeholder="success / partial / failed"
            value={filters.status ?? ""}
            onChange={(e) => updateFilter("status", e.target.value)}
          />
        </div>
      </div>
      <div className="row">
        <div>
          <label htmlFor="audit-from">From (ISO)</label>
          <input
            id="audit-from"
            type="text"
            placeholder="2026-03-01T00:00:00"
            value={filters.date_from ?? ""}
            onChange={(e) => updateFilter("date_from", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="audit-to">To (ISO)</label>
          <input
            id="audit-to"
            type="text"
            placeholder="2026-03-31T23:59:59"
            value={filters.date_to ?? ""}
            onChange={(e) => updateFilter("date_to", e.target.value)}
          />
        </div>
        <div style={{ flex: 0 }}>
          <button onClick={() => void run()}>Apply</button>
        </div>
      </div>

      <table aria-label="Audit log">
        <thead>
          <tr>
            <th>Timestamp</th>
            <th>Type</th>
            <th>Details</th>
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={3}>Loading…</td>
            </tr>
          )}
          {!loading && rows.length === 0 && (
            <tr>
              <td colSpan={3}>No events match the current filters.</td>
            </tr>
          )}
          {rows.map((row, index) => (
            <tr key={index}>
              <td>{String(row.timestamp ?? "")}</td>
              <td>{String(row.type ?? "")}</td>
              <td>
                <pre style={{ margin: 0, fontSize: "0.75rem" }}>
                  {JSON.stringify(row, null, 2)}
                </pre>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
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
