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


def test_memory_config_defaults() -> None:
    settings = load_settings({})
    assert settings.memory_decay_per_day == 5
    assert settings.memory_rehearsal_boost == 25
    assert settings.memory_archive_threshold == 20


def test_memory_config_toml_overrides(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\n"
        "memory_decay_per_day = 7\n"
        "memory_rehearsal_boost = 30\n"
        "memory_archive_threshold = 15\n",
        encoding="utf-8",
    )
    settings = load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert settings.memory_decay_per_day == 7
    assert settings.memory_rehearsal_boost == 30
    assert settings.memory_archive_threshold == 15


def test_memory_config_env_overrides(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_MEMORY_DECAY_PER_DAY": "9",
            "NOVEL_MEMORY_REHEARSAL_BOOST": "40",
            "NOVEL_MEMORY_ARCHIVE_THRESHOLD": "12",
        }
    )
    assert settings.memory_decay_per_day == 9
    assert settings.memory_rehearsal_boost == 40
    assert settings.memory_archive_threshold == 12


def test_memory_config_env_beats_toml(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\n"
        "memory_decay_per_day = 7\n"
        "memory_rehearsal_boost = 30\n"
        "memory_archive_threshold = 15\n",
        encoding="utf-8",
    )
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_MEMORY_DECAY_PER_DAY": "9",
            "NOVEL_MEMORY_REHEARSAL_BOOST": "40",
            "NOVEL_MEMORY_ARCHIVE_THRESHOLD": "12",
        }
    )
    assert settings.memory_decay_per_day == 9
    assert settings.memory_rehearsal_boost == 40
    assert settings.memory_archive_threshold == 12


@pytest.mark.parametrize(
    "env_key",
    [
        "NOVEL_MEMORY_DECAY_PER_DAY",
        "NOVEL_MEMORY_REHEARSAL_BOOST",
        "NOVEL_MEMORY_ARCHIVE_THRESHOLD",
    ],
)
def test_invalid_memory_config_values_report_config_error(
    tmp_path: Path, env_key: str
) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                env_key: "high",
            }
        )
    assert info.value.code == ErrorCode.CONFIG_ERROR


@pytest.mark.parametrize(
    "env_key",
    [
        "NOVEL_MEMORY_DECAY_PER_DAY",
        "NOVEL_MEMORY_REHEARSAL_BOOST",
        "NOVEL_MEMORY_ARCHIVE_THRESHOLD",
    ],
)
def test_negative_memory_config_values_report_config_error(
    tmp_path: Path, env_key: str
) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                env_key: "-1",
            }
        )
    assert info.value.code == ErrorCode.CONFIG_ERROR


def test_memory_archive_threshold_over_100_reports_config_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                "NOVEL_MEMORY_ARCHIVE_THRESHOLD": "101",
            }
        )
    assert info.value.code == ErrorCode.CONFIG_ERROR

    (tmp_path / "config.toml").write_text(
        "[defaults]\nmemory_archive_threshold = 101\n",
        encoding="utf-8",
    )
    with pytest.raises(NovelError) as info:
        load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert info.value.code == ErrorCode.CONFIG_ERROR


def test_zero_memory_config_values_are_allowed(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_MEMORY_DECAY_PER_DAY": "0",
            "NOVEL_MEMORY_REHEARSAL_BOOST": "0",
            "NOVEL_MEMORY_ARCHIVE_THRESHOLD": "0",
        }
    )
    assert settings.memory_decay_per_day == 0
    assert settings.memory_rehearsal_boost == 0
    assert settings.memory_archive_threshold == 0
