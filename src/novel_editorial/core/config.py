"""Configuration loading: env vars + optional TOML overrides."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from novel_editorial.core.errors import ErrorCode, NovelError


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    config_path: Path
    llm_api_key: str | None = None
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"
    log_level: str = "INFO"
    quality_threshold: int = 8
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
    return Settings(
        data_dir=data_dir,
        config_path=config_path,
        llm_api_key=env.get("NOVEL_LLM_API_KEY") or None,
        llm_base_url=env.get("NOVEL_LLM_BASE_URL", "https://api.deepseek.com"),
        llm_model=env.get("NOVEL_LLM_MODEL", "deepseek-chat"),
        log_level=env.get("NOVEL_LOG_LEVEL", "INFO"),
        quality_threshold=quality_threshold,
        defaults=defaults,
    )
