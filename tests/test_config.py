from pathlib import Path

import pytest

from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError


def test_defaults() -> None:
    settings = load_settings({})
    assert settings.llm_base_url == "https://api.deepseek.com"
    assert settings.llm_model == "deepseek-chat"
    assert settings.llm_api_key is None
    assert settings.quality_threshold == 8


def test_env_overrides() -> None:
    settings = load_settings(
        {
            "NOVEL_LLM_API_KEY": "sk-test",
            "NOVEL_LLM_MODEL": "custom-model",
            "NOVEL_DATA_DIR": "C:\\tmp\\novel-data",
        }
    )
    assert settings.llm_api_key == "sk-test"
    assert settings.llm_model == "custom-model"
    assert str(settings.data_dir) == "C:\\tmp\\novel-data"


def test_proactive_defaults() -> None:
    settings = load_settings({})
    assert settings.proactive_enabled is True
    assert settings.proactive_max_per_agent == 3


def test_proactive_env_overrides(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_PROACTIVE_ENABLED": "false",
            "NOVEL_PROACTIVE_MAX_PER_AGENT": "7",
        }
    )
    assert settings.proactive_enabled is False
    assert settings.proactive_max_per_agent == 7


def test_proactive_toml_overrides(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\nproactive_enabled = false\nproactive_max_per_agent = 5\n",
        encoding="utf-8",
    )
    settings = load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert settings.proactive_enabled is False
    assert settings.proactive_max_per_agent == 5


def test_proactive_env_beats_toml(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\nproactive_enabled = false\nproactive_max_per_agent = 5\n",
        encoding="utf-8",
    )
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_PROACTIVE_ENABLED": "true",
            "NOVEL_PROACTIVE_MAX_PER_AGENT": "9",
        }
    )
    assert settings.proactive_enabled is True
    assert settings.proactive_max_per_agent == 9


def test_invalid_proactive_values_report_config_error(tmp_path: Path) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                "NOVEL_PROACTIVE_ENABLED": "maybe",
            }
        )
    assert info.value.code == ErrorCode.CONFIG_ERROR

    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                "NOVEL_PROACTIVE_MAX_PER_AGENT": "high",
            }
        )
    assert info.value.code == ErrorCode.CONFIG_ERROR


def test_negative_proactive_max_reports_config_error(tmp_path: Path) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                "NOVEL_PROACTIVE_MAX_PER_AGENT": "-1",
            }
        )
    assert info.value.code == ErrorCode.CONFIG_ERROR

    (tmp_path / "config.toml").write_text(
        "[defaults]\nproactive_max_per_agent = -1\n",
        encoding="utf-8",
    )
    with pytest.raises(NovelError) as info:
        load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert info.value.code == ErrorCode.CONFIG_ERROR


def test_zero_proactive_max_is_allowed(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_PROACTIVE_MAX_PER_AGENT": "0",
        }
    )
    assert settings.proactive_max_per_agent == 0
