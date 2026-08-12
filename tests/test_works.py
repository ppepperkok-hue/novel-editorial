import re
from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.store.db import DB, global_db_path
from novel_editorial.store.models import Agent

runner = CliRunner()


def test_works_create_and_list(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["works", "create", "测试之书", "--genre", "网文"])
    assert result.exit_code == 0, result.output
    assert "created workspace" in result.output

    settings = load_settings()
    assert global_db_path(settings).exists()

    result = runner.invoke(app, ["works", "list"])
    assert result.exit_code == 0
    assert "测试之书" in result.output


def test_workspace_band_seeded(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["works", "create", "第二本", "--genre", "同人"])
    assert result.exit_code == 0, result.output

    settings = load_settings()
    db = DB(settings)
    works_dir = settings.data_dir / "works"
    assert works_dir.exists()
    workspace_dir = next(works_dir.iterdir())
    assert (workspace_dir / "data.db").exists()
    with db.workspace_session(workspace_dir.name) as session:
        agents = session.query(Agent).all()
        assert len(agents) == 4


def test_works_show(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    create = runner.invoke(app, ["works", "create", "展示之书", "--genre", "短篇"])
    assert create.exit_code == 0, create.output
    match = re.search(r"created workspace (\w+):", create.output)
    assert match is not None
    workspace_id = match.group(1)

    result = runner.invoke(app, ["works", "show", workspace_id])
    assert result.exit_code == 0, result.output
    assert "展示之书" in result.output
    assert "总编" in result.output
    assert "写手" in result.output


def test_works_show_missing_returns_business_error(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    result = runner.invoke(app, ["works", "show", "does-not-exist"])
    assert result.exit_code == 1
    assert "workspace not found" in result.output
