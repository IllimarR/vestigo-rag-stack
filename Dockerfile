# vestigo-rag-stack — Python services image.
#
# One image, three container roles. The composition root (`main.py`)
# accepts `--service {gateway,admin,ingest}` and the Compose file passes
# the appropriate flag per container. This keeps the registry footprint
# small and reinforces the architectural argument that the three
# services share the same code path until the very last entrypoint
# decision.
#
# Two stages:
#   1. `builder` — installs the production dependency set with `uv` into
#      a project-local `.venv`. No dev tools, no test packages.
#   2. `runtime` — slim Python image that only copies the resolved venv
#      and the application source. The smaller surface keeps image
#      pull time and CVE exposure down.

# --- Stage 1: builder ------------------------------------------------------

FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY packages/ ./packages/
COPY services/ ./services/

# Install the locked production dependency set only — no dev group.
RUN uv sync --frozen --no-dev


# --- Stage 2: runtime ------------------------------------------------------

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/app/.venv/bin:$PATH"

# `markitdown` shells out to system binaries for some converters; keep
# the runtime layer small but include the few packages it actually
# needs at runtime. `curl` is for in-container healthchecks (Compose
# uses it to gate dependent services on readiness).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY packages/ ./packages/
COPY services/ ./services/
COPY main.py ./

# Compose mounts persistent volumes here; the path matches the default
# CONTROL_PLANE_DB_PATH / AUDIT_LOG_FILE values, so an unconfigured
# container still writes somewhere persistent rather than vanishing on
# restart.
RUN mkdir -p /app/data /app/config

ENTRYPOINT ["python", "main.py"]
CMD ["--service", "all"]
