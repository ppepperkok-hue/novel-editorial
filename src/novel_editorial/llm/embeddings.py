"""Embedding abstraction: deterministic local embedder plus OpenAI-compatible API."""

from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

from novel_editorial.core.config import Settings
from novel_editorial.core.errors import ErrorCode, NovelError

DEFAULT_TIMEOUT_SECONDS = 60.0

_VALID_BACKENDS = frozenset({"local", "api"})


class EmbeddingClient(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]: ...


class LocalNGramEmbedder(EmbeddingClient):
    """Deterministic character n-gram (n=1..3) hashing embedder.

    Every n-gram is hashed with sha256 and mapped into one of ``dim`` buckets
    by modulo; bucket counts form the vector, then it is L2-normalized. The
    same text always yields the same vector with zero external dependencies;
    empty text yields the zero vector.
    """

    def __init__(self, dim: int) -> None:
        if dim < 1:
            raise NovelError(
                ErrorCode.CONFIG_ERROR,
                f"invalid embedding dim: {dim}",
            )
        self.dim = dim

    def embed(self, text: str) -> list[float]:
        if not text:
            return [0.0] * self.dim
        counts = [0] * self.dim
        for n in (1, 2, 3):
            for index in range(len(text) - n + 1):
                ngram = text[index : index + n]
                digest = hashlib.sha256(ngram.encode("utf-8")).digest()[:8]
                counts[int.from_bytes(digest, "big") % self.dim] += 1
        norm = math.sqrt(sum(count * count for count in counts))
        if norm == 0:
            return [0.0] * self.dim
        return [count / norm for count in counts]


class OpenAICompatEmbedder(EmbeddingClient):
    """OpenAI-compatible /embeddings client (DeepSeek and similar providers)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        from openai import OpenAI

        self._model = model
        try:
            self._client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
            )
        except Exception as exc:
            raise NovelError(
                ErrorCode.LLM_ERROR,
                "embedding client construction failed",
                context={"error": "unknown"},
            ) from exc

    def embed(self, text: str) -> list[float]:
        from openai import (
            APIConnectionError,
            APITimeoutError,
            AuthenticationError,
            RateLimitError,
        )

        try:
            response = self._client.embeddings.create(
                model=self._model,
                input=text,
            )
        except APITimeoutError as exc:
            raise NovelError(
                ErrorCode.LLM_ERROR,
                "embedding request timed out",
                context={"error": "timeout"},
            ) from exc
        except APIConnectionError as exc:
            raise NovelError(
                ErrorCode.LLM_ERROR,
                "embedding connection failed",
                context={"error": "connection"},
            ) from exc
        except AuthenticationError as exc:
            raise NovelError(
                ErrorCode.LLM_ERROR,
                "embedding authentication failed",
                context={"error": "authentication"},
            ) from exc
        except RateLimitError as exc:
            raise NovelError(
                ErrorCode.LLM_ERROR,
                "embedding rate limit exceeded",
                context={"error": "rate_limit"},
            ) from exc
        except Exception as exc:
            raise NovelError(
                ErrorCode.LLM_ERROR,
                "embedding request failed",
                context={"error": "unknown"},
            ) from exc
        try:
            return list(response.data[0].embedding)
        except (AttributeError, IndexError, TypeError) as exc:
            raise NovelError(
                ErrorCode.LLM_ERROR,
                "embedding response malformed",
                context={"error": "malformed"},
            ) from exc


def build_embedding_client(settings: Settings) -> EmbeddingClient:
    """Dispatch to the configured embedding backend."""
    if settings.embedding_backend == "local":
        return LocalNGramEmbedder(settings.embedding_dim)
    if settings.embedding_backend == "api":
        if not settings.embedding_model:
            raise NovelError(
                ErrorCode.CONFIG_ERROR,
                "embedding_model must be explicitly configured when "
                "embedding_backend is 'api'",
            )
        return OpenAICompatEmbedder(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key or "",
            model=settings.embedding_model,
        )
    raise NovelError(
        ErrorCode.CONFIG_ERROR,
        f"invalid embedding backend: {settings.embedding_backend!r} "
        f"(expected one of: {', '.join(sorted(_VALID_BACKENDS))})",
    )
