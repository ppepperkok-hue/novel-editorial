from types import SimpleNamespace
from typing import Any

import pytest
from openai import APIConnectionError, AuthenticationError, RateLimitError

from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.llm.client import (
    LLMMessage,
    MockLLMClient,
    OpenAICompatClient,
    build_client,
)


def _client() -> OpenAICompatClient:
    return OpenAICompatClient(
        api_key="sk-test",
        base_url="https://api.deepseek.com",
        model="deepseek-chat",
    )


def _fake_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def _fake_status_error(exc_type, status_code: int) -> Exception:
    response = SimpleNamespace(status_code=status_code, headers={}, request=SimpleNamespace())
    return exc_type("boom", response=response, body=None)


def test_openai_compat_client_success(monkeypatch) -> None:
    client = _client()
    monkeypatch.setattr(
        client._client.chat.completions,
        "create",
        lambda **kwargs: _fake_response("你好，我是回复"),
    )
    result = client.complete([LLMMessage(role="user", content="你好")])
    assert result.content == "你好，我是回复"


def test_openai_compat_client_auth_error(monkeypatch) -> None:
    client = _client()
    monkeypatch.setattr(
        client._client.chat.completions,
        "create",
        lambda **kwargs: (_ for _ in ()).throw(
            _fake_status_error(AuthenticationError, 401)
        ),
    )
    with pytest.raises(NovelError) as exc_info:
        client.complete([LLMMessage(role="user", content="hi")])
    assert exc_info.value.code == ErrorCode.LLM_ERROR
    assert "authentication" in exc_info.value.context["error"]


def test_openai_compat_client_rate_limit(monkeypatch) -> None:
    client = _client()
    monkeypatch.setattr(
        client._client.chat.completions,
        "create",
        lambda **kwargs: (_ for _ in ()).throw(
            _fake_status_error(RateLimitError, 429)
        ),
    )
    with pytest.raises(NovelError) as exc_info:
        client.complete([LLMMessage(role="user", content="hi")])
    assert exc_info.value.code == ErrorCode.LLM_ERROR
    assert "rate_limit" in exc_info.value.context["error"]


def test_openai_compat_client_connection_error(monkeypatch) -> None:
    client = _client()
    request: Any = SimpleNamespace(method="POST", url="https://api.deepseek.com")
    monkeypatch.setattr(
        client._client.chat.completions,
        "create",
        lambda **kwargs: (_ for _ in ()).throw(
            APIConnectionError(message="boom", request=request)
        ),
    )
    with pytest.raises(NovelError) as exc_info:
        client.complete([LLMMessage(role="user", content="hi")])
    assert exc_info.value.code == ErrorCode.LLM_ERROR
    assert "connection" in exc_info.value.context["error"]


def test_build_client_without_key_returns_mock() -> None:
    settings = load_settings({})
    assert isinstance(build_client(settings), MockLLMClient)


def test_build_client_with_key_returns_real() -> None:
    settings = load_settings({"NOVEL_LLM_API_KEY": "sk-test"})
    assert isinstance(build_client(settings), OpenAICompatClient)
