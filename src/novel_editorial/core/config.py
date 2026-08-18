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


def _load_int_setting(
    env: Mapping[str, str],
    defaults: dict,
    *,
    env_key: str,
    toml_key: str,
    fallback: int,
    label: str,
    max_value: int | None = None,
) -> int:
    """Read one integer setting: TOML default first, then env override."""
    default_value = defaults.get(toml_key, fallback)
    raw_value = env.get(env_key, str(default_value))
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise NovelError(
            ErrorCode.CONFIG_ERROR,
            f"invalid {label}: {raw_value!r}",
        ) from exc
    if value < 0 or (max_value is not None and value > max_value):
        raise NovelError(
            ErrorCode.CONFIG_ERROR,
            f"invalid {label}: {raw_value!r}",
        )
    return value


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    config_path: Path
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    log_level: str = "INFO"
    quality_threshold: int = 8
    memory_decay_per_day: int = 5
    memory_rehearsal_boost: int = 25
    memory_archive_threshold: int = 20
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
    memory_decay_per_day = _load_int_setting(
        env,
        defaults,
        env_key="NOVEL_MEMORY_DECAY_PER_DAY",
        toml_key="memory_decay_per_day",
        fallback=5,
        label="memory decay per day",
    )
    memory_rehearsal_boost = _load_int_setting(
        env,
        defaults,
        env_key="NOVEL_MEMORY_REHEARSAL_BOOST",
        toml_key="memory_rehearsal_boost",
        fallback=25,
        label="memory rehearsal boost",
    )
    memory_archive_threshold = _load_int_setting(
        env,
        defaults,
        env_key="NOVEL_MEMORY_ARCHIVE_THRESHOLD",
        toml_key="memory_archive_threshold",
        fallback=20,
        label="memory archive threshold",
        max_value=100,
    )
    return Settings(
        data_dir=data_dir,
        config_path=config_path,
        llm_api_key=env.get("NOVEL_LLM_API_KEY") or None,
        llm_base_url=env.get("NOVEL_LLM_BASE_URL", "https://api.deepseek.com"),
        llm_model=env.get("NOVEL_LLM_MODEL", "deepseek-chat"),
        log_level=env.get("NOVEL_LOG_LEVEL", "INFO"),
        quality_threshold=quality_threshold,
        memory_decay_per_day=memory_decay_per_day,
        memory_rehearsal_boost=memory_rehearsal_boost,
        memory_archive_threshold=memory_archive_threshold,
        proactive_enabled=proactive_enabled,
        proactive_max_per_agent=proactive_max_per_agent,
        defaults=defaults,
    )
