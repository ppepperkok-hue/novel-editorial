from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.store.db import DB
from novel_editorial.store.models import Draft, Message, StyleAnchor

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch, title: str) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", title, "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def test_workspaces_are_isolated(tmp_path: Path, monkeypatch) -> None:
    workspace_a = _create_workspace(tmp_path, monkeypatch, "甲书")
    workspace_b = _create_workspace(tmp_path, monkeypatch, "乙书")

    runner.invoke(app, ["talk", "send", workspace_a, "甲书专属讨论"])
    runner.invoke(
        app,
        ["style", "set", workspace_a, "--description", "甲书专属风格", "--forbidden", "甲词"],
    )
    created = runner.invoke(app, ["draft", "generate", workspace_a, "--title", "甲书第一章"])
    draft_a = created.output.split()[1]
    runner.invoke(
        app,
        ["review", "add", draft_a, "--from", "作者", "--content", "甲书意见"],
    )
    runner.invoke(app, ["decision", "accept", draft_a])

    settings = load_settings()
    db = DB(settings)

    with db.workspace_session(workspace_b) as session:
        messages_b = session.query(Message).all()
        assert messages_b == []
        draft = session.query(Draft).filter_by(id=draft_a).first()
        assert draft is None
        anchor = session.query(StyleAnchor).filter_by(workspace_id=workspace_b).first()
        assert anchor is None or not anchor.description

    talk_b = runner.invoke(app, ["talk", "list", workspace_b])
    assert talk_b.exit_code == 0
    assert "甲书专属讨论" not in talk_b.output

    drafts_b = runner.invoke(app, ["draft", "list", workspace_b])
    assert drafts_b.exit_code == 0
    assert "甲书第一章" not in drafts_b.output

    pack_b = runner.invoke(app, ["memory", "pack", workspace_b])
    assert pack_b.exit_code == 0
    assert "甲书专属风格" not in pack_b.output
    assert "甲书" not in pack_b.output

    messages_a = list_messages(db, workspace_a)
    assert any("甲书专属讨论" in m.content for m in messages_a)
