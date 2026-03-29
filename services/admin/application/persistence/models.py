"""SQLAlchemy table classes for admin-owned state.

Audit tables live in `services.audit.application.persistence.models`,
not here — admin and audit own their own tables on the shared metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from control_plane import Base
from sqlalchemy import JSON, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

__all__ = ["ConfigEntry"]


class ConfigEntry(Base):
    """One row per top-level config section.

    The shape mirrors the YAML file `FileConfigProvider` writes: keys
    like `embedding`, `reranker`, `generation`, `chunking` hold a JSON
    object dumped from the matching frozen DTO via `model_dump(mode="json")`;
    `rag_prompt_template` and `default_collection` hold a JSON string.

    JSON-as-blob keeps the schema flat — adding a new config section in
    the future is a code change in the DTO and one new key, no
    migration. Trade-off: filtering on inner fields would need
    `json_extract(...)`, but the `ConfigProvider` contract only reads
    whole sections, so flat is fine.
    """

    __tablename__ = "admin_config_entries"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
