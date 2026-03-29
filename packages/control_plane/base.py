"""SQLAlchemy declarative base shared by the admin and audit services."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase

__all__ = ["Base"]


class Base(DeclarativeBase):
    """Shared declarative base.

    Admin tables (config, api_keys) and audit tables (query / ingest /
    admin events) all register on `Base.metadata`, so a single
    `Base.metadata.create_all(engine)` materialises the whole schema.
    """
