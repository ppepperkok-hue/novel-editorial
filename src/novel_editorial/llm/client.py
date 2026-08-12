"""Unified LLM client. Real provider lands in U5; mock mode works today."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from novel_editorial.core.config import Settings
from novel_editorial.core.errors import ErrorCode, NovelError


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


def build_client(settings: Settings) -> LLMClient:
    if not settings.llm_api_key:
        return MockLLMClient()
    raise NovelError(ErrorCode.LLM_ERROR, "real LLM client is not implemented yet (U5)")
