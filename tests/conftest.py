import pytest


@pytest.fixture(autouse=True)
def _force_mock_llm(monkeypatch) -> None:
    """Pin every test to the mock LLM regardless of local environment."""
    monkeypatch.delenv("NOVEL_LLM_API_KEY", raising=False)
