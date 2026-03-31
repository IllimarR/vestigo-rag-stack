import { useCallback, useEffect, useState } from "react";
import { apiKeys, ApiError } from "../api/client";
import type { ApiKeyRecord, CreatedApiKey } from "../api/types";

// API key management: list / create / revoke.
//
// Plaintext from `POST /v1/api-keys` is shown once in a warning-styled
// banner — operators have exactly that one chance to copy it. Subsequent
// reads only surface audit_id / name / created_at / revoked.

export function ApiKeysView(): JSX.Element {
  const [records, setRecords] = useState<ApiKeyRecord[]>([]);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<CreatedApiKey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [createDisabled, setCreateDisabled] = useState(false);

  const refresh = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const response = await apiKeys.list();
      setRecords(response.results);
    } catch (e) {
      setError(formatError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const create = async () => {
    if (!name.trim()) return;
    setError(null);
    try {
      const result = await apiKeys.create(name.trim());
      setCreated(result);
      setName("");
      setCreateDisabled(false);
      await refresh();
    } catch (e) {
      const formatted = formatError(e);
      setError(formatted);
      // Backend in env-mode returns 409 — keep the form disabled so a
      // confused operator doesn't keep retrying.
      if (e instanceof ApiError && e.status === 409) {
        setCreateDisabled(true);
      }
    }
  };

  const revoke = async (auditId: string) => {
    setError(null);
    try {
      await apiKeys.revoke(auditId);
      await refresh();
    } catch (e) {
      setError(formatError(e));
    }
  };

  return (
    <section>
      <header className="view-header">
        <h2>API keys</h2>
        <p className="view-subtitle">
          Bearer tokens accepted by the API Gateway — resolved through the{" "}
          <code className="mono">ApiKeyStore</code> contract.
        </p>
      </header>

      {error && <div className="error" style={{ marginTop: "0.75rem" }}>{error}</div>}
      {created && (
        <div className="card" style={{ marginTop: "0.75rem" }}>
          <div className="card__body">
            <strong>Key created — copy this plaintext now.</strong>
            <div className="muted" style={{ fontSize: "0.82rem", marginTop: "0.25rem" }}>
              It will not be shown again. Audit id: <code>{created.audit_id}</code>
            </div>
            <pre className="plaintext-banner">{created.plaintext}</pre>
            <button className="secondary" onClick={() => setCreated(null)}>
              I copied it
            </button>
          </div>
        </div>
      )}

      <div className="card" style={{ marginTop: "1rem" }}>
        <div className="card__header">
          <div>
            <h3 className="card__title">Create a new key</h3>
            <div className="card__subtitle">
              Only available when <code className="mono">API_KEY_BACKEND=sqlite</code>.
              Env-backed stores are read-only.
            </div>
          </div>
        </div>
        <div className="card__body">
          <div className="row">
            <div>
              <label htmlFor="new-key-name">Name</label>
              <input
                id="new-key-name"
                type="text"
                placeholder="e.g. ingest-bot"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void create();
                }}
                disabled={createDisabled}
              />
            </div>
            <div style={{ flex: 0 }}>
              <button onClick={create} disabled={!name.trim() || createDisabled}>
                Create key
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="card" style={{ marginTop: "1rem" }}>
        <div className="card__header">
          <div>
            <h3 className="card__title">
              Configured keys
              <span
                className="badge badge--accent"
                style={{ marginLeft: "0.6rem", verticalAlign: "middle" }}
              >
                {records.length}
              </span>
            </h3>
            <div className="card__subtitle">
              SHA-256 hashes only — plaintext was returned at creation time.
            </div>
          </div>
        </div>
        <div className="card__body card__body--flush">
          <div className="table-wrap">
            <table aria-label="API keys">
              <thead>
                <tr>
                  <th style={{ width: "11rem" }}>Audit ID</th>
                  <th>Name</th>
                  <th style={{ width: "12rem", whiteSpace: "nowrap" }}>Created</th>
                  <th style={{ width: "6rem" }}>Status</th>
                  <th style={{ width: "5rem" }}></th>
                </tr>
              </thead>
              <tbody>
                {loading && (
                  <tr>
                    <td colSpan={5} className="empty-state">Loading…</td>
                  </tr>
                )}
                {!loading && records.length === 0 && (
                  <tr>
                    <td colSpan={5} className="empty-state">
                      No keys configured yet.
                    </td>
                  </tr>
                )}
                {records.map((record) => (
                  <tr key={record.audit_id}>
                    <td><code>{record.audit_id}</code></td>
                    <td>{record.name}</td>
                    <td className="muted mono" style={{ whiteSpace: "nowrap" }}>
                      {formatCreatedAt(record.created_at)}
                    </td>
                    <td>
                      <span
                        className={
                          record.revoked
                            ? "badge badge--revoked"
                            : "badge badge--success"
                        }
                      >
                        {record.revoked ? "revoked" : "active"}
                      </span>
                    </td>
                    <td>
                      {!record.revoked && (
                        <button
                          className="danger"
                          onClick={() => revoke(record.audit_id)}
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </section>
  );
}

function formatCreatedAt(iso: string): string {
  // Render as `YYYY-MM-DD HH:MM` — locale-independent and narrow enough
  // to fit the column without wrapping. The full ISO string is still
  // available via the audit log if anyone needs sub-minute precision.
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, "0");
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ` +
    `${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

function formatError(e: unknown): string {
  if (e instanceof ApiError) {
    if (e.status === 409) {
      return "API_KEY_BACKEND=env is read-only. Switch to sqlite to manage keys via this UI.";
    }
    if (e.status === 401) {
      return "Admin key missing or rejected. Set it in the bar above.";
    }
    return `${e.message}: ${JSON.stringify(e.detail)}`;
  }
  return String(e);
}
