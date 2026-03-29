# Vestigo admin-ui

Operator control plane for `vestigo-rag-stack`. Talks to the Admin API
on port 8001 over the same routes documented in
`services/admin/README.md`.

## Stack

- Vite + React + TypeScript.
- No design system, no router, no state library beyond `useState`.
  Three views (API keys / Configuration / Audit log) and a shared
  `AuthBar`. Plain CSS in `src/styles.css`.
- Vitest + Testing Library cover the smoke surface: tab switching,
  initial loads, localStorage persistence, and Authorization header
  attachment.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `VITE_ADMIN_API_URL` | `http://localhost:8001` | Base URL for the Admin API |

The shared-secret admin bearer is entered into the auth bar in the
header and held in `localStorage` (`vestigo.admin.token`). Clearing
the field also wipes the stored value — no orphan auth state.

## Scripts

```bash
npm install
npm run dev      # vite dev server on http://localhost:3000
npm run build    # type-check + production build into ./dist
npm run preview  # serve ./dist locally
npm run test     # vitest run (jsdom + Testing Library)
npm run lint     # tsc --noEmit (no separate linter — Vite/TS is enough for this scope)
```

## Layout

```
admin-ui/
├── index.html
├── package.json
├── tsconfig.json
├── vite.config.ts
└── src/
    ├── App.tsx              # tab shell
    ├── main.tsx             # ReactDOM entry
    ├── styles.css
    ├── api/
    │   ├── client.ts        # typed fetch wrapper, ApiError, token helpers
    │   └── types.ts         # mirrors Admin API response shapes
    ├── components/
    │   └── AuthBar.tsx
    ├── views/
    │   ├── ApiKeysView.tsx  # list / create / revoke
    │   ├── ConfigView.tsx   # six per-section edits (JSON textarea)
    │   └── AuditView.tsx    # filter + view audit log rows
    └── __tests__/
        ├── App.test.tsx     # smoke tests via Testing Library + fetch mock
        └── setup.ts
```

## Scope

Phase 4 prototype. Per-user admin auth is a Phase 6 follow-up; the UI
is plumbed for a single shared secret. Future enhancements:
form-driven config editors (instead of raw JSON textareas), audit log
exports, and inline RAG prompt testing.
