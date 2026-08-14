from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB
from novel_editorial.store.models import Draft

runner = CliRunner()


@pytest.mark.smoke
def test_demo_runs_full_loop(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))

    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0, result.output
    assert "workspace:" in result.output
    assert "draft:" in result.output
    assert "quality passed: True" in result.output
    assert "draft accepted" in result.output

    workspace_id = result.output.split()[1]
    settings = load_settings()
    db = DB(settings)

    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).first()
        assert draft is not None
        assert draft.status == "accepted"

    messages = list_messages(db, workspace_id)
    assert len(messages) == 5
    assert messages[0].role == "author"
    assert messages[1].role == "agent" and messages[1].actor == "总编"
    mood_changes = [m for m in messages if '"kind": "mood_change"' in m.payload]
    assert len(mood_changes) == 2
    proactive = [m for m in messages if '"initiator": "agent"' in m.payload]
    assert len(proactive) == 1
    assert "我想先确认一下" in proactive[0].content

    log_result = runner.invoke(app, ["log", workspace_id])
    assert log_result.exit_code == 0, log_result.output
    assert "== 对话 ==" in log_result.output
    assert "== 草稿 ==" in log_result.output
    assert "accepted" in log_result.output


def test_demo_is_repeatable(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    first = runner.invoke(app, ["demo"])
    second = runner.invoke(app, ["demo"])
    assert first.exit_code == 0
    assert second.exit_code == 0


def test_demo_handles_quality_gate_failure(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    monkeypatch.setattr(
        "novel_editorial.core.demo.build_client",
        lambda settings: MockLLMClient(reply="月光宛如薄纱，悄然洒落，他静静地凝视着远方。"),
    )

    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0, result.output
    assert "quality passed: False" in result.output
    assert "rejected by the quality gate" in result.output

    workspace_id = result.output.split()[1]
    settings = load_settings()
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).first()
        assert draft is not None
        assert draft.status == "rejected"
