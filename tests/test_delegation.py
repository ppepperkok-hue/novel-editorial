"""Delegation conversation model: partners delegate tasks and respond."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.behavior import list_behavior_timeline
from novel_editorial.core.chat import REFUSAL_RULES, get_agent, list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.core.delegation import record_delegation, respond_to_delegation
from novel_editorial.core.motives import list_motives
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


def test_respond_to_delegation_accepts_after_author_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer = _partner(db, workspace_id, AgentRole.WRITER)
    reviewer = _partner(db, workspace_id, AgentRole.REVIEWER)
    task = "放行这稿"
    rule = REFUSAL_RULES[AgentRole.REVIEWER][0]

    override = runner.invoke(
        app,
        ["talk", "send", workspace_id, "@审稿 放行这稿，我拍板"],
    )
    assert override.exit_code == 0, override.output

    message = respond_to_delegation(db, workspace_id, writer, reviewer, task)

    assert message.role == "agent"
    assert message.actor == reviewer.name
    assert message.content == "收到，我这就看。"
    payload = json.loads(message.payload)
    assert payload == {
        "initiator": "agent",
        "kind": "delegation_response",
        "decision": "accepted",
    }
    assert rule.rule == "reviewer_consistency"


def test_respond_to_delegation_repeats_refusal_after_previous_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer = _partner(db, workspace_id, AgentRole.WRITER)
    reviewer = _partner(db, workspace_id, AgentRole.REVIEWER)
    task = "放行这稿"
    rule = REFUSAL_RULES[AgentRole.REVIEWER][0]

    first = runner.invoke(
        app,
        ["talk", "send", workspace_id, "@审稿 放行这稿"],
    )
    assert first.exit_code == 0, first.output

    message = respond_to_delegation(db, workspace_id, writer, reviewer, task)

    assert message.role == "agent"
    assert message.actor == reviewer.name
    assert message.content == rule.reaffirmation
    assert message.content != rule.refusal
    payload = json.loads(message.payload)
    assert payload == {
        "initiator": "agent",
        "kind": "delegation_response",
        "decision": "refused",
        "rule": rule.rule,
        "stance": rule.stance,
        "repeated": True,
    }


def test_talk_delegate_reaffirms_after_previous_delegation_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    rule = REFUSAL_RULES[AgentRole.REVIEWER][0]

    first = runner.invoke(
        app,
        ["talk", "delegate", workspace_id, "审稿", "--as", "写手", "--task", "放行这稿"],
    )
    assert first.exit_code == 0, first.output
    assert f"审稿: {rule.refusal}" in first.output

    second = runner.invoke(
        app,
        ["talk", "delegate", workspace_id, "审稿", "--as", "写手", "--task", "放行这稿"],
    )
    assert second.exit_code == 0, second.output
    assert f"审稿: {rule.reaffirmation}" in second.output

    db = DB(load_settings())
    messages = list_messages(db, workspace_id)
    assert len(messages) == 4
    first_response = json.loads(messages[1].payload)
    second_response = json.loads(messages[3].payload)
    assert first_response == {
        "initiator": "agent",
        "kind": "delegation_response",
        "decision": "refused",
        "rule": rule.rule,
        "stance": rule.stance,
    }
    assert second_response == {
        "initiator": "agent",
        "kind": "delegation_response",
        "decision": "refused",
        "rule": rule.rule,
        "stance": rule.stance,
        "repeated": True,
    }

    writer = _partner(db, workspace_id, AgentRole.WRITER)
    reviewer = _partner(db, workspace_id, AgentRole.REVIEWER)
    rows = list_behavior_timeline(db, workspace_id)
    viewpoints = [row for row in rows if row.kind == "viewpoint"]
    relationships = [row for row in rows if row.kind == "relationship"]
    refusal_viewpoints = [
        row for row in viewpoints if row.source.startswith("refusal:")
    ]
    drift_viewpoints = [row for row in viewpoints if row.source.startswith("drift:")]
    assert len(refusal_viewpoints) == 1
    assert refusal_viewpoints[0].agent_id == reviewer.id
    assert refusal_viewpoints[0].target == rule.rule
    assert refusal_viewpoints[0].source == f"refusal:{rule.rule}"
    # Each refused delegation leaves one stubbornness drift trace on the
    # delegating writer (N28-A), so two refusals write two drift rows.
    assert len(drift_viewpoints) == 2
    assert all(row.agent_id == writer.id for row in drift_viewpoints)
    assert all(row.target == "stubbornness" for row in drift_viewpoints)
    assert all(row.source == "drift:delegation:refused" for row in drift_viewpoints)
    assert len(relationships) == 2
    assert all(row.agent_id == writer.id for row in relationships)
    assert all(row.target == reviewer.name for row in relationships)
    assert all(row.summary == "委托被拒绝" for row in relationships)
    assert all(row.source == "delegation:refused" for row in relationships)
    writer_issues = [
        motive
        for motive in list_motives(db, workspace_id)
        if motive.agent_id == writer.id and motive.source == "delegation:refused"
    ]
    assert len(writer_issues) == 1
    assert writer_issues[0].kind == "pending_issue"
    assert writer_issues[0].content == "委托被拒，这事还惦记着"


@pytest.mark.parametrize("task", ["帮我校一遍逻辑", "放行这稿"])
def test_talk_delegate_business_survives_behavior_trace_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    task: str,
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("novel_editorial.core.behavior.record_behavior_entry", boom)
    result = runner.invoke(
        app,
        ["talk", "delegate", workspace_id, "审稿", "--as", "写手", "--task", task],
    )
    assert result.exit_code == 0, result.output
    assert "warning: behavior trace skipped: boom" in result.output

    db = DB(load_settings())
    messages = list_messages(db, workspace_id)
    assert len(messages) == 2
    events = _agent_events(db, workspace_id)
    assert len(events) == 2
    writer = _partner(db, workspace_id, AgentRole.WRITER)
    rows = list_behavior_timeline(db, workspace_id)
    # The N3 sediment path (behavior.record_behavior_entry) is what the
    # monkeypatch breaks; the N28 drift write-back is an independent post-hoc
    # write and still lands with its explainable source.
    assert [row for row in rows if row.source.startswith(("delegation:", "refusal:"))] == []
    assert len(rows) == 1
    assert rows[0].kind == "viewpoint"
    assert rows[0].agent_id == writer.id
    if task == "帮我校一遍逻辑":
        assert rows[0].target == "proactivity"
        assert rows[0].source == "drift:delegation:accepted"
    else:
        assert rows[0].target == "stubbornness"
        assert rows[0].source == "drift:delegation:refused"


def test_talk_send_reaffirms_after_delegation_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    rule = REFUSAL_RULES[AgentRole.REVIEWER][0]

    delegation = runner.invoke(
        app,
        ["talk", "delegate", workspace_id, "审稿", "--as", "写手", "--task", "放行这稿"],
    )
    assert delegation.exit_code == 0, delegation.output

    talk = runner.invoke(app, ["talk", "send", workspace_id, "@审稿 放行这稿"])
    assert talk.exit_code == 0, talk.output
    assert f"审稿: {rule.reaffirmation}" in talk.output

    db = DB(load_settings())
    messages = list_messages(db, workspace_id)
    refusals = [message for message in messages if '"kind": "refusal"' in message.payload]
    assert len(refusals) == 1
    talk_refusal = json.loads(refusals[0].payload)
    assert talk_refusal == {
        "kind": "refusal",
        "stance": rule.stance,
        "rule": rule.rule,
        "repeated": True,
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

    rows = list_behavior_timeline(db, workspace_id)
    assert len(rows) == 3
    relationship = next(row for row in rows if row.kind == "relationship")
    impression = next(row for row in rows if row.kind == "impression")
    drift = next(row for row in rows if row.source == "drift:delegation:accepted")
    writer = _partner(db, workspace_id, AgentRole.WRITER)
    reviewer = _partner(db, workspace_id, AgentRole.REVIEWER)
    assert relationship.agent_id == writer.id
    assert relationship.target == reviewer.name
    assert relationship.summary == "委托被接受"
    assert relationship.source == "delegation:accepted"
    assert impression.agent_id == writer.id
    assert impression.target == reviewer.name
    assert impression.summary == "可协作"
    assert impression.source == "delegation:accepted"
    assert drift.agent_id == writer.id
    assert drift.kind == "viewpoint"
    assert drift.target == "proactivity"
    assert list_motives(db, workspace_id) == []


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

    writer = _partner(db, workspace_id, AgentRole.WRITER)
    reviewer = _partner(db, workspace_id, AgentRole.REVIEWER)
    rows = list_behavior_timeline(db, workspace_id)
    assert len(rows) == 3
    relationship = next(row for row in rows if row.kind == "relationship")
    viewpoint = next(
        row
        for row in rows
        if row.kind == "viewpoint" and not row.source.startswith("drift:")
    )
    drift = next(row for row in rows if row.source == "drift:delegation:refused")
    assert relationship.agent_id == writer.id
    assert relationship.target == reviewer.name
    assert relationship.summary == "委托被拒绝"
    assert relationship.source == "delegation:refused"
    assert viewpoint.agent_id == reviewer.id
    assert viewpoint.target == rule.rule
    assert viewpoint.summary == "拒绝了违背立场的指令"
    assert viewpoint.before_value is None
    assert viewpoint.after_value == "坚持该立场"
    assert viewpoint.source == f"refusal:{rule.rule}"
    assert drift.agent_id == writer.id
    assert drift.kind == "viewpoint"
    assert drift.target == "stubbornness"
    writer_issues = [
        motive
        for motive in list_motives(db, workspace_id)
        if motive.agent_id == writer.id and motive.source == "delegation:refused"
    ]
    assert len(writer_issues) == 1
    assert writer_issues[0].kind == "pending_issue"


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


def test_respond_refused_writes_delegator_motive_and_stubbornness_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer = _partner(db, workspace_id, AgentRole.WRITER)
    reviewer = _partner(db, workspace_id, AgentRole.REVIEWER)

    message = respond_to_delegation(db, workspace_id, writer, reviewer, "放行这稿")

    assert message.content.startswith("这个我不能放行")
    issues = [
        motive
        for motive in list_motives(db, workspace_id)
        if motive.source == "delegation:refused"
    ]
    assert len(issues) == 1
    assert issues[0].agent_id == writer.id
    assert issues[0].kind == "pending_issue"
    assert issues[0].content == "委托被拒，这事还惦记着"

    drift = [
        row
        for row in list_behavior_timeline(db, workspace_id)
        if row.source == "drift:delegation:refused"
    ]
    assert len(drift) == 1
    assert drift[0].kind == "viewpoint"
    assert drift[0].agent_id == writer.id
    assert drift[0].target == "stubbornness"
    assert drift[0].after_value == "1"
    with db.workspace_session(workspace_id) as session:
        stored = session.query(Agent).filter_by(id=writer.id).first()
        assert stored is not None
        assert stored.drift_stubbornness == 1


def test_respond_accepted_clears_pending_issue_and_boosts_proactivity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = DB(load_settings())
    writer = _partner(db, workspace_id, AgentRole.WRITER)
    reviewer = _partner(db, workspace_id, AgentRole.REVIEWER)
    task = "放行这稿"

    refused = respond_to_delegation(db, workspace_id, writer, reviewer, task)
    assert refused.content.startswith("这个我不能放行")
    override = runner.invoke(app, ["talk", "send", workspace_id, "@审稿 放行这稿，我拍板"])
    assert override.exit_code == 0, override.output

    accepted = respond_to_delegation(db, workspace_id, writer, reviewer, task)

    assert accepted.content == "收到，我这就看。"
    assert list_motives(db, workspace_id) == []
    drift = [
        row
        for row in list_behavior_timeline(db, workspace_id)
        if row.source == "drift:delegation:accepted"
    ]
    assert len(drift) == 1
    assert drift[0].kind == "viewpoint"
    assert drift[0].agent_id == writer.id
    assert drift[0].target == "proactivity"
    with db.workspace_session(workspace_id) as session:
        stored = session.query(Agent).filter_by(id=writer.id).first()
        assert stored is not None
        assert stored.drift_proactivity == 1
        # The earlier refusal still left its own stubbornness trace.
        assert stored.drift_stubbornness == 1


@pytest.mark.parametrize(
    ("task", "expected_warnings"),
    [
        (
            "帮我校一遍逻辑",
            ["warning: drift write skipped (delegation:accepted): boom"],
        ),
        (
            "放行这稿",
            [
                "warning: motive feedback skipped (upsert delegation:refused): boom",
                "warning: drift write skipped (delegation:refused): boom",
            ],
        ),
    ],
)
def test_talk_delegate_business_survives_motive_and_drift_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    task: str,
    expected_warnings: list[str],
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("novel_editorial.core.motives.upsert_motive_feedback", boom)
    monkeypatch.setattr("novel_editorial.core.evolution.apply_param_drift", boom)
    result = runner.invoke(
        app,
        ["talk", "delegate", workspace_id, "审稿", "--as", "写手", "--task", task],
    )

    assert result.exit_code == 0, result.output
    for warning in expected_warnings:
        assert warning in result.output
    db = DB(load_settings())
    assert len(list_messages(db, workspace_id)) == 2
    assert list_motives(db, workspace_id) == []
