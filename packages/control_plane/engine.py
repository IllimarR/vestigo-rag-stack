"""Engine + sessionmaker factories for the control-plane SQLite DB."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

__all__ = ["get_engine", "make_session_factory"]


def get_engine(path: Path) -> Engine:
    """Open a SQLite engine for the control-plane DB.

    `check_same_thread=False` is required because FastAPI dispatches
    handlers onto an `asyncio` thread pool and a Session may be created
    on one thread and used on another. SQLAlchemy still serialises
    actual usage of a Session, so this only loosens SQLite's threading
    enforcement, not SQLAlchemy's.

    A `connect` listener enables `PRAGMA foreign_keys=ON` on every new
    connection — SQLite defaults to OFF, which silently lets dangling
    references survive deletes.
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{path}",
        future=True,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection: object, _: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Sessionmaker with autoflush off and expire_on_commit off.

    Expiring on commit forces attribute reloads after every commit,
    which causes a confusing `DetachedInstanceError` if the caller
    accesses the row after closing the session. The repositories in this
    project always copy data out of the row before returning it, so
    expiration after commit only hurts.
    """

    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )
