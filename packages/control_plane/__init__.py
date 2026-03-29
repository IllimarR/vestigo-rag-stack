"""Shared control-plane DB infrastructure for vestigo-rag-stack.

The Admin and Audit services persist their state (model configuration,
API keys, audit events) to a single SQLite file accessed via SQLAlchemy
2.x. This package owns the three pieces both services share:

  * `Base` — the declarative base. Each service registers its own
    `Table` / `Mapped` classes against it, but the metadata is shared
    so `Base.metadata.create_all(engine)` materialises every service's
    schema in one round-trip.
  * `get_engine(path)` — opens a SQLite engine with `check_same_thread=False`
    (FastAPI runs handlers on a thread pool) and a `PRAGMA foreign_keys=ON`
    connect listener.
  * `SessionFactory` — `sessionmaker[Session]` bound to the engine,
    returned by `make_session_factory(engine)`.

This is the analogue of `packages/contracts/`: shared infrastructure
that multiple services depend on without depending on each other. It is
*not* a service. The composition root in `main.py` is the only place
that constructs engines.

Alembic is intentionally absent. The prototype boots via
`Base.metadata.create_all()` because there are no schema migrations
yet; adding Alembic is a self-contained follow-up that doesn't touch
the model classes.
"""

from __future__ import annotations

from control_plane.base import Base
from control_plane.engine import get_engine, make_session_factory

__all__ = ["Base", "get_engine", "make_session_factory"]
