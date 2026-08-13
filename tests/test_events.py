import json
import sqlite3
import time
from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.events import EventType
from novel_editorial.llm.client import MockLLMClient
from novel_editorial.store.db import DB, workspace_db_path
from novel_editorial.store.events import list_events, list_events_since, record_event

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "事件之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _generate_draft(workspace_id: str, monkeypatch, reply: str = "正文内容") -> str:
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply=reply),
    )
    result = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert result.exit_code == 0, result.output
    return result.output.split()[1]


def test_workspace_has_events_table_and_starts_empty(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    settings = load_settings()
    assert list_events(DB(settings), workspace_id) == []
    with sqlite3.connect(workspace_db_path(settings, workspace_id)) as connection:
        tables = [
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
    assert "events" in tables


def test_list_events_newest_first_with_type_filter_and_limit(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    record_event(db, workspace_id, type=EventType.SYSTEM, actor="system", payload={"n": 1})
    time.sleep(0.001)
    record_event(db, workspace_id, type=EventType.AGENT_MESSAGE, actor="主编", payload={"n": 2})
    time.sleep(0.001)
    record_event(db, workspace_id, type=EventType.DRAFT_CREATED, actor="写手", payload={"n": 3})

    events = list_events(db, workspace_id)
    assert [event.type for event in events] == [
        "draft.created",
        "agent.message",
        "system",
    ]
    filtered = list_events(db, workspace_id, types=[EventType.AGENT_MESSAGE])
    assert [event.type for event in filtered] == ["agent.message"]
    assert len(list_events(db, workspace_id, limit=2)) == 2


def test_list_events_since_respects_cursor(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    record_event(db, workspace_id, type=EventType.SYSTEM, actor="system", payload={"n": 1})
    time.sleep(0.001)
    record_event(db, workspace_id, type=EventType.SYSTEM, actor="system", payload={"n": 2})
    time.sleep(0.001)
    record_event(db, workspace_id, type=EventType.SYSTEM, actor="system", payload={"n": 3})

    all_events = list_events(db, workspace_id)
    newest = all_events[0]
    middle = all_events[1]
    oldest = all_events[2]
    assert [
        event.id
        for event in list_events_since(db, workspace_id, after_time=oldest.time, after_id=oldest.id)
    ] == [middle.id, newest.id]
    assert list_events_since(db, workspace_id, after_time=newest.time, after_id=newest.id) == []


def test_talk_records_agent_message_events_only_for_agents(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["talk", "send", workspace_id, "我们写一个侦探故事"])
    assert result.exit_code == 0, result.output

    events = list_events(DB(load_settings()), workspace_id)
    assert [event.type for event in events] == ["agent.message", "agent.message"]
    assert events[0].actor == "责编"
    assert json.loads(events[0].payload) == {
        "initiator": "agent",
        "kind": "proactive_question",
    }
    assert events[1].actor == "总编"
    assert json.loads(events[1].payload) == {}


def test_draft_generate_emits_created_gate_and_decision_events(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)

    events = list_events(DB(load_settings()), workspace_id)
    assert [event.type for event in events] == [
        "decision.requested",
        "quality_gate.passed",
        "draft.created",
    ]
    created = json.loads(events[2].payload)
    assert created == {"draft_id": draft_id, "title": "第一章"}
    gate = json.loads(events[1].payload)
    assert gate["draft_id"] == draft_id
    assert gate["version"] == 1
    assert gate["score"] == 0.0
    decision = json.loads(events[0].payload)
    assert decision == {"draft_id": draft_id, "version": 1}


def test_quality_failure_emits_only_draft_created(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply="月光宛如薄纱，悄然洒落，他静静地凝视着远方。"),
    )
    result = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert result.exit_code == 0, result.output

    events = list_events(DB(load_settings()), workspace_id)
    assert [event.type for event in events] == ["draft.created"]


def test_revise_emits_gate_and_decision_with_new_version(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply="修订稿内容"),
    )
    revised = runner.invoke(app, ["draft", "revise", draft_id, "--reason", "重写铺垫"])
    assert revised.exit_code == 0, revised.output

    events = list_events(DB(load_settings()), workspace_id)
    created = [event for event in events if event.type == "draft.created"]
    gate = [event for event in events if event.type == "quality_gate.passed"]
    decision = [event for event in events if event.type == "decision.requested"]
    assert len(created) == 1
    assert len(gate) == 2 and json.loads(gate[0].payload)["version"] == 2
    assert len(decision) == 2 and json.loads(decision[0].payload)["version"] == 2


def test_review_rejected_only_for_agent_reviews(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    draft_id = _generate_draft(workspace_id, monkeypatch)

    author = runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "作者", "--content", "节奏太慢"],
    )
    assert author.exit_code == 0, author.output
    agent = runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "责编", "--content", "退稿：钩子不成立"],
    )
    assert agent.exit_code == 0, agent.output

    events = list_events(DB(load_settings()), workspace_id)
    rejected = [event for event in events if event.type == "review.rejected"]
    assert len(rejected) == 1
    assert rejected[0].actor == "责编"
    payload = json.loads(rejected[0].payload)
    assert payload["draft_id"] == draft_id
    assert payload["review_id"]
    assert payload["actor"] == "责编"
    assert payload["content"] == "退稿：钩子不成立"


def test_end_to_end_event_order(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )
    talk = runner.invoke(app, ["talk", "send", workspace_id, "我们写一个侦探故事"])
    assert talk.exit_code == 0, talk.output
    draft = runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])
    assert draft.exit_code == 0, draft.output
    draft_id = draft.output.split()[1]
    review = runner.invoke(
        app,
        ["review", "add", draft_id, "--from", "责编", "--content", "退稿：钩子不成立"],
    )
    assert review.exit_code == 0, review.output

    events = list_events(DB(load_settings()), workspace_id)
    oldest_first = list(reversed([event.type for event in events]))
    assert oldest_first == [
        "agent.message",
        "agent.message",
        "draft.created",
        "quality_gate.passed",
        "decision.requested",
        "review.rejected",
    ]


def test_events_list_cli_filters_limits_and_rejects_unknown_types(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    empty = runner.invoke(app, ["events", "list", workspace_id])
    assert empty.exit_code == 0, empty.output
    assert "no events yet" in empty.output

    monkeypatch.setattr(
        "novel_editorial.cli.app.build_client",
        lambda settings: MockLLMClient(reply="正文内容"),
    )
    runner.invoke(app, ["talk", "send", workspace_id, "我们写一个侦探故事"])
    runner.invoke(app, ["draft", "generate", workspace_id, "--title", "第一章"])

    result = runner.invoke(app, ["events", "list", workspace_id])
    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    assert "[decision.requested]" in lines[0]
    assert "[quality_gate.passed]" in lines[1]
    assert "[draft.created]" in lines[2]

    only_messages = runner.invoke(app, ["events", "list", workspace_id, "--type", "agent.message"])
    assert only_messages.exit_code == 0, only_messages.output
    message_lines = only_messages.output.strip().splitlines()
    assert len(message_lines) == 2
    assert all("[agent.message]" in line for line in message_lines)

    limited = runner.invoke(app, ["events", "list", workspace_id, "--limit", "2"])
    assert limited.exit_code == 0, limited.output
    assert len(limited.output.strip().splitlines()) == 2

    unknown = runner.invoke(app, ["events", "list", workspace_id, "--type", "nope"])
    assert unknown.exit_code == 2
    assert "unknown event type: nope" in unknown.output


def test_events_watch_streams_only_new_events_and_exits_cleanly(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    record_event(db, workspace_id, type=EventType.SYSTEM, actor="system", payload={"note": "old"})

    calls = {"count": 0}

    def fake_sleep(seconds: float) -> None:
        calls["count"] += 1
        if calls["count"] == 1:
            record_event(
                db, workspace_id, type=EventType.SYSTEM, actor="system", payload={"note": "new"}
            )
        else:
            raise KeyboardInterrupt

    monkeypatch.setattr(time, "sleep", fake_sleep)
    result = runner.invoke(app, ["events", "watch", workspace_id, "--interval", "1"])
    assert result.exit_code == 0, result.output
    assert '"note": "old"' not in result.output
    assert '"note": "new"' in result.output
