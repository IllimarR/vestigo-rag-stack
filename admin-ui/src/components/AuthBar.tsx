import { useEffect, useState } from "react";
import { getToken, setToken } from "../api/client";

// Single shared-secret bearer for the Admin API. Holding the value in
// localStorage means a page reload doesn't kick the operator back to the
// "paste your key" step every time. Clearing the field wipes the stored
// value too — there is no orphan auth state.

export function AuthBar(): JSX.Element {
  const [value, setValue] = useState<string>(() => getToken());

  useEffect(() => {
    setToken(value);
  }, [value]);

  return (
    <div className="auth-bar">
      <label htmlFor="admin-key" style={{ marginTop: 0 }}>
        Admin key
      </label>
      <input
        id="admin-key"
        type="password"
        autoComplete="off"
        placeholder="ADMIN_API_KEY"
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      {value && (
        <button
          type="button"
          className="secondary"
          onClick={() => setValue("")}
          aria-label="clear admin key"
        >
          Clear
        </button>
      )}
    </div>
  );
}
