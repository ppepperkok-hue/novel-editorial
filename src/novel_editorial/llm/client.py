"""Unified LLM client: OpenAI-compatible provider plus deterministic mock."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import cast

from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    OpenAI,
    RateLimitError,
)
from openai.types.chat import ChatCompletionMessageParam

from novel_editorial.core.config import Settings
from novel_editorial.core.errors import ErrorCode, NovelError

DEFAULT_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


@dataclass(frozen=True)
class LLMResult:
    content: str
    raw: object | None = None


class LLMClient(ABC):
    @abstractmethod
    def complete(self, messages: list[LLMMessage]) -> LLMResult: ...


class MockLLMClient(LLMClient):
    """Deterministic client used for tests and demos without a real key."""

    def __init__(self, reply: str = "（模拟回复）") -> None:
        self.reply = reply

    def complete(self, messages: list[LLMMessage]) -> LLMResult:
        return LLMResult(content=self.reply)


class OpenAICompatClient(LLMClient):
    """OpenAI-compatible chat client (DeepSeek and similar providers)."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._model = model
        self._client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=timeout,
        )

    def complete(self, messages: list[LLMMessage]) -> LLMResult:
        try:
            payload = cast(
                list[ChatCompletionMessageParam],
                [{"role": m.role, "content": m.content} for m in messages],
            )
            response = self._client.chat.completions.create(
                model=self._model,
                messages=payload,
            )
        except APITimeoutError as exc:
            raise NovelError(
                ErrorCode.LLM_ERROR, "LLM request timed out", context={"error": "timeout"}
            ) from exc
        except APIConnectionError as exc:
            raise NovelError(
                ErrorCode.LLM_ERROR, "LLM connection failed", context={"error": "connection"}
            ) from exc
        except AuthenticationError as exc:
            raise NovelError(
                ErrorCode.LLM_ERROR,
                "LLM authentication failed",
                context={"error": "authentication"},
            ) from exc
        except RateLimitError as exc:
            raise NovelError(
                ErrorCode.LLM_ERROR, "LLM rate limit exceeded", context={"error": "rate_limit"}
            ) from exc
        except Exception as exc:
            raise NovelError(
                ErrorCode.LLM_ERROR, "LLM request failed", context={"error": "unknown"}
            ) from exc
        content = response.choices[0].message.content or ""
        return LLMResult(content=content, raw=response)


def build_client(settings: Settings) -> LLMClient:
    if settings.llm_api_key:
        return OpenAICompatClient(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
            model=settings.llm_model,
        )
    return MockLLMClient()
