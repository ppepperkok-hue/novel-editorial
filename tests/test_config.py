from novel_editorial.core.config import load_settings


def test_defaults() -> None:
    settings = load_settings({})
    assert settings.llm_base_url == "https://api.deepseek.com"
    assert settings.llm_model == "deepseek-chat"
    assert settings.llm_api_key is None


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
