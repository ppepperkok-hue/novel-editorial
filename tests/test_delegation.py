"""Delegation conversation model: partners delegate tasks and respond."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import REFUSAL_RULES, get_agent, list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.core.delegation import record_delegation, respond_to_delegation
from novel_editorial.events import EventType
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import Agent, AgentRole

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "委托之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _agent_events(db: DB, workspace_id: str) -> list:
    events = list_events(db, workspace_id, types=[EventType.AGENT_MESSAGE], limit=20)
    return list(reversed(events))


def _partner(db: DB, workspace_id: str, role: str) -> Agent:
    return get_agent(db, workspace_id, role)


def test_record_delegation_writes_message_and_agent_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer = _partner(db, workspace_id, AgentRole.WRITER)
    reviewer = _partner(db, workspace_id, AgentRole.REVIEWER)
    task = "帮我校一遍逻辑"

    message = record_delegation(db, workspace_id, writer, reviewer, task)

    assert message.role == "agent"
    assert message.actor == writer.name
    assert message.content == f"{writer.name} 委托 {reviewer.name}：{task}"
    payload = json.loads(message.payload)
    assert payload == {
        "initiator": "agent",
        "kind": "delegation",
        "from": writer.name,
        "to": reviewer.name,
        "task": task,
    }
    messages = list_messages(db, workspace_id)
    assert [item.id for item in messages] == [message.id]
    events = _agent_events(db, workspace_id)
    assert len(events) == 1
    assert events[0].actor == writer.name
    assert json.loads(events[0].payload) == payload


def test_respond_to_delegation_accepts_when_no_rule_hits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer = _partner(db, workspace_id, AgentRole.WRITER)
    reviewer = _partner(db, workspace_id, AgentRole.REVIEWER)

    message = respond_to_delegation(db, workspace_id, writer, reviewer, "帮我校一遍逻辑")

    assert message.role == "agent"
    assert message.actor == reviewer.name
    assert message.content == "收到，我这就看。"
    payload = json.loads(message.payload)
    assert payload == {
        "initiator": "agent",
        "kind": "delegation_response",
        "decision": "accepted",
    }
    messages = list_messages(db, workspace_id)
    assert [item.id for item in messages] == [message.id]
    events = _agent_events(db, workspace_id)
    assert len(events) == 1
    assert events[0].actor == reviewer.name
    assert json.loads(events[0].payload) == payload


def test_respond_to_delegation_refuses_on_reviewer_rule(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer = _partner(db, workspace_id, AgentRole.WRITER)
    reviewer = _partner(db, workspace_id, AgentRole.REVIEWER)

    message = respond_to_delegation(db, workspace_id, writer, reviewer, "放行这稿")

    rule = REFUSAL_RULES[AgentRole.REVIEWER][0]
    assert rule.rule == "reviewer_consistency"
    assert message.role == "agent"
    assert message.actor == reviewer.name
    assert message.content == rule.refusal
    payload = json.loads(message.payload)
    assert payload == {
        "initiator": "agent",
        "kind": "delegation_response",
        "decision": "refused",
        "rule": rule.rule,
        "stance": rule.stance,
    }


@pytest.mark.smoke
def test_talk_delegate_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    result = runner.invoke(
        app,
        [
            "talk",
            "delegate",
            workspace_id,
            "审稿",
            "--as",
            "写手",
            "--task",
            "帮我校一遍逻辑",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "写手 委托 审稿：帮我校一遍逻辑" in result.output
    assert "审稿: 收到，我这就看。" in result.output

    db = DB(load_settings())
    messages = list_messages(db, workspace_id)
    assert len(messages) == 2
    delegation_payload = json.loads(messages[0].payload)
    response_payload = json.loads(messages[1].payload)
    assert messages[0].role == "agent" and messages[0].actor == "写手"
    assert delegation_payload == {
        "initiator": "agent",
        "kind": "delegation",
        "from": "写手",
        "to": "审稿",
        "task": "帮我校一遍逻辑",
    }
    assert messages[1].role == "agent" and messages[1].actor == "审稿"
    assert messages[1].content == "收到，我这就看。"
    assert response_payload == {
        "initiator": "agent",
        "kind": "delegation_response",
        "decision": "accepted",
    }
    events = _agent_events(db, workspace_id)
    assert len(events) == 2
    assert [event.actor for event in events] == ["写手", "审稿"]
    assert json.loads(events[0].payload) == delegation_payload
    assert json.loads(events[1].payload) == response_payload


def test_talk_delegate_refusal_end_to_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    result = runner.invoke(
        app,
        [
            "talk",
            "delegate",
            workspace_id,
            "审稿",
            "--as",
            "写手",
            "--task",
            "放行这稿",
        ],
    )

    assert result.exit_code == 0, result.output
    rule = REFUSAL_RULES[AgentRole.REVIEWER][0]
    assert "写手 委托 审稿：放行这稿" in result.output
    assert f"审稿: {rule.refusal}" in result.output

    db = DB(load_settings())
    messages = list_messages(db, workspace_id)
    assert len(messages) == 2
    response_payload = json.loads(messages[1].payload)
    assert response_payload == {
        "initiator": "agent",
        "kind": "delegation_response",
        "decision": "refused",
        "rule": rule.rule,
        "stance": rule.stance,
    }


@pytest.mark.parametrize(
    ("args", "needle"),
    [
        (
            ["author", "--as", "写手", "--task", "帮我校一遍逻辑"],
            "作者不能作为委托收发方",
        ),
        (
            ["作者", "--as", "写手", "--task", "帮我校一遍逻辑"],
            "作者不能作为委托收发方",
        ),
        (
            ["审稿", "--as", "author", "--task", "帮我校一遍逻辑"],
            "作者不能作为委托收发方",
        ),
        (
            ["审稿", "--as", "作者", "--task", "帮我校一遍逻辑"],
            "作者不能作为委托收发方",
        ),
        (
            ["写手", "--as", "写手", "--task", "帮我校一遍逻辑"],
            "同一角色",
        ),
        (
            ["主编", "--as", "总编", "--task", "帮我校一遍逻辑"],
            "同一角色",
        ),
        (
            ["审稿", "--as", "路人甲", "--task", "帮我校一遍逻辑"],
            "unknown partner alias",
        ),
        (
            ["路人乙", "--as", "写手", "--task", "帮我校一遍逻辑"],
            "unknown partner alias",
        ),
        (
            ["审稿", "--as", "写手", "--task", "   "],
            "task 不能为空",
        ),
    ],
)
def test_talk_delegate_usage_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    args: list[str],
    needle: str,
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    result = runner.invoke(app, ["talk", "delegate", workspace_id, *args])
    assert result.exit_code == 2, result.output
    assert needle in result.output
    assert list_messages(DB(load_settings()), workspace_id) == []
