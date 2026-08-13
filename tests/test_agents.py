from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "简档之书"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def test_agents_show_lists_full_profiles(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["agents", "show", workspace_id])
    assert result.exit_code == 0, result.output
    for name in ("总编", "责编", "写手", "审稿"):
        assert name in result.output
    assert "性格" in result.output
    assert "立场" in result.output


def test_agents_show_missing_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["agents", "show", "nope"])
    assert result.exit_code == 1
    assert "workspace not found" in result.output
