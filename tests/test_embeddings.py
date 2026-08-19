import math
from pathlib import Path
from types import SimpleNamespace

import pytest

from novel_editorial.core.config import Settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.llm.embeddings import (
    LocalNGramEmbedder,
    OpenAICompatEmbedder,
    build_embedding_client,
)


def _settings(
    *,
    backend: str = "local",
    model: str = "",
    dim: int = 256,
    top_k: int = 5,
) -> Settings:
    return Settings(
        data_dir=Path("."),
        config_path=Path("."),
        embedding_backend=backend,
        embedding_model=model,
        embedding_dim=dim,
        embedding_top_k=top_k,
    )


def test_local_embedder_is_deterministic() -> None:
    embedder = LocalNGramEmbedder(256)
    assert embedder.embed("雨夜归乡") == embedder.embed("雨夜归乡")
    assert len(embedder.embed("雨夜归乡")) == 256


def test_local_embedder_normalizes_l2() -> None:
    embedder = LocalNGramEmbedder(256)
    vector = embedder.embed("雨夜归乡，客船靠岸")
    norm = math.sqrt(sum(value * value for value in vector))
    assert norm == pytest.approx(1.0)


def test_local_embedder_distinguishes_different_texts() -> None:
    embedder = LocalNGramEmbedder(256)
    first = embedder.embed("雨夜归乡")
    second = embedder.embed("晴天出航")
    assert first != second


def test_local_embedder_char_ngram_overlap_scores_higher() -> None:
    embedder = LocalNGramEmbedder(256)
    base = embedder.embed("雨夜归乡")
    near = embedder.embed("雨夜回乡")
    far = embedder.embed("晴天出航")
    assert _cosine(base, near) > _cosine(base, far)


def test_local_embedder_empty_text_is_zero_vector() -> None:
    embedder = LocalNGramEmbedder(256)
    assert embedder.embed("") == [0.0] * 256


def test_openai_compat_embedder_returns_embedding(monkeypatch) -> None:
    class FakeEmbeddings:
        def create(self, **kwargs):
            assert kwargs["model"] == "text-embedding-3-small"
            assert kwargs["input"] == "hello"
            return SimpleNamespace(
                data=[SimpleNamespace(embedding=[0.1, 0.2, 0.3])]
            )

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    embedder = OpenAICompatEmbedder(
        base_url="https://example.com/v1",
        api_key="sk-test",
        model="text-embedding-3-small",
    )
    assert embedder.embed("hello") == [0.1, 0.2, 0.3]


def test_openai_compat_embedder_failure_raises_llm_error(monkeypatch) -> None:
    class FakeEmbeddings:
        def create(self, **kwargs):
            raise RuntimeError("backend exploded")

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    embedder = OpenAICompatEmbedder(
        base_url="https://example.com/v1",
        api_key="sk-test",
        model="text-embedding-3-small",
    )
    with pytest.raises(NovelError) as info:
        embedder.embed("hello")
    assert info.value.code is ErrorCode.LLM_ERROR
    assert "unknown" in info.value.context["error"]


def test_openai_compat_embedder_malformed_response_raises_llm_error(
    monkeypatch,
) -> None:
    class FakeEmbeddings:
        def create(self, **kwargs):
            return SimpleNamespace(data=[])

    class FakeOpenAI:
        def __init__(self, **kwargs):
            self.embeddings = FakeEmbeddings()

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    embedder = OpenAICompatEmbedder(
        base_url="https://example.com/v1",
        api_key="sk-test",
        model="text-embedding-3-small",
    )
    with pytest.raises(NovelError) as info:
        embedder.embed("hello")
    assert info.value.code is ErrorCode.LLM_ERROR
    assert info.value.context["error"] == "malformed"


def test_build_embedding_client_dispatches_local() -> None:
    client = build_embedding_client(_settings(backend="local", dim=128))
    assert isinstance(client, LocalNGramEmbedder)
    assert client.dim == 128


def test_build_embedding_client_dispatches_api(monkeypatch) -> None:
    seen: dict = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.embeddings = SimpleNamespace(create=lambda **kwargs: None)

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    client = build_embedding_client(
        _settings(
            backend="api",
            model="custom-embedding",
            dim=512,
        )
    )
    assert isinstance(client, OpenAICompatEmbedder)
    assert seen["base_url"] == "https://api.deepseek.com"
    assert seen["api_key"] == ""


def test_build_embedding_client_api_uses_llm_model_fallback(monkeypatch) -> None:
    seen: dict = {}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            seen.update(kwargs)
            self.embeddings = SimpleNamespace(create=lambda **kwargs: None)

    monkeypatch.setattr("openai.OpenAI", FakeOpenAI)
    client = build_embedding_client(
        Settings(
            data_dir=Path("."),
            config_path=Path("."),
            llm_base_url="https://custom.example/v1",
            llm_model="deepseek-chat",
            embedding_backend="api",
            embedding_model="",
        )
    )
    assert isinstance(client, OpenAICompatEmbedder)
    assert client._model == "deepseek-chat"


def test_build_embedding_client_unknown_backend_reports_config_error() -> None:
    with pytest.raises(NovelError) as info:
        build_embedding_client(_settings(backend="remote"))
    assert info.value.code is ErrorCode.CONFIG_ERROR


def _cosine(first: list[float], second: list[float]) -> float:
    return sum(a * b for a, b in zip(first, second, strict=True))
