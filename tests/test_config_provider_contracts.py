"""Contract-compliance suite for every `ConfigProvider` implementation.

One test body, one contract, N backends. Add a new provider by appending
its factory to `_PROVIDERS` and the whole suite runs against it for
free. Same pattern as `tests/test_vector_store_contracts.py`.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from contracts import (
    ChunkConfig,
    ConfigProvider,
    EmbeddingConfig,
    GenerationConfig,
    RerankerConfig,
)

from services.admin.application.file_config_provider import (
    DEFAULT_CONFIG,
    FileConfigProvider,
)
from services.admin.application.sqlite_config_provider import SqliteConfigProvider

ProviderFactory = Callable[[Path], ConfigProvider]


def _file_backend(tmp_path: Path) -> ConfigProvider:
    return FileConfigProvider(tmp_path / "config.yaml")


def _sqlite_backend(tmp_path: Path) -> ConfigProvider:
    return SqliteConfigProvider.from_path(tmp_path / "control_plane.db")


_PROVIDERS: dict[str, ProviderFactory] = {
    "file": _file_backend,
    "sqlite": _sqlite_backend,
}


@pytest.fixture(params=sorted(_PROVIDERS), ids=sorted(_PROVIDERS))
def provider(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[ConfigProvider]:
    factory = _PROVIDERS[request.param]
    yield factory(tmp_path)


# --- Bootstrap defaults -------------------------------------------------------


def test_bootstrap_seeds_defaults(provider: ConfigProvider) -> None:
    chunking = provider.get_chunking_config()
    assert chunking.method == DEFAULT_CONFIG["chunking"]["method"]
    assert chunking.size == DEFAULT_CONFIG["chunking"]["size"]
    assert chunking.overlap == DEFAULT_CONFIG["chunking"]["overlap"]


def test_bootstrap_seeds_prompt_template(provider: ConfigProvider) -> None:
    template = provider.get_rag_prompt_template()
    assert "{context}" in template
    assert "{question}" in template


def test_bootstrap_seeds_default_collection(provider: ConfigProvider) -> None:
    assert provider.get_default_collection() == DEFAULT_CONFIG["default_collection"]


def test_bootstrap_seeds_embedding(provider: ConfigProvider) -> None:
    embedding = provider.get_embedding_config()
    assert embedding.api_type == DEFAULT_CONFIG["embedding"]["api_type"]
    assert embedding.model_name == DEFAULT_CONFIG["embedding"]["model_name"]


def test_bootstrap_seeds_reranker(provider: ConfigProvider) -> None:
    reranker = provider.get_reranker_config()
    assert reranker.type == DEFAULT_CONFIG["reranker"]["type"]
    assert reranker.model_name == DEFAULT_CONFIG["reranker"]["model_name"]


def test_bootstrap_seeds_generation(provider: ConfigProvider) -> None:
    generation = provider.get_generation_config()
    assert generation.api_type == DEFAULT_CONFIG["generation"]["api_type"]
    assert generation.model_name == DEFAULT_CONFIG["generation"]["model_name"]


# --- Write roundtrip ---------------------------------------------------------


def test_set_embedding_config_roundtrip(provider: ConfigProvider) -> None:
    provider.set_embedding_config(
        EmbeddingConfig(
            endpoint="http://example/e",
            api_type="openai-compatible",
            model_name="e5-base",
        )
    )
    refreshed = provider.get_embedding_config()
    assert refreshed.model_name == "e5-base"
    assert refreshed.endpoint == "http://example/e"


def test_set_reranker_config_roundtrip(provider: ConfigProvider) -> None:
    provider.set_reranker_config(
        RerankerConfig(type="cross_encoder", endpoint=None, model_name="bge-reranker-large")
    )
    refreshed = provider.get_reranker_config()
    assert refreshed.model_name == "bge-reranker-large"


def test_set_generation_config_roundtrip(provider: ConfigProvider) -> None:
    provider.set_generation_config(
        GenerationConfig(
            endpoint="http://example/g",
            api_type="anthropic",
            model_name="claude",
            parameters={"temperature": 0.7, "max_tokens": 1024},
        )
    )
    refreshed = provider.get_generation_config()
    assert refreshed.api_type == "anthropic"
    assert refreshed.parameters["temperature"] == 0.7


def test_set_chunking_config_roundtrip(provider: ConfigProvider) -> None:
    provider.set_chunking_config(
        ChunkConfig(method="semantic", size=800, overlap=120, parameters={"foo": "bar"})
    )
    refreshed = provider.get_chunking_config()
    assert refreshed.method == "semantic"
    assert refreshed.size == 800
    assert refreshed.overlap == 120
    assert refreshed.parameters["foo"] == "bar"


def test_set_rag_prompt_template_roundtrip(provider: ConfigProvider) -> None:
    provider.set_rag_prompt_template("NEW: {question}")
    assert provider.get_rag_prompt_template() == "NEW: {question}"


def test_set_default_collection_roundtrip(provider: ConfigProvider) -> None:
    provider.set_default_collection("corporate-docs")
    assert provider.get_default_collection() == "corporate-docs"


# --- Persistence across fresh instances --------------------------------------


def test_writes_persist_across_fresh_provider(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    """Writing then constructing a new provider on the same backing store
    must surface the persisted value — proves the write is durable, not
    just held in an in-memory cache."""

    # Run once per backend by tapping the same factory dict.
    for name, factory in _PROVIDERS.items():
        subdir = tmp_path / name
        subdir.mkdir()
        first = factory(subdir)
        first.set_default_collection(f"persisted-via-{name}")
        first.set_rag_prompt_template(f"template-{name}: {{question}}")

        second = factory(subdir)
        assert second.get_default_collection() == f"persisted-via-{name}"
        assert second.get_rag_prompt_template() == f"template-{name}: {{question}}"


# --- SQLite-specific: file→sqlite seed hand-off -------------------------------


def test_sqlite_seeds_from_existing_yaml(tmp_path: Path) -> None:
    """When `seed_from_path` points at an existing FileConfigProvider file,
    the SQLite provider's first run must inherit its tuned values.

    This is the operator's migration path from CONFIG_BACKEND=file to
    CONFIG_BACKEND=sqlite — switch the env var, restart, keep your config."""

    yaml_path = tmp_path / "config.yaml"
    file_provider = FileConfigProvider(yaml_path)
    file_provider.set_default_collection("from-yaml")
    file_provider.set_rag_prompt_template("migrated: {question}")

    db_path = tmp_path / "control_plane.db"
    sqlite_provider = SqliteConfigProvider.from_path(db_path, seed_from_path=yaml_path)
    assert sqlite_provider.get_default_collection() == "from-yaml"
    assert sqlite_provider.get_rag_prompt_template() == "migrated: {question}"


def test_sqlite_seed_ignored_if_db_already_populated(tmp_path: Path) -> None:
    """Seeding only happens on an empty DB — re-pointing to a YAML on a
    populated DB must not clobber existing values."""

    db_path = tmp_path / "control_plane.db"
    first = SqliteConfigProvider.from_path(db_path)
    first.set_default_collection("custom-already")

    yaml_path = tmp_path / "should-be-ignored.yaml"
    other_file = FileConfigProvider(yaml_path)
    other_file.set_default_collection("would-overwrite")

    second = SqliteConfigProvider.from_path(db_path, seed_from_path=yaml_path)
    assert second.get_default_collection() == "custom-already"
