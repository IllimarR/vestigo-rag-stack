"""SQLite-backed ConfigProvider — Phase 4 replacement for the file stub.

Reads and writes JSON-shaped config sections out of a single table on
the shared control-plane DB. Same observable surface as
`FileConfigProvider`; the existing YAML stub stays valid for the
simplest deployments and the operator chooses between them via the
`CONFIG_BACKEND` env var.

On construction, if the table is empty:
  * if a `seed_from_path` is given AND that YAML file exists, the
    existing tuned config is read out and persisted. This is the
    one-shot migration path for operators flipping from `file` to
    `sqlite` mid-life.
  * otherwise `DEFAULT_CONFIG` is persisted. Same defaults as
    `FileConfigProvider`, so the boot story is identical regardless of
    backend choice.

Writes are single-row UPSERTs in their own session — small, isolated,
and safe to call from multiple threads. Reads always go to the DB; no
in-process cache, no invalidation problem. Hot-path overhead is
microseconds (~one SQLite read per query) — well below the embedding /
generation latency that dominates the request.
"""

from __future__ import annotations

import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from contracts import (
    ChunkConfig,
    EmbeddingConfig,
    GenerationConfig,
    RerankerConfig,
)
from control_plane import Base, get_engine, make_session_factory
from sqlalchemy import Engine, select
from sqlalchemy.orm import sessionmaker

from services.admin.application.file_config_provider import DEFAULT_CONFIG
from services.admin.application.persistence.models import ConfigEntry

__all__ = ["SqliteConfigProvider"]


class SqliteConfigProvider:
    """SQLite implementation of the `ConfigProvider` contract."""

    def __init__(
        self,
        *,
        engine: Engine,
        seed_from_path: Path | None = None,
    ) -> None:
        self._engine = engine
        self._session_factory: sessionmaker[Any] = make_session_factory(engine)
        self._lock = threading.Lock()
        Base.metadata.create_all(engine)
        self._bootstrap_if_empty(seed_from_path)

    # --- construction helpers -------------------------------------------------

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        seed_from_path: Path | None = None,
    ) -> SqliteConfigProvider:
        """Convenience constructor: open an engine at `path` and seed if empty."""

        return cls(engine=get_engine(path), seed_from_path=seed_from_path)

    def _bootstrap_if_empty(self, seed_from_path: Path | None) -> None:
        with self._session_factory() as session:
            existing = session.execute(select(ConfigEntry.key)).first()
            if existing is not None:
                return
            seed = _read_seed(seed_from_path) if seed_from_path else DEFAULT_CONFIG
            now = datetime.now(UTC)
            session.add_all(
                [ConfigEntry(key=key, value=value, updated_at=now) for key, value in seed.items()]
            )
            session.commit()

    # --- internal I/O ---------------------------------------------------------

    def _get(self, key: str) -> Any:
        with self._session_factory() as session:
            row = session.get(ConfigEntry, key)
        if row is None:
            raise KeyError(f"config key {key!r} is missing — DB was not seeded correctly")
        return row.value

    def _set(self, key: str, value: Any) -> None:
        with self._lock, self._session_factory() as session:
            row = session.get(ConfigEntry, key)
            now = datetime.now(UTC)
            if row is None:
                session.add(ConfigEntry(key=key, value=value, updated_at=now))
            else:
                row.value = value
                row.updated_at = now
            session.commit()

    # --- Reads ----------------------------------------------------------------

    def get_embedding_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(**self._get("embedding"))

    def get_reranker_config(self) -> RerankerConfig:
        return RerankerConfig(**self._get("reranker"))

    def get_generation_config(self) -> GenerationConfig:
        return GenerationConfig(**self._get("generation"))

    def get_chunking_config(self) -> ChunkConfig:
        return ChunkConfig(**self._get("chunking"))

    def get_rag_prompt_template(self) -> str:
        return str(self._get("rag_prompt_template"))

    def get_default_collection(self) -> str:
        return str(self._get("default_collection"))

    # --- Writes ---------------------------------------------------------------

    def set_embedding_config(self, config: EmbeddingConfig) -> None:
        self._set("embedding", config.model_dump(mode="json"))

    def set_reranker_config(self, config: RerankerConfig) -> None:
        self._set("reranker", config.model_dump(mode="json"))

    def set_generation_config(self, config: GenerationConfig) -> None:
        self._set("generation", config.model_dump(mode="json"))

    def set_chunking_config(self, config: ChunkConfig) -> None:
        self._set("chunking", config.model_dump(mode="json"))

    def set_rag_prompt_template(self, template: str) -> None:
        self._set("rag_prompt_template", template)

    def set_default_collection(self, collection: str) -> None:
        self._set("default_collection", collection)


def _read_seed(path: Path) -> dict[str, Any]:
    """Read an existing YAML config file for the file→sqlite hand-off."""

    if not path.exists():
        return DEFAULT_CONFIG
    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f)
    if loaded is None:
        return DEFAULT_CONFIG
    if not isinstance(loaded, dict):
        raise ValueError(
            f"Seed config at {path} must be a YAML mapping, got {type(loaded).__name__}."
        )
    merged: dict[str, Any] = dict(DEFAULT_CONFIG)
    merged.update(loaded)
    return merged
