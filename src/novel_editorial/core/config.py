"""Configuration loading: env vars + optional TOML overrides."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from novel_editorial.core.errors import ErrorCode, NovelError

_TRUE_ENABLED_VALUES = frozenset({"1", "true", "yes", "on"})
_FALSE_ENABLED_VALUES = frozenset({"0", "false", "no", "off"})


def _parse_enabled(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in _TRUE_ENABLED_VALUES:
        return True
    if lowered in _FALSE_ENABLED_VALUES:
        return False
    raise NovelError(ErrorCode.CONFIG_ERROR, f"invalid proactive enabled: {value!r}")


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    config_path: Path
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    log_level: str = "INFO"
    quality_threshold: int = 8
    proactive_enabled: bool = True
    proactive_max_per_agent: int = 3
    defaults: dict = field(default_factory=dict)


def _read_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    env = env if env is not None else os.environ
    data_dir = Path(env.get("NOVEL_DATA_DIR", "./data"))
    config_path = Path(env.get("NOVEL_CONFIG", "./config.toml"))
    config = _read_toml(config_path)
    defaults = config.get("defaults", {})
    default_threshold = defaults.get("quality_threshold", 8)
    threshold_value = env.get("NOVEL_QUALITY_THRESHOLD", str(default_threshold))
    try:
        quality_threshold = int(threshold_value)
    except (TypeError, ValueError) as exc:
        raise NovelError(
            ErrorCode.CONFIG_ERROR,
            f"invalid quality threshold: {threshold_value!r}",
        ) from exc
    default_proactive_enabled = defaults.get("proactive_enabled", True)
    enabled_value = env.get("NOVEL_PROACTIVE_ENABLED", str(default_proactive_enabled))
    proactive_enabled = _parse_enabled(enabled_value)
    default_proactive_max = defaults.get("proactive_max_per_agent", 3)
    max_value = env.get("NOVEL_PROACTIVE_MAX_PER_AGENT", str(default_proactive_max))
    try:
        proactive_max_per_agent = int(max_value)
    except (TypeError, ValueError) as exc:
        raise NovelError(
            ErrorCode.CONFIG_ERROR,
            f"invalid proactive max per agent: {max_value!r}",
        ) from exc
    if proactive_max_per_agent < 0:
        raise NovelError(
            ErrorCode.CONFIG_ERROR,
            f"invalid proactive max per agent: {max_value!r}",
        )
    return Settings(
        data_dir=data_dir,
        config_path=config_path,
        llm_api_key=env.get("NOVEL_LLM_API_KEY") or None,
        llm_base_url=env.get("NOVEL_LLM_BASE_URL", "https://api.deepseek.com"),
        llm_model=env.get("NOVEL_LLM_MODEL", "deepseek-chat"),
        log_level=env.get("NOVEL_LOG_LEVEL", "INFO"),
        quality_threshold=quality_threshold,
        proactive_enabled=proactive_enabled,
        proactive_max_per_agent=proactive_max_per_agent,
        defaults=defaults,
    )
