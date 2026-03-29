import { useCallback, useEffect, useState } from "react";
import { apiKeys, ApiError } from "../api/client";
import type { ApiKeyRecord, CreatedApiKey } from "../api/types";

// API key management: list / create / revoke.
//
// The plaintext returned by `POST /v1/api-keys` is shown once in a
// bordered banner — operators have exactly that one chance to copy it.
// Subsequent reads only surface audit_id / name / created_at / revoked.

export function ApiKeysView(): JSX.Element {
  const [records, setRecords] = useState<ApiKeyRecord[]>([]);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<CreatedApiKey | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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
      await refresh();
    } catch (e) {
      setError(formatError(e));
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
      <h2>API keys</h2>
      {error && <div className="error">{error}</div>}
      {created && (
        <div className="success">
          <strong>Key created — copy this plaintext now.</strong>
          <br />
          It will not be shown again. Audit id: <code>{created.audit_id}</code>
          <pre className="plaintext-banner">{created.plaintext}</pre>
          <button className="secondary" onClick={() => setCreated(null)}>
            I copied it
          </button>
        </div>
      )}

      <div className="row">
        <div>
          <label htmlFor="new-key-name" style={{ marginTop: 0 }}>
            New key name
          </label>
          <input
            id="new-key-name"
            type="text"
            placeholder="e.g. ingest-bot"
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") void create();
            }}
          />
        </div>
        <div style={{ flex: 0 }}>
          <button onClick={create} disabled={!name.trim()}>
            Create
          </button>
        </div>
      </div>

      <table aria-label="API keys">
        <thead>
          <tr>
            <th>Audit ID</th>
            <th>Name</th>
            <th>Created</th>
            <th>Status</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {loading && (
            <tr>
              <td colSpan={5}>Loading…</td>
            </tr>
          )}
          {!loading && records.length === 0 && (
            <tr>
              <td colSpan={5}>No keys configured.</td>
            </tr>
          )}
          {records.map((record) => (
            <tr key={record.audit_id}>
              <td>
                <code>{record.audit_id}</code>
              </td>
              <td>{record.name}</td>
              <td>{new Date(record.created_at).toLocaleString()}</td>
              <td>{record.revoked ? "revoked" : "active"}</td>
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
    </section>
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
