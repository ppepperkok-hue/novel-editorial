import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import has_proactive_message, list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.llm.client import LLMClient, LLMMessage, LLMResult, MockLLMClient
from novel_editorial.store.db import DB, workspace_db_path

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "对话之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def test_talk_send_records_author_reply_and_proactive(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["talk", "send", workspace_id, "我们写一个侦探故事"])
    assert result.exit_code == 0, result.output
    assert f"{'作者'}: 我们写一个侦探故事" in result.output
    assert "总编: （模拟回复）" in result.output
    assert "责编: 我想先确认一下" in result.output

    settings = load_settings()
    db = DB(settings)
    messages = list_messages(db, workspace_id)
    assert len(messages) == 4
    assert messages[0].role == "author"
    assert messages[1].role == "agent" and messages[1].actor == "总编"
    mood_payload = json.loads(messages[2].payload)
    assert mood_payload["kind"] == "mood_change"
    proactive_payload = json.loads(messages[3].payload)
    assert proactive_payload["initiator"] == "agent"
    assert has_proactive_message(db, workspace_id)


def test_talk_send_routes_at_mention(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["talk", "send", workspace_id, "@写手 写一段开场"])
    assert result.exit_code == 0, result.output
    assert "写手: （模拟回复）" in result.output


def test_talk_send_routes_at_mention_with_cjk_punctuation(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["talk", "send", workspace_id, "@写手，写一段雨夜开场"])
    assert result.exit_code == 0, result.output
    assert "写手: （模拟回复）" in result.output


def test_talk_proactive_happens_only_once(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    runner.invoke(app, ["talk", "send", workspace_id, "第一句"])
    runner.invoke(app, ["talk", "send", workspace_id, "第二句"])

    settings = load_settings()
    db = DB(settings)
    messages = list_messages(db, workspace_id)
    proactive = [m for m in messages if json.loads(m.payload).get("initiator") == "agent"]
    assert len(proactive) == 1


def test_talk_send_unknown_alias(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["talk", "send", workspace_id, "@主编大人 你好"])
    assert result.exit_code == 2
    assert "unknown partner alias" in result.output


def test_talk_send_failure_leaves_no_messages(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)

    result = runner.invoke(app, ["talk", "send", workspace_id, "@主编大人 你好"])
    assert result.exit_code == 2
    assert list_messages(db, workspace_id) == []


class _RaisingLLMClient(LLMClient):
    def complete(self, messages: list[LLMMessage]) -> LLMResult:
        raise NovelError(ErrorCode.LLM_ERROR, "boom")


def test_talk_send_llm_failure_leaves_no_messages(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: _RaisingLLMClient(),
    )
    settings = load_settings()
    db = DB(settings)

    result = runner.invoke(app, ["talk", "send", workspace_id, "正常消息"])
    assert result.exit_code == 1
    assert list_messages(db, workspace_id) == []


def test_talk_upgrades_pre_migration_workspace(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    db = DB(settings)
    path = workspace_db_path(settings, workspace_id)
    connection = sqlite3.connect(path)
    tables = [
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT IN ('agents', 'workspaces', 'alembic_version')"
        )
    ]
    for table in tables:
        connection.execute(f"DROP TABLE IF EXISTS {table}")
    for column in (
        "values",
        "aesthetic",
        "emotion_baseline",
        "work_habits",
            "weaknesses",
            "relationship_presets",
            "private_motive",
            "mood",
        ):
        connection.execute(f'ALTER TABLE agents DROP COLUMN "{column}"')
    connection.execute("DELETE FROM alembic_version")
    connection.execute("INSERT INTO alembic_version (version_num) VALUES ('3b05b83f8953')")
    connection.commit()
    connection.close()

    result = runner.invoke(app, ["talk", "send", workspace_id, "升级后能聊"])
    assert result.exit_code == 0, result.output
    assert len(list_messages(db, workspace_id)) == 4

    with db.workspace_session(workspace_id) as session:
        from novel_editorial.store.models import Agent

        writer = session.query(Agent).filter_by(workspace_id=workspace_id, role="writer").first()
        assert writer is not None
        assert writer.values
        assert writer.private_motive
        assert writer.mood == "平静"


def test_proactive_question_survives_rebuttal(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )
    created = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    draft_id = created.output.split()[1]
    runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "责编", "--content", "退稿：钩子不成立"],
    )
    runner.invoke(app, ["draft", "revise", draft_id, "--reason", "重写铺垫"])

    result = runner.invoke(app, ["talk", "send", workspace_id, "继续聊这个故事"])
    assert result.exit_code == 0, result.output
    assert "责编: 我想先确认一下" in result.output
