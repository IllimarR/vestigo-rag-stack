import { useEffect, useState } from "react";
import { ApiKeysView } from "./views/ApiKeysView";
import { ConfigView } from "./views/ConfigView";
import { AuditView } from "./views/AuditView";
import { AuthBar } from "./components/AuthBar";
import { adminHealth, getToken } from "./api/client";

type Tab = "keys" | "config" | "audit";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "keys", label: "API keys" },
  { id: "config", label: "Configuration" },
  { id: "audit", label: "Audit log" },
];

type ConnState = "online" | "offline" | "checking";

export function App(): JSX.Element {
  const [active, setActive] = useState<Tab>("keys");
  const [conn, setConn] = useState<ConnState>("checking");
  const [hasAuth, setHasAuth] = useState<boolean>(() => Boolean(getToken()));

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        await adminHealth();
        if (!cancelled) setConn("online");
      } catch {
        if (!cancelled) setConn("offline");
      }
    };
    void tick();
    const interval = window.setInterval(() => void tick(), 15000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  // Re-evaluate auth presence when the AuthBar updates localStorage. The
  // bar dispatches a synthetic 'storage'-like event when the user types
  // so we don't have to thread state down here.
  useEffect(() => {
    const onChange = () => setHasAuth(Boolean(getToken()));
    window.addEventListener("vestigo:auth-changed", onChange);
    return () => window.removeEventListener("vestigo:auth-changed", onChange);
  }, []);

  const statusLabel =
    conn === "checking"
      ? "Connecting…"
      : conn === "offline"
        ? "Admin API offline"
        : hasAuth
          ? "Connected"
          : "Authenticate to load data";

  const statusClass =
    conn === "offline"
      ? "topbar__status is-offline"
      : !hasAuth && conn === "online"
        ? "topbar__status is-anonymous"
        : "topbar__status";

  return (
    <>
      <header className="topbar">
        <div className="topbar__brand">
          <div className="topbar__mark" aria-hidden="true">V</div>
          <div className="topbar__titles">
            <h1 className="topbar__title">Vestigo Admin</h1>
            <span className="topbar__subtitle">Modular RAG control plane</span>
          </div>
        </div>
        <div className="topbar__spacer" />
        <span className={statusClass} role="status">{statusLabel}</span>
        <AuthBar />
      </header>

      <div className="page">
        <nav className="tabs">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              className={tab.id === active ? "active" : ""}
              onClick={() => setActive(tab.id)}
              aria-current={tab.id === active ? "page" : undefined}
            >
              {tab.label}
            </button>
          ))}
        </nav>

        <main>
          {active === "keys" && <ApiKeysView />}
          {active === "config" && <ConfigView />}
          {active === "audit" && <AuditView />}
        </main>
      </div>
    </>
  );
}
