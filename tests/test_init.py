from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app

runner = CliRunner()


@pytest.mark.smoke
def test_init_is_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))

    first = runner.invoke(app, ["init"])
    assert first.exit_code == 0, first.output
    assert (tmp_path / "config.toml").exists()

    second = runner.invoke(app, ["init"])
    assert second.exit_code == 0, second.output
    assert "config exists" in second.output


def test_init_generates_config_template(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))

    result = runner.invoke(app, ["init"])
    assert result.exit_code == 0, result.output
    content = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert "[defaults]" in content
