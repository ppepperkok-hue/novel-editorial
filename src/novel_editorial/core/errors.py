"""Error hierarchy with stable codes."""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    CONFIG_ERROR = "config_error"
    DB_ERROR = "db_error"
    NOT_FOUND = "not_found"
    USAGE_ERROR = "usage_error"
    LLM_ERROR = "llm_error"
    QUALITY_ERROR = "quality_error"
    INTERNAL = "internal"


class NovelError(Exception):
    """Base error carrying a stable code and context."""

    def __init__(self, code: ErrorCode, message: str, *, context: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.context = context or {}
