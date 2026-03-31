# Deployment Runbook

> Back to [README](../README.md) | See also: [Architecture](architecture.md) · [Swap-Demo Evidence](swap-demo.md) · [Phases](phases.md)

---

This document is the operational counterpart to
[Swap-Demo Evidence](swap-demo.md): where that file proves the
*modularity* claim, this one proves the *self-hostability* claim. Phase 6
exit criteria call for "system runs self-hosted end-to-end with
reproducible setup" — the single `docker compose up` flow below is that
proof.

---

## Stack topology

Six containers, two custom images, one upstream image:

| Container | Image | Port (host) | Purpose |
|---|---|---|---|
| `vestigo-gateway` | `vestigo-app:latest` (`--service gateway`) | 8000 | OpenAI Responses-shaped query API |
| `vestigo-admin` | `vestigo-app:latest` (`--service admin`) | 8001 | Config / audit / API-key management |
| `vestigo-ingest` | `vestigo-app:latest` (`--service ingest`) | 8002 | Filesystem + push document ingestion |
| `vestigo-admin-ui` | `vestigo-admin-ui:latest` (nginx) | 3000 | Vite + React SPA |
| `vestigo-chromadb` | `chromadb/chroma:0.5.20` | 8500 | Vector storage |

Two persistent named volumes:

| Volume | Mounted at | Purpose |
|---|---|---|
| `chromadb-data` | `/chroma/chroma` (in chromadb) | ChromaDB collections, embeddings |
| `control-plane-data` | `/app/data` (in gateway, admin, ingest) | SQLite control-plane DB, audit log file backend |

Plus two host bind-mounts:

| Bind | Mounted at | Purpose |
|---|---|---|
| `./config` | `/app/config` | `config.yaml` for the file-backed `ConfigProvider`. Edit on host, restart container to apply. |
| `./data/incoming` | `/app/data/incoming` | Drop folder for the `FilesystemSourceConnector` (only used when `SOURCE_CONNECTORS=filesystem`). |

The LLM server (Ollama, vLLM, ...) **runs on the host**, not in
Compose. Containers reach it via `host.docker.internal` — set up
automatically on Mac and Windows, mapped to the bridge gateway via
`extra_hosts` on Linux. Keeping models on the host means GPU access,
weights, and bandwidth all stay on hardware that has them.

---

## First-run bootstrap

```bash
# 1. Seed env
cp .env.example .env

# Optional: pre-configure auth so the gateway / admin / ingest APIs
# don't run in dev-mode unauthenticated.
echo "ADMIN_API_KEY=$(openssl rand -hex 16)" >> .env
echo "INGEST_API_KEY=$(openssl rand -hex 16)" >> .env

# 2. Point the LLM endpoints at the host
# Edit config/config.yaml:
#   embedding.endpoint:  http://host.docker.internal:11434/v1
#   generation.endpoint: http://host.docker.internal:11434/v1
# (Replace 11434 / model_name with whatever your Ollama / vLLM / ...
# server actually exposes.)

# 3. Build + start
docker compose up -d
```

Verify:

```bash
curl http://localhost:8000/health   # gateway
curl http://localhost:8001/health   # admin
curl http://localhost:8002/health   # ingest
curl http://localhost:8500/api/v1/heartbeat   # chromadb
open http://localhost:3000          # admin-ui (Mac)
```

All five Vestigo containers gate on each other's `/health`, and the
gateway/admin/ingest containers gate on ChromaDB's
`/api/v1/heartbeat`, so a clean boot order is enforced — there is no
race window where the gateway tries to talk to an unready ChromaDB.

---

## Swapping a backend in the live stack

The whole point of the architecture. Three swap surfaces:

### 1. Application-level (via `config/config.yaml`)

Edit `config/config.yaml` on the host, then restart the affected
container:

```bash
docker compose restart admin gateway ingest
```

See [Swap-Demo Evidence](swap-demo.md) §1-4 for the per-contract
YAML. Examples:

- `embedding.api_type: sentence-transformers` — local embeddings, no
  HTTP hop (model weights download into the venv on first call).
- `generation.api_type: anthropic` + `generation.parameters.api_key:
  sk-ant-...` — switch the answer model to Claude.
- `reranker.type: llm` — reuse the bound generation provider as a
  zero-shot relevance judge.
- `chunking.method: fixed_size` — simplest possible chunker.

### 2. Infrastructure-level (via `.env`)

Edit `.env` on the host, then restart:

```bash
docker compose down && docker compose up -d
```

(The container env is captured at `create` time, so `restart` alone
doesn't pick up new env. `down && up` does.)

Available swaps:

| Variable | Values | Notes |
|---|---|---|
| `CONFIG_BACKEND` | `file` (default) \| `sqlite` | SQLite seeds from `config.yaml` on first run if `CONFIG_FILE_PATH` is present. |
| `AUDIT_BACKEND` | `file` (default) \| `sqlite` | JSONL files at `AUDIT_LOG_FILE` vs an indexed table in the control-plane DB. |
| `API_KEY_BACKEND` | `env` (default) \| `sqlite` | Admin-API-managed keys live in SQLite; env keys come from `API_KEYS`. Switching from `env` to `sqlite` seeds any existing `API_KEYS` into the DB once. |
| `SOURCE_CONNECTORS` | `filesystem` (default) \| `api` | `filesystem` watches `data/incoming/`; `api` exposes the push routes at `:8002/v1/documents`. |
| `VECTOR_STORE_BACKEND` | `in_memory` \| `chromadb` (Compose default) | `in_memory` is for tests / local dev only; Compose pins this to `chromadb` regardless of the `.env` value. |

### 3. Code-level (deploying a new adapter)

A new adapter requires only:
1. Implement the contract under `services/<owner>/application/`.
2. Add a factory branch in the matching `_build_*` helper in `main.py`.
3. Register the factory in the corresponding parameterized test suite
   in `tests/test_*_contracts.py` — it inherits the full contract
   compliance battery.
4. `docker compose build && docker compose up -d`.

The `import-linter` contracts fail loudly if step 1 reaches outside
its allowed dependency surface, so the abstraction can't drift
silently.

---

## Backup and restore

Two named volumes hold all state:

```bash
# Snapshot ChromaDB to a tarball
docker run --rm \
  -v vestigo-rag-stack_chromadb-data:/source:ro \
  -v "$(pwd)":/backup \
  alpine tar czf /backup/chromadb-$(date +%F).tar.gz -C /source .

# Snapshot the control-plane (SQLite DB, JSONL audit log)
docker run --rm \
  -v vestigo-rag-stack_control-plane-data:/source:ro \
  -v "$(pwd)":/backup \
  alpine tar czf /backup/control-plane-$(date +%F).tar.gz -C /source .
```

Restore is the inverse — extract the tarball into the same named volume
with the stack stopped (`docker compose down`).

The host bind-mounts (`./config/`, `./data/incoming/`) back up via
ordinary file copy — they live on the host filesystem.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `vestigo-gateway` restarts in a loop with `connection refused` to chromadb | ChromaDB volume corrupted / first-run race | `docker compose down -v` (deletes volumes — careful!) then `docker compose up -d` |
| `[vestigo] WARNING: no API keys configured` | `API_KEYS` empty and `API_KEY_BACKEND=env` | Set `API_KEYS=key1,key2,...` in `.env` and recreate, or switch to `API_KEY_BACKEND=sqlite` and POST keys via the admin API |
| Embedding / generation errors `Connection refused` from inside containers | LLM endpoint points at `localhost` instead of `host.docker.internal` | Edit `config/config.yaml`, restart the gateway and ingest containers |
| `403` from the gateway with `INVALID_API_KEY` | Bearer header missing or wrong | Send `Authorization: Bearer <key>` with one of the keys in `API_KEYS` (env mode) or one created via `POST :8001/v1/api-keys` (sqlite mode) |

---

## Reproducing the Phase 6 exit-criterion

The "system runs self-hosted end-to-end with reproducible setup" claim
is reproducible from a clean checkout in under two minutes (excluding
first-time image build):

```bash
git clone git@github.com:IllimarR/vestigo-rag-stack.git
cd vestigo-rag-stack
cp .env.example .env
docker compose up -d --build
sleep 30   # first-time image build + ChromaDB warmup
for port in 8000 8001 8002 8500; do curl -fsS http://localhost:$port/health || curl -fsS http://localhost:$port/api/v1/heartbeat; echo; done
docker compose down
```

Every `/health` returning `ok` and the ChromaDB heartbeat returning a
nanosecond timestamp closes the criterion.
