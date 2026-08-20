from pathlib import Path

import pytest

from novel_editorial.core.config import load_settings, set_quality_threshold
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
