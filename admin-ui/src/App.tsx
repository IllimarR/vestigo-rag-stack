import { useState } from "react";
import { ApiKeysView } from "./views/ApiKeysView";
import { ConfigView } from "./views/ConfigView";
import { AuditView } from "./views/AuditView";
import { AuthBar } from "./components/AuthBar";

type Tab = "keys" | "config" | "audit";

const TABS: Array<{ id: Tab; label: string }> = [
  { id: "keys", label: "API keys" },
  { id: "config", label: "Configuration" },
  { id: "audit", label: "Audit log" },
];

export function App(): JSX.Element {
  const [active, setActive] = useState<Tab>("keys");

  return (
    <>
      <header>
        <h1>Vestigo Admin</h1>
        <AuthBar />
      </header>

      <nav className="tabs">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            className={tab.id === active ? "active" : ""}
            onClick={() => setActive(tab.id)}
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
    </>
  );
}
