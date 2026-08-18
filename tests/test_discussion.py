"""N4 editorial discussion data model and CLI skeleton (E1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import AUTHOR_ACTOR, get_agent, list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.core.discussion import (
    CONTRIBUTION_TEMPLATES,
    SUMMARY_LEAD,
    conclude_discussion,
    contribute_to_discussion,
    open_discussion,
    summarize_discussion,
)
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import Agent, AgentRole

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "讨论之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _db() -> DB:
    return DB(load_settings())


def test_open_discussion_records_kickoff_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    topic = "主角动机要不要改"
    writer = get_agent(db, workspace_id, AgentRole.WRITER)
    reviewer = get_agent(db, workspace_id, AgentRole.REVIEWER)

    discussion_id, message = open_discussion(
        db, workspace_id, topic=topic, participants=[writer, reviewer]
    )

    assert len(discussion_id) == 32
    assert message.role == "author"
    assert message.actor == AUTHOR_ACTOR
    assert message.content == "作者发起讨论「主角动机要不要改」（参与：写手、审稿）"
    assert json.loads(message.payload) == {
        "kind": "discussion_open",
        "discussion_id": discussion_id,
        "topic": topic,
        "participants": ["写手", "审稿"],
        "convener": "作者",
    }
    assert len(list_messages(db, workspace_id)) == 1
    assert list_events(db, workspace_id) == []


def test_open_discussion_rejects_blank_topic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = get_agent(db, workspace_id, AgentRole.WRITER)

    with pytest.raises(NovelError) as excinfo:
        open_discussion(db, workspace_id, topic="  ", participants=[writer])

    assert excinfo.value.code is ErrorCode.USAGE_ERROR
    assert list_messages(db, workspace_id) == []


def test_open_discussion_rejects_empty_participants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as excinfo:
        open_discussion(db, workspace_id, topic="议题", participants=[])

    assert excinfo.value.code is ErrorCode.USAGE_ERROR


def test_open_discussion_rejects_duplicate_roles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = get_agent(db, workspace_id, AgentRole.WRITER)

    with pytest.raises(NovelError) as excinfo:
        open_discussion(db, workspace_id, topic="议题", participants=[writer, writer])

    assert excinfo.value.code is ErrorCode.USAGE_ERROR
    assert list_messages(db, workspace_id) == []


@pytest.mark.parametrize(
    ("role", "actor"),
    [
        (AgentRole.EDITOR_IN_CHIEF, "总编"),
        (AgentRole.EDITOR, "责编"),
        (AgentRole.WRITER, "写手"),
        (AgentRole.REVIEWER, "审稿"),
    ],
)
def test_contribute_uses_fixed_role_template(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    role: str,
    actor: str,
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    topic = "主角动机要不要改"
    agent = get_agent(db, workspace_id, role)
    discussion_id, _ = open_discussion(db, workspace_id, topic=topic, participants=[agent])

    message = contribute_to_discussion(
        db, workspace_id, discussion_id=discussion_id, topic=topic, agent=agent
    )

    assert message.role == "agent"
    assert message.actor == actor
    assert message.content == CONTRIBUTION_TEMPLATES[role].format(topic=topic)
    payload = json.loads(message.payload)
    assert payload == {
        "kind": "discussion_contribution",
        "discussion_id": discussion_id,
        "topic": topic,
        "position": "stated",
    }
    events = list_events(db, workspace_id)
    assert len(events) == 1
    assert events[0].type == "agent.message"
    assert events[0].actor == actor
    assert json.loads(events[0].payload) == payload


def test_contribute_unknown_role_rejects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    stranger = Agent(workspace_id=workspace_id, name="路人", role="stranger")

    with pytest.raises(NovelError) as excinfo:
        contribute_to_discussion(
            db, workspace_id, discussion_id="0" * 32, topic="议题", agent=stranger
        )

    assert excinfo.value.code is ErrorCode.USAGE_ERROR


def test_summarize_lists_every_contribution_deterministically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    topic = "主角动机要不要改"
    writer = get_agent(db, workspace_id, AgentRole.WRITER)
    reviewer = get_agent(db, workspace_id, AgentRole.REVIEWER)
    discussion_id, _ = open_discussion(
        db, workspace_id, topic=topic, participants=[writer, reviewer]
    )
    writer_message = contribute_to_discussion(
        db, workspace_id, discussion_id=discussion_id, topic=topic, agent=writer
    )
    reviewer_message = contribute_to_discussion(
        db, workspace_id, discussion_id=discussion_id, topic=topic, agent=reviewer
    )
    summarizer = get_agent(db, workspace_id, AgentRole.EDITOR_IN_CHIEF)

    summary = summarize_discussion(
        db, workspace_id, discussion_id=discussion_id, topic=topic, summarizer=summarizer
    )

    assert summary.role == "agent"
    assert summary.actor == "总编"
    assert summary.content == (
        f"{SUMMARY_LEAD.format(topic=topic)}\n"
        f"写手：{writer_message.content}\n"
        f"审稿：{reviewer_message.content}"
    )
    payload = json.loads(summary.payload)
    assert payload["kind"] == "discussion_summary"
    assert payload["discussion_id"] == discussion_id
    assert payload["topic"] == topic
    assert payload["positions"] == [
        {"agent": "写手", "position": "stated", "content": writer_message.content},
        {"agent": "审稿", "position": "stated", "content": reviewer_message.content},
    ]
    events = list_events(db, workspace_id)
    assert [event.actor for event in reversed(events)] == ["写手", "审稿", "总编"]


def test_summarize_unknown_discussion_raises_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    summarizer = get_agent(db, workspace_id, AgentRole.EDITOR_IN_CHIEF)

    with pytest.raises(NovelError) as excinfo:
        summarize_discussion(
            db,
            workspace_id,
            discussion_id="0" * 32,
            topic="议题",
            summarizer=summarizer,
        )

    assert excinfo.value.code is ErrorCode.NOT_FOUND


def test_summarize_without_contributions_raises_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = get_agent(db, workspace_id, AgentRole.WRITER)
    summarizer = get_agent(db, workspace_id, AgentRole.EDITOR_IN_CHIEF)
    discussion_id, _ = open_discussion(db, workspace_id, topic="议题", participants=[writer])

    with pytest.raises(NovelError) as excinfo:
        summarize_discussion(
            db, workspace_id, discussion_id=discussion_id, topic="议题", summarizer=summarizer
        )

    assert excinfo.value.code is ErrorCode.USAGE_ERROR


def test_conclude_records_author_decision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    topic = "主角动机要不要改"
    writer = get_agent(db, workspace_id, AgentRole.WRITER)
    discussion_id, _ = open_discussion(db, workspace_id, topic=topic, participants=[writer])
    outcome = "先不改，加一场揭示戏"

    decision = conclude_discussion(
        db, workspace_id, discussion_id=discussion_id, topic=topic, outcome=outcome
    )

    assert decision.role == "author"
    assert decision.actor == AUTHOR_ACTOR
    assert decision.content == f"作者拍板：{outcome}"
    assert json.loads(decision.payload) == {
        "kind": "discussion_decision",
        "discussion_id": discussion_id,
        "topic": topic,
        "outcome": outcome,
    }
    assert list_events(db, workspace_id) == []


def test_conclude_rejects_blank_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as excinfo:
        conclude_discussion(db, workspace_id, discussion_id="x", topic="议题", outcome="  ")

    assert excinfo.value.code is ErrorCode.USAGE_ERROR


def test_conclude_unknown_discussion_raises_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    with pytest.raises(NovelError) as excinfo:
        conclude_discussion(
            db,
            workspace_id,
            discussion_id="0" * 32,
            topic="议题",
            outcome="先不改",
        )

    assert excinfo.value.code is ErrorCode.NOT_FOUND
    assert excinfo.value.message == f"discussion not found: {'0' * 32}"
    assert list_messages(db, workspace_id) == []


def test_talk_discuss_runs_full_flow_in_fixed_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    topic = "主角动机要不要改"
    outcome = "先不改，加一场揭示戏"

    result = runner.invoke(
        app,
        [
            "talk",
            "discuss",
            workspace_id,
            "--topic",
            topic,
            "--with",
            "写手,审稿",
            "--outcome",
            outcome,
        ],
    )

    assert result.exit_code == 0, result.output
    writer_template = CONTRIBUTION_TEMPLATES[AgentRole.WRITER].format(topic=topic)
    reviewer_template = CONTRIBUTION_TEMPLATES[AgentRole.REVIEWER].format(topic=topic)
    assert result.output == "\n".join(
        [
            "作者发起讨论「主角动机要不要改」（参与：写手、审稿）",
            writer_template,
            reviewer_template,
            SUMMARY_LEAD.format(topic=topic),
            f"写手：{writer_template}",
            f"审稿：{reviewer_template}",
            f"作者拍板：{outcome}",
        ]
    ) + "\n"

    messages = list_messages(db, workspace_id)
    assert len(messages) == 5
    assert [json.loads(m.payload)["kind"] for m in messages] == [
        "discussion_open",
        "discussion_contribution",
        "discussion_contribution",
        "discussion_summary",
        "discussion_decision",
    ]
    events = list_events(db, workspace_id)
    assert len(events) == 3
    assert [event.actor for event in reversed(events)] == ["写手", "审稿", "总编"]


def test_talk_discuss_defaults_to_all_four_partners(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    topic = "大纲定调"

    result = runner.invoke(app, ["talk", "discuss", workspace_id, "--topic", topic])

    assert result.exit_code == 0, result.output
    assert "作者发起讨论「大纲定调」（参与：总编、责编、写手、审稿）" in result.output
    templates = [
        CONTRIBUTION_TEMPLATES[role].format(topic=topic)
        for role in (
            AgentRole.EDITOR_IN_CHIEF,
            AgentRole.EDITOR,
            AgentRole.WRITER,
            AgentRole.REVIEWER,
        )
    ]
    indexes = [result.output.index(template) for template in templates]
    assert indexes == sorted(indexes)
    assert "作者拍板" not in result.output

    messages = list_messages(db, workspace_id)
    assert len(messages) == 6
    assert len(list_events(db, workspace_id)) == 5


@pytest.mark.parametrize(
    ("with_value", "error_fragment"),
    [
        ("作者", "作者不能参与讨论"),
        ("unknown", "unknown partner alias"),
        ("总编,主编", "重复角色"),
        ("写手,写手", "重复角色"),
    ],
)
def test_talk_discuss_rejects_invalid_with(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    with_value: str,
    error_fragment: str,
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    result = runner.invoke(
        app, ["talk", "discuss", workspace_id, "--topic", "议题", "--with", with_value]
    )

    assert result.exit_code == 2
    assert error_fragment in result.output
    assert list_messages(db, workspace_id) == []


def test_talk_discuss_rejects_blank_topic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    result = runner.invoke(app, ["talk", "discuss", workspace_id, "--topic", "  "])

    assert result.exit_code == 2
    assert "topic 不能为空" in result.output


def test_talk_discuss_rejects_blank_with(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    result = runner.invoke(
        app, ["talk", "discuss", workspace_id, "--topic", "议题", "--with", ""]
    )

    assert result.exit_code == 2
    assert "--with 不能为空" in result.output


def test_talk_discuss_rejects_blank_outcome_before_writing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()

    result = runner.invoke(
        app,
        [
            "talk",
            "discuss",
            workspace_id,
            "--topic",
            "议题",
            "--outcome",
            "  ",
        ],
    )

    assert result.exit_code == 2
    assert "outcome 不能为空" in result.output
    assert list_messages(db, workspace_id) == []
