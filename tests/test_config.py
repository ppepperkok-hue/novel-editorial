import tomllib
from pathlib import Path

import pytest

from novel_editorial.core.config import (
    WRITABLE_CONFIG_KEYS,
    load_settings,
    set_config_value,
    set_quality_threshold,
)
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


def test_freedom_config_defaults() -> None:
    settings = load_settings({})
    assert settings.freedom_dial == 0.0
    assert settings.freedom_seed == 42
    assert settings.motive_llm_enabled is False


def test_freedom_config_env_overrides(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_FREEDOM_DIAL": "0.7",
            "NOVEL_FREEDOM_SEED": "7",
            "NOVEL_MOTIVE_LLM_ENABLED": "true",
        }
    )
    assert settings.freedom_dial == 0.7
    assert settings.freedom_seed == 7
    assert settings.motive_llm_enabled is True


def test_freedom_config_toml_overrides(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\n"
        "freedom_dial = 0.3\n"
        "freedom_seed = 17\n"
        "motive_llm_enabled = true\n",
        encoding="utf-8",
    )
    settings = load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert settings.freedom_dial == 0.3
    assert settings.freedom_seed == 17
    assert settings.motive_llm_enabled is True


def test_freedom_config_env_beats_toml(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\n"
        "freedom_dial = 0.3\n"
        "freedom_seed = 17\n"
        "motive_llm_enabled = true\n",
        encoding="utf-8",
    )
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_FREEDOM_DIAL": "0.9",
            "NOVEL_FREEDOM_SEED": "99",
            "NOVEL_MOTIVE_LLM_ENABLED": "off",
        }
    )
    assert settings.freedom_dial == 0.9
    assert settings.freedom_seed == 99
    assert settings.motive_llm_enabled is False


@pytest.mark.parametrize("dial", ["high", "-0.1", "1.5", "nan", "inf", "-inf"])
def test_invalid_freedom_dial_env_reports_config_error(
    tmp_path: Path, dial: str
) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                "NOVEL_FREEDOM_DIAL": dial,
            }
        )
    assert info.value.code is ErrorCode.CONFIG_ERROR


@pytest.mark.parametrize("dial", [-0.1, 1.5])
def test_invalid_freedom_dial_toml_reports_config_error(
    tmp_path: Path, dial: float
) -> None:
    (tmp_path / "config.toml").write_text(
        f"[defaults]\nfreedom_dial = {dial}\n",
        encoding="utf-8",
    )
    with pytest.raises(NovelError) as info:
        load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert info.value.code is ErrorCode.CONFIG_ERROR


def test_freedom_dial_bounds_are_inclusive(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_FREEDOM_DIAL": "0",
        }
    )
    assert settings.freedom_dial == 0.0

    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_FREEDOM_DIAL": "1",
        }
    )
    assert settings.freedom_dial == 1.0


@pytest.mark.parametrize("seed", ["high", "3.5"])
def test_invalid_freedom_seed_env_reports_config_error(
    tmp_path: Path, seed: str
) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                "NOVEL_FREEDOM_SEED": seed,
            }
        )
    assert info.value.code is ErrorCode.CONFIG_ERROR


def test_invalid_freedom_seed_toml_reports_config_error(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\nfreedom_seed = 3.5\n",
        encoding="utf-8",
    )
    with pytest.raises(NovelError) as info:
        load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert info.value.code is ErrorCode.CONFIG_ERROR


def test_negative_freedom_seed_is_allowed(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_FREEDOM_SEED": "-5",
        }
    )
    assert settings.freedom_seed == -5


@pytest.mark.parametrize("value", ["maybe", "2"])
def test_invalid_motive_llm_enabled_env_reports_config_error(
    tmp_path: Path, value: str
) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                "NOVEL_MOTIVE_LLM_ENABLED": value,
            }
        )
    assert info.value.code is ErrorCode.CONFIG_ERROR


def test_invalid_motive_llm_enabled_toml_reports_config_error(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        '[defaults]\nmotive_llm_enabled = "maybe"\n',
        encoding="utf-8",
    )
    with pytest.raises(NovelError) as info:
        load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert info.value.code is ErrorCode.CONFIG_ERROR


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


def test_embedding_config_defaults() -> None:
    settings = load_settings({})
    assert settings.embedding_backend == "local"
    assert settings.embedding_model == ""
    assert settings.embedding_dim == 256
    assert settings.embedding_top_k == 5


def test_embedding_config_toml_overrides(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\n"
        'embedding_backend = "api"\n'
        'embedding_model = "text-embedding-3-small"\n'
        "embedding_dim = 512\n"
        "embedding_top_k = 8\n",
        encoding="utf-8",
    )
    settings = load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert settings.embedding_backend == "api"
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.embedding_dim == 512
    assert settings.embedding_top_k == 8


def test_embedding_config_env_overrides(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_EMBEDDING_BACKEND": "api",
            "NOVEL_EMBEDDING_MODEL": "custom-embedding",
            "NOVEL_EMBEDDING_DIM": "128",
            "NOVEL_EMBEDDING_TOP_K": "10",
        }
    )
    assert settings.embedding_backend == "api"
    assert settings.embedding_model == "custom-embedding"
    assert settings.embedding_dim == 128
    assert settings.embedding_top_k == 10


def test_embedding_config_env_beats_toml(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\n"
        'embedding_backend = "api"\n'
        "embedding_dim = 512\n"
        "embedding_top_k = 8\n",
        encoding="utf-8",
    )
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_EMBEDDING_BACKEND": "local",
            "NOVEL_EMBEDDING_DIM": "64",
            "NOVEL_EMBEDDING_TOP_K": "3",
        }
    )
    assert settings.embedding_backend == "local"
    assert settings.embedding_dim == 64
    assert settings.embedding_top_k == 3


def test_invalid_embedding_backend_reports_config_error(tmp_path: Path) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                "NOVEL_EMBEDDING_BACKEND": "remote",
            }
        )
    assert info.value.code is ErrorCode.CONFIG_ERROR

    (tmp_path / "config.toml").write_text(
        '[defaults]\nembedding_backend = "remote"\n',
        encoding="utf-8",
    )
    with pytest.raises(NovelError) as info:
        load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert info.value.code is ErrorCode.CONFIG_ERROR


@pytest.mark.parametrize("env_key", ["NOVEL_EMBEDDING_DIM", "NOVEL_EMBEDDING_TOP_K"])
def test_invalid_embedding_int_values_report_config_error(
    tmp_path: Path, env_key: str
) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                env_key: "high",
            }
        )
    assert info.value.code is ErrorCode.CONFIG_ERROR


@pytest.mark.parametrize("dim", ["31", "4097"])
def test_embedding_dim_out_of_range_reports_config_error(
    tmp_path: Path, dim: str
) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                "NOVEL_EMBEDDING_DIM": dim,
            }
        )
    assert info.value.code is ErrorCode.CONFIG_ERROR

    (tmp_path / "config.toml").write_text(
        f"[defaults]\nembedding_dim = {dim}\n",
        encoding="utf-8",
    )
    with pytest.raises(NovelError) as info:
        load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert info.value.code is ErrorCode.CONFIG_ERROR


@pytest.mark.parametrize("top_k", ["0", "51"])
def test_embedding_top_k_out_of_range_reports_config_error(
    tmp_path: Path, top_k: str
) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                "NOVEL_EMBEDDING_TOP_K": top_k,
            }
        )
    assert info.value.code is ErrorCode.CONFIG_ERROR

    (tmp_path / "config.toml").write_text(
        f"[defaults]\nembedding_top_k = {top_k}\n",
        encoding="utf-8",
    )
    with pytest.raises(NovelError) as info:
        load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert info.value.code is ErrorCode.CONFIG_ERROR


def test_embedding_dim_bounds_are_inclusive(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_EMBEDDING_DIM": "32",
            "NOVEL_EMBEDDING_TOP_K": "1",
        }
    )
    assert settings.embedding_dim == 32
    assert settings.embedding_top_k == 1

    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_EMBEDDING_DIM": "4096",
            "NOVEL_EMBEDDING_TOP_K": "50",
        }
    )
    assert settings.embedding_dim == 4096
    assert settings.embedding_top_k == 50


def test_api_config_defaults() -> None:
    settings = load_settings({})
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8765


def test_api_config_env_overrides(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_API_HOST": "0.0.0.0",
            "NOVEL_API_PORT": "9000",
        }
    )
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 9000


def test_api_config_toml_overrides(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\n"
        'api_host = "0.0.0.0"\n'
        "api_port = 9001\n",
        encoding="utf-8",
    )
    settings = load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 9001


def test_api_config_env_beats_toml(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\n"
        'api_host = "0.0.0.0"\n'
        "api_port = 9001\n",
        encoding="utf-8",
    )
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_API_HOST": "127.0.0.1",
            "NOVEL_API_PORT": "8766",
        }
    )
    assert settings.api_host == "127.0.0.1"
    assert settings.api_port == 8766


@pytest.mark.parametrize("port", ["high", "0", "-1", "65536"])
def test_invalid_api_port_env_reports_config_error(
    tmp_path: Path, port: str
) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                "NOVEL_API_PORT": port,
            }
        )
    assert info.value.code is ErrorCode.CONFIG_ERROR


def test_invalid_api_port_toml_reports_config_error(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\napi_port = 0\n",
        encoding="utf-8",
    )
    with pytest.raises(NovelError) as info:
        load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert info.value.code is ErrorCode.CONFIG_ERROR


def test_api_port_bounds_are_inclusive(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_API_PORT": "1",
        }
    )
    assert settings.api_port == 1

    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_API_PORT": "65535",
        }
    )
    assert settings.api_port == 65535


def test_panel_poll_interval_defaults() -> None:
    settings = load_settings({})
    assert settings.panel_poll_interval == 3


def test_panel_poll_interval_env_overrides(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_PANEL_POLL_INTERVAL": "7",
        }
    )
    assert settings.panel_poll_interval == 7


def test_panel_poll_interval_toml_overrides(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\npanel_poll_interval = 5\n",
        encoding="utf-8",
    )
    settings = load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert settings.panel_poll_interval == 5


def test_panel_poll_interval_env_beats_toml(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text(
        "[defaults]\npanel_poll_interval = 5\n",
        encoding="utf-8",
    )
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_PANEL_POLL_INTERVAL": "9",
        }
    )
    assert settings.panel_poll_interval == 9


@pytest.mark.parametrize("value", ["high", "0", "-1", "301"])
def test_invalid_panel_poll_interval_env_reports_config_error(
    tmp_path: Path, value: str
) -> None:
    with pytest.raises(NovelError) as info:
        load_settings(
            {
                "NOVEL_CONFIG": str(tmp_path / "config.toml"),
                "NOVEL_PANEL_POLL_INTERVAL": value,
            }
        )
    assert info.value.code is ErrorCode.CONFIG_ERROR


@pytest.mark.parametrize("value", [0, -1, 301])
def test_invalid_panel_poll_interval_toml_reports_config_error(
    tmp_path: Path, value: int
) -> None:
    (tmp_path / "config.toml").write_text(
        f"[defaults]\npanel_poll_interval = {value}\n",
        encoding="utf-8",
    )
    with pytest.raises(NovelError) as info:
        load_settings({"NOVEL_CONFIG": str(tmp_path / "config.toml")})
    assert info.value.code is ErrorCode.CONFIG_ERROR


def test_panel_poll_interval_bounds_are_inclusive(tmp_path: Path) -> None:
    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_PANEL_POLL_INTERVAL": "1",
        }
    )
    assert settings.panel_poll_interval == 1

    settings = load_settings(
        {
            "NOVEL_CONFIG": str(tmp_path / "config.toml"),
            "NOVEL_PANEL_POLL_INTERVAL": "300",
        }
    )
    assert settings.panel_poll_interval == 300


def test_set_quality_threshold_creates_missing_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"

    set_quality_threshold(config_path, 12)

    assert config_path.read_text(encoding="utf-8") == (
        "[defaults]\nquality_threshold = 12\n"
    )
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 12


def test_set_quality_threshold_replaces_value_keeping_comments_and_other_keys(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "# top comment\n"
        "[defaults]\n"
        "quality_threshold = 8  # keep me\n"
        "proactive_enabled = false\n"
        "[logging]\n"
        'level = "DEBUG"  # log note\n',
        encoding="utf-8",
    )

    set_quality_threshold(config_path, 15)

    content = config_path.read_text(encoding="utf-8")
    assert "quality_threshold = 15  # keep me" in content
    assert "proactive_enabled = false" in content
    assert "# top comment" in content
    assert '[logging]\nlevel = "DEBUG"  # log note' in content
    assert content.count("quality_threshold") == 1
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 15


def test_set_quality_threshold_appends_defaults_section_when_missing(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[logging]\nlevel = "INFO"\n', encoding="utf-8")

    set_quality_threshold(config_path, 9)

    content = config_path.read_text(encoding="utf-8")
    assert content.endswith("[defaults]\nquality_threshold = 9\n")
    assert 'level = "INFO"' in content
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 9


def test_set_quality_threshold_inserts_key_into_existing_defaults(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "# c\n[defaults]\nproactive_enabled = true\n",
        encoding="utf-8",
    )

    set_quality_threshold(config_path, 11)

    content = config_path.read_text(encoding="utf-8")
    assert "quality_threshold = 11" in content
    assert "proactive_enabled = true" in content
    assert content.startswith("# c\n[defaults]\n")
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 11


def test_set_quality_threshold_rejects_invalid_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[defaults\n", encoding="utf-8")

    with pytest.raises(NovelError) as info:
        set_quality_threshold(config_path, 10)

    assert info.value.code is ErrorCode.CONFIG_ERROR
    assert str(config_path) in info.value.message
    assert config_path.read_text(encoding="utf-8") == "[defaults\n"


def test_set_quality_threshold_is_idempotent(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    set_quality_threshold(config_path, 13)
    first = config_path.read_text(encoding="utf-8")

    set_quality_threshold(config_path, 13)

    assert config_path.read_text(encoding="utf-8") == first
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 13


def test_set_quality_threshold_is_idempotent_on_existing_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\n"
        "quality_threshold = 8  # keep\n"
        "proactive_enabled = false\n"
        "[other]\n"
        'name = "x"\n',
        encoding="utf-8",
    )
    set_quality_threshold(config_path, 18)
    first = config_path.read_text(encoding="utf-8")

    set_quality_threshold(config_path, 18)

    assert config_path.read_text(encoding="utf-8") == first
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 18


def test_set_quality_threshold_write_is_visible_to_load_settings(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\nquality_threshold = 8\n",
        encoding="utf-8",
    )

    set_quality_threshold(config_path, 20)

    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 20


def test_set_quality_threshold_ignores_multiline_string_content(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\n"
        "desc = \"\"\"\n"
        "quality_threshold = 5\n"
        "[foo]\n"
        "\"\"\"\n"
        "proactive_enabled = true\n",
        encoding="utf-8",
    )

    set_quality_threshold(config_path, 15)

    content = config_path.read_text(encoding="utf-8")
    assert content == (
        "[defaults]\n"
        "quality_threshold = 15\n"
        "desc = \"\"\"\n"
        "quality_threshold = 5\n"
        "[foo]\n"
        "\"\"\"\n"
        "proactive_enabled = true\n"
    )
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 15


def test_set_quality_threshold_updates_real_key_around_multiline_string(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\n"
        "quality_threshold = 8\n"
        "desc = \"\"\"\n"
        "quality_threshold = 5\n"
        "[foo]\n"
        "\"\"\"\n",
        encoding="utf-8",
    )

    set_quality_threshold(config_path, 15)

    content = config_path.read_text(encoding="utf-8")
    assert content == (
        "[defaults]\n"
        "quality_threshold = 15\n"
        "desc = \"\"\"\n"
        "quality_threshold = 5\n"
        "[foo]\n"
        "\"\"\"\n"
    )
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 15


def test_set_quality_threshold_ignores_defaults_header_inside_multiline_string(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'desc = """\n'
        "[defaults]\n"
        "quality_threshold = 5\n"
        '"""\n'
        "[other]\n"
        'name = "x"\n',
        encoding="utf-8",
    )

    set_quality_threshold(config_path, 9)

    content = config_path.read_text(encoding="utf-8")
    assert '"""\n[defaults]\nquality_threshold = 5\n"""' in content
    assert content.endswith("[defaults]\nquality_threshold = 9\n")
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 9


def test_set_quality_threshold_ignores_single_quote_multiline_string(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\n"
        "desc = '''\n"
        "quality_threshold = 5\n"
        "'''\n"
        "proactive_enabled = true\n",
        encoding="utf-8",
    )

    set_quality_threshold(config_path, 15)

    content = config_path.read_text(encoding="utf-8")
    assert content == (
        "[defaults]\n"
        "quality_threshold = 15\n"
        "desc = '''\n"
        "quality_threshold = 5\n"
        "'''\n"
        "proactive_enabled = true\n"
    )
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 15


def test_set_quality_threshold_does_not_truncate_section_at_lookalike_header(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\n"
        "desc = \"\"\"\n"
        "[foo]\n"
        "\"\"\"\n"
        "quality_threshold = 8\n",
        encoding="utf-8",
    )

    set_quality_threshold(config_path, 15)

    content = config_path.read_text(encoding="utf-8")
    assert content == (
        "[defaults]\n"
        "desc = \"\"\"\n"
        "[foo]\n"
        "\"\"\"\n"
        "quality_threshold = 15\n"
    )
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 15


def test_set_quality_threshold_same_value_keeps_file_byte_identical(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\nquality_threshold   =   8  # keep\n",
        encoding="utf-8",
    )
    before = config_path.read_bytes()

    set_quality_threshold(config_path, 8)

    assert config_path.read_bytes() == before


def test_set_quality_threshold_preserves_comment_without_space_before_hash(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\nquality_threshold = 8#keep\n",
        encoding="utf-8",
    )

    set_quality_threshold(config_path, 15)

    content = config_path.read_text(encoding="utf-8")
    assert content == "[defaults]\nquality_threshold = 15#keep\n"
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 15


def test_set_quality_threshold_same_value_keeps_no_space_comment(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\nquality_threshold = 8#keep\n",
        encoding="utf-8",
    )
    before = config_path.read_bytes()

    set_quality_threshold(config_path, 8)

    assert config_path.read_bytes() == before


def test_set_quality_threshold_replaces_multiline_value_span(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\n"
        "quality_threshold = [\n"
        "  1, # one\n"
        "  2,\n"
        "]\n",
        encoding="utf-8",
    )

    set_quality_threshold(config_path, 15)

    content = config_path.read_text(encoding="utf-8")
    assert content == "[defaults]\nquality_threshold = 15\n"
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 15


def test_set_quality_threshold_replaces_multiline_string_value(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\n"
        "quality_threshold = \"\"\"\n"
        "8\n"
        "\"\"\"  # keep\n",
        encoding="utf-8",
    )

    set_quality_threshold(config_path, 15)

    content = config_path.read_text(encoding="utf-8")
    assert content == "[defaults]\nquality_threshold = 15  # keep\n"
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 15


def test_set_quality_threshold_keeps_escaped_triple_quote_in_multiline_string(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\n"
        'desc = """a\\"""b"""\n'
        "quality_threshold = 8\n",
        encoding="utf-8",
    )

    set_quality_threshold(config_path, 15)

    content = config_path.read_text(encoding="utf-8")
    assert content == (
        "[defaults]\n"
        'desc = """a\\"""b"""\n'
        "quality_threshold = 15\n"
    )
    tomllib.loads(content)
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 15


def test_set_quality_threshold_replaces_multiline_string_value_with_escaped_triple_quote(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\n"
        'quality_threshold = """\n'
        '8\\"""9\n'
        '"""  # keep\n',
        encoding="utf-8",
    )

    set_quality_threshold(config_path, 15)

    content = config_path.read_text(encoding="utf-8")
    assert content == "[defaults]\nquality_threshold = 15  # keep\n"
    tomllib.loads(content)
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 15


def test_writable_config_keys_whitelist() -> None:
    assert WRITABLE_CONFIG_KEYS == frozenset(
        {
            "quality_threshold",
            "panel_poll_interval",
            "freedom_dial",
            "freedom_seed",
            "proactive_enabled",
            "proactive_max_per_agent",
            "motive_llm_enabled",
        }
    )


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("quality_threshold", 12, 12),
        ("panel_poll_interval", 7, 7),
        ("freedom_dial", 0.5, 0.5),
        ("freedom_seed", -3, -3),
        ("proactive_enabled", False, False),
        ("proactive_max_per_agent", 0, 0),
        ("motive_llm_enabled", True, True),
    ],
)
def test_set_config_value_writes_each_writable_key(
    tmp_path: Path, key: str, value: object, expected: object
) -> None:
    config_path = tmp_path / "config.toml"

    set_config_value(config_path, key, value)

    content = config_path.read_text(encoding="utf-8")
    assert content.startswith("[defaults]\n")
    assert f"{key} = " in content
    tomllib.loads(content)
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert getattr(settings, key) == expected


@pytest.mark.parametrize(
    "key,value,expected",
    [
        ("quality_threshold", "9", 9),
        ("panel_poll_interval", "5", 5),
        ("freedom_dial", "0.25", 0.25),
        ("freedom_seed", "-1", -1),
        ("proactive_max_per_agent", "2", 2),
        ("proactive_enabled", "off", False),
        ("proactive_enabled", "1", True),
        ("motive_llm_enabled", "yes", True),
        ("motive_llm_enabled", "FALSE", False),
    ],
)
def test_set_config_value_accepts_string_forms(
    tmp_path: Path, key: str, value: str, expected: object
) -> None:
    config_path = tmp_path / "config.toml"

    set_config_value(config_path, key, value)

    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert getattr(settings, key) == expected


@pytest.mark.parametrize(
    "key,value",
    [
        ("quality_threshold", -1),
        ("quality_threshold", 3.5),
        ("quality_threshold", "high"),
        ("panel_poll_interval", 0),
        ("panel_poll_interval", 301),
        ("freedom_dial", 2),
        ("freedom_dial", -0.1),
        ("freedom_dial", "nan"),
        ("freedom_seed", "3.5"),
        ("proactive_enabled", "maybe"),
        ("proactive_enabled", 1),
        ("proactive_max_per_agent", -1),
        ("motive_llm_enabled", "2"),
    ],
)
def test_set_config_value_rejects_invalid_values(
    tmp_path: Path, key: str, value: object
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[defaults]\nquality_threshold = 8\n", encoding="utf-8")
    before = config_path.read_bytes()

    with pytest.raises(NovelError) as info:
        set_config_value(config_path, key, value)

    assert info.value.code is ErrorCode.USAGE_ERROR
    assert config_path.read_bytes() == before


@pytest.mark.parametrize(
    "key", ["llm_api_key", "embedding_model", "api_port", "data_dir", "defaults"]
)
def test_set_config_value_rejects_unknown_or_read_only_keys(
    tmp_path: Path, key: str
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[defaults]\nquality_threshold = 8\n", encoding="utf-8")
    before = config_path.read_bytes()

    with pytest.raises(NovelError) as info:
        set_config_value(config_path, key, 1)

    assert info.value.code is ErrorCode.USAGE_ERROR
    assert "config key" in info.value.message
    assert config_path.read_bytes() == before


def test_set_config_value_is_idempotent(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    set_config_value(config_path, "freedom_dial", 0.5)
    first = config_path.read_bytes()

    set_config_value(config_path, "freedom_dial", 0.5)

    assert config_path.read_bytes() == first
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.freedom_dial == 0.5


def test_set_config_value_float_accepts_integer_spelling(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[defaults]\nfreedom_dial = 0\n", encoding="utf-8")
    before = config_path.read_bytes()

    set_config_value(config_path, "freedom_dial", 0.0)

    assert config_path.read_bytes() == before
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.freedom_dial == 0.0


def test_set_config_value_replaces_value_keeping_comments_and_other_keys(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "# top comment\n"
        "[defaults]\n"
        "quality_threshold = 8  # keep me\n"
        "proactive_enabled = false\n"
        "[logging]\n"
        'level = "DEBUG"  # log note\n',
        encoding="utf-8",
    )

    set_config_value(config_path, "quality_threshold", 15)

    content = config_path.read_text(encoding="utf-8")
    assert "quality_threshold = 15  # keep me" in content
    assert "proactive_enabled = false" in content
    assert "# top comment" in content
    assert '[logging]\nlevel = "DEBUG"  # log note' in content
    assert content.count("quality_threshold") == 1
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 15


def test_set_config_value_appends_defaults_section_when_missing(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[logging]\nlevel = "INFO"\n', encoding="utf-8")

    set_config_value(config_path, "freedom_dial", 0.4)

    content = config_path.read_text(encoding="utf-8")
    assert content.endswith("[defaults]\nfreedom_dial = 0.4\n")
    assert 'level = "INFO"' in content
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.freedom_dial == 0.4


def test_set_config_value_rejects_inline_defaults_table(
    tmp_path: Path,
) -> None:
    """An inline ``defaults`` table must never be appended to into invalid TOML."""
    config_path = tmp_path / "config.toml"
    original = "defaults = { quality_threshold = 8 }\n"
    config_path.write_text(original, encoding="utf-8")
    original_bytes = config_path.read_bytes()

    with pytest.raises(NovelError) as exc_info:
        set_config_value(config_path, "quality_threshold", 10)

    assert exc_info.value.code is ErrorCode.CONFIG_ERROR
    assert "convert it to a [defaults] section" in exc_info.value.message
    assert config_path.read_bytes() == original_bytes
    assert tomllib.loads(config_path.read_text(encoding="utf-8")) == {
        "defaults": {"quality_threshold": 8}
    }


@pytest.mark.parametrize(
    "original",
    [
        "defaults = 42\n",
        "defaults.quality_threshold = 8\n",
        '"defaults" = 8\n',
        "'defaults' = 8\n",
    ],
)
def test_set_config_value_rejects_top_level_defaults_assignment(
    tmp_path: Path, original: str
) -> None:
    """Any top-level ``defaults`` assignment conflicts with the appended section."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(original, encoding="utf-8")
    original_bytes = config_path.read_bytes()

    with pytest.raises(NovelError) as exc_info:
        set_config_value(config_path, "quality_threshold", 10)

    assert exc_info.value.code is ErrorCode.CONFIG_ERROR
    assert "convert it to a [defaults] section" in exc_info.value.message
    assert config_path.read_bytes() == original_bytes


def test_set_config_value_allows_subtable_header_under_defaults(
    tmp_path: Path,
) -> None:
    """A ``[defaults.*]`` header stays valid TOML after appending [defaults]."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults.quality]\nthreshold = 8\n", encoding="utf-8"
    )

    set_config_value(config_path, "quality_threshold", 10)

    content = config_path.read_text(encoding="utf-8")
    assert content.startswith("[defaults.quality]\nthreshold = 8\n")
    assert content.endswith("[defaults]\nquality_threshold = 10\n")
    tomllib.loads(content)
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 10


def test_set_config_value_ignores_defaults_key_inside_subtable(
    tmp_path: Path,
) -> None:
    """A ``defaults`` key inside a subtable is not a top-level assignment."""
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults.quality]\ndefaults = 8\nthreshold = 5\n",
        encoding="utf-8",
    )

    set_config_value(config_path, "quality_threshold", 10)

    content = config_path.read_text(encoding="utf-8")
    assert content.endswith("[defaults]\nquality_threshold = 10\n")
    tomllib.loads(content)
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.quality_threshold == 10


def test_set_config_value_rejects_defaults_array_of_tables(
    tmp_path: Path,
) -> None:
    """A ``[[defaults]]`` array of tables must not be appended into invalid TOML."""
    config_path = tmp_path / "config.toml"
    original = "[[defaults]]\nx = 1\n"
    config_path.write_text(original, encoding="utf-8")
    original_bytes = config_path.read_bytes()

    with pytest.raises(NovelError) as exc_info:
        set_config_value(config_path, "quality_threshold", 10)

    assert exc_info.value.code is ErrorCode.CONFIG_ERROR
    assert "rolled back" in exc_info.value.message
    assert config_path.read_bytes() == original_bytes


def test_set_config_value_rejects_escaped_defaults_key(
    tmp_path: Path,
) -> None:
    """An escaped quoted key spelling ``defaults`` must still be refused."""
    config_path = tmp_path / "config.toml"
    original = '"def\\u0061ults" = 1\n'
    config_path.write_text(original, encoding="utf-8")
    original_bytes = config_path.read_bytes()

    with pytest.raises(NovelError) as exc_info:
        set_config_value(config_path, "quality_threshold", 10)

    assert exc_info.value.code is ErrorCode.CONFIG_ERROR
    assert "rolled back" in exc_info.value.message
    assert config_path.read_bytes() == original_bytes


def test_set_config_value_rejects_indented_top_level_dotted_key(
    tmp_path: Path,
) -> None:
    """An indented top-level ``defaults.*`` dotted key is still a conflict."""
    config_path = tmp_path / "config.toml"
    original = "  defaults.foo = 1\n"
    config_path.write_text(original, encoding="utf-8")
    original_bytes = config_path.read_bytes()

    with pytest.raises(NovelError) as exc_info:
        set_config_value(config_path, "quality_threshold", 10)

    assert exc_info.value.code is ErrorCode.CONFIG_ERROR
    assert "convert it to a [defaults] section" in exc_info.value.message
    assert config_path.read_bytes() == original_bytes


def test_set_config_value_inserts_key_into_existing_defaults(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "# c\n[defaults]\nproactive_enabled = true\n",
        encoding="utf-8",
    )

    set_config_value(config_path, "motive_llm_enabled", True)

    content = config_path.read_text(encoding="utf-8")
    assert "motive_llm_enabled = true" in content
    assert "proactive_enabled = true" in content
    assert content.startswith("# c\n[defaults]\n")
    tomllib.loads(content)
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.motive_llm_enabled is True


def test_set_config_value_preserves_quoted_key_spelling(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text('[defaults]\n"freedom_dial" = 0.5\n', encoding="utf-8")

    set_config_value(config_path, "freedom_dial", 0.7)

    content = config_path.read_text(encoding="utf-8")
    assert '"freedom_dial" = 0.7' in content
    assert "freedom_dial = 0.7" not in content
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.freedom_dial == 0.7


def test_set_config_value_ignores_multiline_string_content(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        "[defaults]\n"
        "desc = \"\"\"\n"
        "freedom_dial = 5\n"
        "[foo]\n"
        "\"\"\"\n"
        "proactive_enabled = true\n",
        encoding="utf-8",
    )

    set_config_value(config_path, "freedom_dial", 0.3)

    content = config_path.read_text(encoding="utf-8")
    assert "freedom_dial = 0.3" in content
    assert 'desc = """' in content
    assert "freedom_dial = 5" in content
    tomllib.loads(content)
    settings = load_settings({"NOVEL_CONFIG": str(config_path)})
    assert settings.freedom_dial == 0.3


def test_set_config_value_rejects_invalid_toml(tmp_path: Path) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text("[defaults\n", encoding="utf-8")

    with pytest.raises(NovelError) as info:
        set_config_value(config_path, "quality_threshold", 10)

    assert info.value.code is ErrorCode.CONFIG_ERROR
    assert str(config_path) in info.value.message
    assert config_path.read_text(encoding="utf-8") == "[defaults\n"
