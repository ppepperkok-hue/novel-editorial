import re

import pytest

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")


@pytest.fixture
def plain_cli_text():
    """Strip ANSI escapes from captured CLI output.

    GitHub Actions exports ``GITHUB_ACTIONS``, so Typer/Rich force a colour
    terminal even while pytest captures stdout. A rendered option name then
    reaches the test as separate styled spans (``"\\x1b[1m-"`` followed by
    ``"\\x1b[1m-template"``) and is no longer a contiguous ``--template``.
    Stripping the escapes restores the text a user actually reads, so help
    assertions keep checking option names instead of Rich styling.
    """

    def _plain(text: str) -> str:
        return _ANSI_ESCAPE.sub("", text)

    return _plain


@pytest.fixture(autouse=True)
def _force_mock_llm(monkeypatch) -> None:
    """Pin every test to the mock LLM regardless of local environment."""
    monkeypatch.delenv("NOVEL_LLM_API_KEY", raising=False)
