"""File-based ConfigProvider reading/writing a YAML file.

Phase 1 stub per `docs/phases.md`:
> Implement file-based ConfigProvider as the initial stub — reads
> configuration from a YAML/JSON file, supports all ConfigProvider contract
> methods. This allows Phases 2–3 to resolve model endpoints, chunking
> config, and RAG prompt templates without the Admin API or database being
> ready yet.

Reads on every access (simple, no cache invalidation). Writes atomically
via temp-file + rename. On first construction, if the target file does
not exist, a defaults file is seeded so the composition root can boot
without requiring any manual setup.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import yaml

from contracts import (
    ChunkConfig,
    EmbeddingConfig,
    GenerationConfig,
    RerankerConfig,
)

__all__ = ["DEFAULT_CONFIG", "FileConfigProvider"]


DEFAULT_CONFIG: dict[str, Any] = {
    "embedding": {
        "endpoint": "http://localhost:11434/v1",
        "api_type": "openai-compatible",
        "model_name": "nomic-embed-text",
        "parameters": {},
    },
    "reranker": {
        "type": "cross_encoder",
        "endpoint": None,
        "model_name": "BAAI/bge-reranker-base",
        "parameters": {},
    },
    "generation": {
        "endpoint": "http://localhost:11434/v1",
        "api_type": "openai-compatible",
        "model_name": "llama3",
        "parameters": {"temperature": 0.2, "max_tokens": 2048},
    },
    "chunking": {
        "method": "recursive",
        "size": 1000,
        "overlap": 200,
        "parameters": {},
    },
    "rag_prompt_template": (
        "You are a helpful assistant. Answer the user's question using ONLY "
        "the provided context. Cite chunk IDs as [chunk:N] inline.\n\n"
        "Context:\n{context}\n\n"
        "Question: {question}"
    ),
    "default_collection": "default",
}


class FileConfigProvider:
    """YAML-backed implementation of the `ConfigProvider` contract."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write(DEFAULT_CONFIG)

    # --- internal file I/O ---

    def _read(self) -> dict[str, Any]:
        with self._lock:
            with self._path.open("r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f)
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ValueError(
                f"Config file at {self._path} must be a YAML mapping, "
                f"got {type(loaded).__name__}."
            )
        return dict(loaded)

    def _write(self, data: dict[str, Any]) -> None:
        with self._lock:
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)
            tmp.replace(self._path)

    def _update(self, key: str, value: Any) -> None:
        data = self._read()
        data[key] = value
        self._write(data)

    # --- Reads ---

    def get_embedding_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(**self._read()["embedding"])

    def get_reranker_config(self) -> RerankerConfig:
        return RerankerConfig(**self._read()["reranker"])

    def get_generation_config(self) -> GenerationConfig:
        return GenerationConfig(**self._read()["generation"])

    def get_chunking_config(self) -> ChunkConfig:
        return ChunkConfig(**self._read()["chunking"])

    def get_rag_prompt_template(self) -> str:
        return str(self._read()["rag_prompt_template"])

    def get_default_collection(self) -> str:
        return str(self._read()["default_collection"])

    # --- Writes ---

    def set_embedding_config(self, config: EmbeddingConfig) -> None:
        self._update("embedding", config.model_dump(mode="json"))

    def set_reranker_config(self, config: RerankerConfig) -> None:
        self._update("reranker", config.model_dump(mode="json"))

    def set_generation_config(self, config: GenerationConfig) -> None:
        self._update("generation", config.model_dump(mode="json"))

    def set_chunking_config(self, config: ChunkConfig) -> None:
        self._update("chunking", config.model_dump(mode="json"))

    def set_rag_prompt_template(self, template: str) -> None:
        self._update("rag_prompt_template", template)

    def set_default_collection(self, collection: str) -> None:
        self._update("default_collection", collection)
