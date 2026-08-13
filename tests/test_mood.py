"""U23 partner mood tests: state changes and mood_change traces."""

import json
import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import build_agent_prompt, list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB, workspace_db_path
from novel_editorial.store.models import (
    Agent,
    Decision,
    Draft,
    DraftVersion,
    Message,
    Workspace,
)

runner = CliRunner()

DEFAULT_MOODS = {
    "editor_in_chief": "沉稳",
    "editor": "精力充沛",
    "writer": "平静",
    "reviewer": "冷静",
}


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "状态之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _generate_draft(workspace_id: str, monkeypatch) -> str:
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply="初稿内容"),
    )
    result = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert result.exit_code == 0, result.output
    return result.output.split()[1]


def _agent(db: DB, workspace_id: str, role: str) -> Agent:
    with db.workspace_session(workspace_id) as session:
        agent = session.query(Agent).filter_by(workspace_id=workspace_id, role=role).first()
        assert agent is not None
        return agent


def _mood_traces(db: DB, workspace_id: str) -> list[dict]:
    traces = []
    for message in list_messages(db, workspace_id):
        payload = json.loads(message.payload)
        if payload.get("kind") == "mood_change":
            traces.append(payload)
    return traces


def test_default_band_mood_non_empty_per_role(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    with db.workspace_session(workspace_id) as session:
        agents = session.query(Agent).filter_by(workspace_id=workspace_id).all()
    assert len(agents) == 4
    for agent in agents:
        assert agent.mood
        assert agent.mood == DEFAULT_MOODS[agent.role]


def test_mood_upgrades_pre_migration_workspace(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    path = workspace_db_path(settings, workspace_id)
    connection = sqlite3.connect(path)
    connection.execute('ALTER TABLE agents DROP COLUMN "mood"')
    connection.execute("DELETE FROM alembic_version")
    connection.execute("INSERT INTO alembic_version (version_num) VALUES ('ede724222072')")
    connection.commit()
    connection.close()

    shown = runner.invoke(app, ["agents", "show", workspace_id])
    assert shown.exit_code == 0, shown.output
    db = DB(settings)
    with db.workspace_session(workspace_id) as session:
        agents = session.query(Agent).filter_by(workspace_id=workspace_id).all()
    for agent in agents:
        assert agent.mood == DEFAULT_MOODS[agent.role]


def test_talk_updates_target_mood_with_trace(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["talk", "send", workspace_id, "@写手 写一段开场"])
    assert result.exit_code == 0, result.output

    db = DB(load_settings())
    writer = _agent(db, workspace_id, "writer")
    assert writer.mood == "投入对话"
    traces = _mood_traces(db, workspace_id)
    assert len(traces) == 1
    assert traces[0] == {
        "kind": "mood_change",
        "from": "平静",
        "to": "投入对话",
        "agent": "写手",
    }


def test_talk_refusal_counts_as_conversation(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(
        app,
        ["talk", "send", workspace_id, "@写手 这段按违背人设的设定写"],
    )
    assert result.exit_code == 0, result.output
    assert "这个我写不了" in result.output

    db = DB(load_settings())
    writer = _agent(db, workspace_id, "writer")
    assert writer.mood == "投入对话"
    traces = _mood_traces(db, workspace_id)
    assert len(traces) == 1
    assert traces[0]["from"] == "平静"
    assert traces[0]["to"] == "投入对话"
    assert traces[0]["agent"] == "写手"


def test_revise_updates_writer_mood(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply="修订稿内容"),
    )
    revised = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "重写铺垫"])
    assert revised.exit_code == 0, revised.output

    db = DB(load_settings())
    writer = _agent(db, workspace_id, "writer")
    assert writer.mood == "专注修订"
    traces = _mood_traces(db, workspace_id)
    assert len(traces) == 1
    assert traces[0] == {
        "kind": "mood_change",
        "from": "平静",
        "to": "专注修订",
        "agent": "写手",
    }


def test_decision_reject_lowers_writer_mood(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    rejected = runner.invoke(app, ["decision", "reject", draft_id])
    assert rejected.exit_code == 0, rejected.output

    db = DB(load_settings())
    writer = _agent(db, workspace_id, "writer")
    assert writer.mood == "低落"
    traces = _mood_traces(db, workspace_id)
    assert len(traces) == 1
    assert traces[0] == {
        "kind": "mood_change",
        "from": "平静",
        "to": "低落",
        "agent": "写手",
    }


def test_decision_accept_raises_writer_mood(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    accepted = runner.invoke(app, ["decision", "accept", draft_id])
    assert accepted.exit_code == 0, accepted.output

    db = DB(load_settings())
    writer = _agent(db, workspace_id, "writer")
    assert writer.mood == "振奋"
    traces = _mood_traces(db, workspace_id)
    assert len(traces) == 1
    assert traces[0] == {
        "kind": "mood_change",
        "from": "平静",
        "to": "振奋",
        "agent": "写手",
    }


def test_agents_show_displays_mood(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["agents", "show", workspace_id])
    assert result.exit_code == 0, result.output
    assert "当前状态" in result.output
    assert "当前状态: 平静" in result.output
    assert "当前状态: 沉稳" in result.output


def test_log_shows_mood_change_trace(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    runner.invoke(app, ["talk", "send", workspace_id, "@写手 写一段开场"])
    result = runner.invoke(app, ["log", workspace_id])
    assert result.exit_code == 0, result.output
    assert "== 状态 ==" in result.output
    assert "mood_change" in result.output
    assert "平静 -> 投入对话" in result.output
    assert "[写手]" in result.output


def test_demo_leaves_mood_changes(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["demo"])
    assert result.exit_code == 0, result.output
    workspace_id = result.output.split()[1]

    db = DB(load_settings())
    traces = _mood_traces(db, workspace_id)
    assert len(traces) == 2
    by_agent = {trace["agent"]: trace for trace in traces}
    assert by_agent["总编"]["to"] == "投入对话"
    assert by_agent["写手"]["to"] == "振奋"


def test_mood_change_is_idempotent_when_unchanged(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    runner.invoke(app, ["talk", "send", workspace_id, "@写手 第一句"])
    runner.invoke(app, ["talk", "send", workspace_id, "@写手 第二句"])

    db = DB(load_settings())
    assert len(_mood_traces(db, workspace_id)) == 1
    assert _agent(db, workspace_id, "writer").mood == "投入对话"


def _message(role: str, actor: str, content: str, payload: dict | None = None) -> Message:
    return Message(
        workspace_id="unit",
        role=role,
        actor=actor,
        content=content,
        payload=json.dumps(payload or {}, ensure_ascii=False),
    )


def _prompt_workspace_and_writer() -> tuple[Workspace, Agent]:
    workspace = Workspace(id="unit", title="测试之书", genre="悬疑")
    writer = Agent(id="writer", workspace_id="unit", name="写手", role="writer")
    return workspace, writer


def test_build_agent_prompt_filters_mood_change_before_windowing() -> None:
    workspace, writer = _prompt_workspace_and_writer()
    history = [
        _message("author", "作者", "第一句"),
        _message("agent", "写手", "回应一"),
        _message(
            "system",
            "写手",
            "写手 的状态从「平静」变为「投入对话」",
            {"kind": "mood_change", "from": "平静", "to": "投入对话", "agent": "写手"},
        ),
        _message("author", "作者", "第二句"),
        _message("agent", "写手", "回应二"),
        _message("author", "作者", "第三句"),
        _message("agent", "写手", "回应三"),
        _message("author", "作者", "第四句"),
    ]

    prompt = build_agent_prompt(workspace, writer, history, latest_message="第五句")

    assert "状态从「平静」变为「投入对话」" not in prompt
    assert "作者: 第一句" not in prompt
    assert "写手: 回应一" in prompt
    assert "作者: 第四句" in prompt


def test_build_agent_prompt_excludes_system_messages() -> None:
    workspace, writer = _prompt_workspace_and_writer()
    history = [
        _message("author", "作者", "你好"),
        _message("system", "写手", "内部提示：不要泄露"),
        _message("agent", "写手", "回复"),
    ]

    prompt = build_agent_prompt(workspace, writer, history)

    assert "内部提示" not in prompt
    assert "作者: 你好" in prompt
    assert "写手: 回复" in prompt


class _CapturingLLMClient(MockLLMClient):
    def __init__(self) -> None:
        super().__init__(reply="模拟回复")
        self.last_prompt = ""

    def complete(self, messages):
        self.last_prompt = messages[-1].content
        return super().complete(messages)


def test_second_talk_prompt_excludes_mood_change_self_report(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.app.build_client", lambda settings: capturing)

    first = runner.invoke(app, ["talk", "send", workspace_id, "@写手 写一段开场"])
    assert first.exit_code == 0, first.output
    second = runner.invoke(app, ["talk", "send", workspace_id, "@写手 再写一段"])
    assert second.exit_code == 0, second.output

    assert "状态从「平静」变为「投入对话」" not in capturing.last_prompt
    assert "mood_change" not in capturing.last_prompt


def test_editor_talk_prompt_excludes_writer_mood_trace(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    capturing = _CapturingLLMClient()
    monkeypatch.setattr("novel_editorial.cli.app.build_client", lambda settings: capturing)

    writer_talk = runner.invoke(app, ["talk", "send", workspace_id, "@写手 写一段开场"])
    assert writer_talk.exit_code == 0, writer_talk.output
    editor_talk = runner.invoke(
        app, ["talk", "send", workspace_id, "@责编 开头节奏怎么样"]
    )
    assert editor_talk.exit_code == 0, editor_talk.output

    assert "写手 的状态从" not in capturing.last_prompt
    assert "mood_change" not in capturing.last_prompt


def test_decision_accept_commits_decision_and_trace_together(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    accepted = runner.invoke(app, ["decision", "accept", draft_id])
    assert accepted.exit_code == 0, accepted.output

    db = DB(load_settings())
    with db.workspace_session(workspace_id) as session:
        decisions = session.query(Decision).filter_by(draft_id=draft_id).all()
    assert [decision.action for decision in decisions] == ["accept"]
    assert _agent(db, workspace_id, "writer").mood == "振奋"
    traces = _mood_traces(db, workspace_id)
    assert len(traces) == 1
    assert traces[0]["to"] == "振奋"


def _raise_mood_write_failure(*args, **kwargs) -> None:
    raise NovelError(ErrorCode.DB_ERROR, "mood write failed")


def test_decision_rolls_back_when_mood_write_fails(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)

    import novel_editorial.core.decision as decision_module

    original = decision_module._update_agent_mood_in_session
    monkeypatch.setattr(
        decision_module, "_update_agent_mood_in_session", _raise_mood_write_failure
    )

    failed = runner.invoke(app, ["decision", "accept", draft_id])
    assert failed.exit_code == 1

    db = DB(load_settings())
    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).filter_by(id=draft_id).first()
        assert draft is not None
        assert draft.status == "draft"
        assert session.query(Decision).filter_by(draft_id=draft_id).count() == 0
    assert _agent(db, workspace_id, "writer").mood == "平静"
    assert _mood_traces(db, workspace_id) == []

    monkeypatch.setattr(decision_module, "_update_agent_mood_in_session", original)
    retried = runner.invoke(app, ["decision", "accept", draft_id])
    assert retried.exit_code == 0, retried.output
    assert _agent(db, workspace_id, "writer").mood == "振奋"


def test_revise_rolls_back_when_mood_write_fails(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply="修订稿内容"),
    )

    import novel_editorial.core.draft as draft_module

    original = draft_module._update_agent_mood_in_session
    monkeypatch.setattr(
        draft_module, "_update_agent_mood_in_session", _raise_mood_write_failure
    )

    failed = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "重写铺垫"])
    assert failed.exit_code == 1

    db = DB(load_settings())
    with db.workspace_session(workspace_id) as session:
        draft = session.query(Draft).filter_by(id=draft_id).first()
        assert draft is not None
        assert draft.current_version == 1
        assert draft.status == "draft"
        versions = session.query(DraftVersion).filter_by(draft_id=draft_id).all()
        assert [version.version for version in versions] == [1]
    assert _agent(db, workspace_id, "writer").mood == "平静"
    assert _mood_traces(db, workspace_id) == []

    monkeypatch.setattr(draft_module, "_update_agent_mood_in_session", original)
    retried = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "重写铺垫"])
    assert retried.exit_code == 0, retried.output
    assert _agent(db, workspace_id, "writer").mood == "专注修订"
