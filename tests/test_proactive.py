import json
from pathlib import Path

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from novel_editorial.core import proactive
from novel_editorial.core.config import Settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.workspace import create_workspace
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import Agent, AgentRole, Message


def _make_db(
    tmp_path: Path,
    *,
    proactive_enabled: bool = True,
    proactive_max_per_agent: int = 3,
) -> tuple[DB, str]:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_path=tmp_path / "config.toml",
        proactive_enabled=proactive_enabled,
        proactive_max_per_agent=proactive_max_per_agent,
    )
    db = DB(settings)
    db.init_schema()
    workspace = create_workspace(db, title="主动之书", genre="悬疑")
    return db, workspace.id


def _agent_name(db: DB, workspace_id: str, role: str) -> str:
    with db.workspace_session(workspace_id) as session:
        agent = session.query(Agent).filter_by(workspace_id=workspace_id, role=role).first()
    assert agent is not None
    return agent.name


def _insert_proactive(
    db: DB,
    workspace_id: str,
    actor: str,
    *,
    kind: str = proactive.PROACTIVE_KIND_REVIEW,
    trigger: str = "draft_generated",
) -> None:
    payload = proactive.build_proactive_payload(kind, trigger)
    with db.workspace_session(workspace_id) as session:
        session.add(
            Message(
                workspace_id=workspace_id,
                role="agent",
                actor=actor,
                content="主动消息",
                payload=json.dumps(payload, ensure_ascii=False),
            )
        )
        session.commit()


def test_kinds_and_payload_structure() -> None:
    assert proactive.PROACTIVE_KIND_QUESTION == "proactive_question"
    assert proactive.PROACTIVE_KIND_REVIEW == "proactive_review"
    assert proactive.PROACTIVE_KIND_CONSISTENCY == "proactive_consistency"
    assert proactive.PROACTIVE_KIND_DIRECTION == "proactive_direction"
    assert proactive.PROACTIVE_KIND_REPORT == "proactive_report"
    assert proactive.PROACTIVE_KINDS == {
        "proactive_question",
        "proactive_review",
        "proactive_consistency",
        "proactive_direction",
        "proactive_report",
    }
    assert proactive.build_proactive_payload("proactive_review", "draft_generated") == {
        "initiator": "agent",
        "kind": "proactive_review",
        "trigger": "draft_generated",
    }


def test_evaluate_returns_matching_candidates(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    agent = _agent_name(db, workspace_id, AgentRole.EDITOR)
    proactive.register_proactive_trigger(
        trigger="draft_gate_passed_a1",
        agent=agent,
        kind=proactive.PROACTIVE_KIND_REVIEW,
        content="这一稿节奏可以再收紧。",
        condition=lambda context: context.get("passed") is True,
    )

    matched = proactive.evaluate_proactive_triggers(
        db, workspace_id, "draft_gate_passed_a1", {"passed": True}
    )
    assert matched == [
        proactive.ProactiveCandidate(
            agent=agent,
            kind=proactive.PROACTIVE_KIND_REVIEW,
            content="这一稿节奏可以再收紧。",
        )
    ]
    assert (
        proactive.evaluate_proactive_triggers(
            db, workspace_id, "draft_gate_passed_a1", {"passed": False}
        )
        == []
    )
    assert proactive.evaluate_proactive_triggers(db, workspace_id, "unregistered_a1", {}) == []


def test_count_requires_initiator_and_kind_markers(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent_name(db, workspace_id, AgentRole.WRITER)
    _insert_proactive(db, workspace_id, writer, kind=proactive.PROACTIVE_KIND_REPORT)
    with db.workspace_session(workspace_id) as session:
        session.add_all(
            [
                Message(
                    workspace_id=workspace_id,
                    role="agent",
                    actor=writer,
                    content="状态",
                    payload=json.dumps({"kind": "mood_change"}, ensure_ascii=False),
                ),
                Message(
                    workspace_id=workspace_id,
                    role="agent",
                    actor=writer,
                    content="只有发起标记",
                    payload=json.dumps({"initiator": "agent"}, ensure_ascii=False),
                ),
                Message(
                    workspace_id=workspace_id,
                    role="agent",
                    actor=writer,
                    content="普通消息",
                    payload="{}",
                ),
            ]
        )
        session.commit()

    assert proactive.count_proactive_messages(db, workspace_id, writer) == 1
    assert not proactive.proactive_within_limit(db, workspace_id, writer, 1)
    assert proactive.proactive_within_limit(db, workspace_id, writer, 2)


def test_frequency_limit_skips_partner_at_max(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path, proactive_max_per_agent=3)
    reviewer = _agent_name(db, workspace_id, AgentRole.REVIEWER)
    editor = _agent_name(db, workspace_id, AgentRole.EDITOR)
    for _ in range(3):
        _insert_proactive(
            db,
            workspace_id,
            reviewer,
            kind=proactive.PROACTIVE_KIND_CONSISTENCY,
            trigger="style_set_a1",
        )
    proactive.register_proactive_trigger(
        trigger="style_set_a1",
        agent=reviewer,
        kind=proactive.PROACTIVE_KIND_CONSISTENCY,
        content="审稿提示矛盾",
        condition=lambda context: True,
    )
    proactive.register_proactive_trigger(
        trigger="style_set_a1",
        agent=editor,
        kind=proactive.PROACTIVE_KIND_DIRECTION,
        content="主编梳理方向",
        condition=lambda context: True,
    )

    candidates = proactive.evaluate_proactive_triggers(db, workspace_id, "style_set_a1", {})
    assert [candidate.agent for candidate in candidates] == [editor]


def test_disabled_switch_returns_empty(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path, proactive_enabled=False)
    agent = _agent_name(db, workspace_id, AgentRole.WRITER)
    proactive.register_proactive_trigger(
        trigger="talk_sent_a1",
        agent=agent,
        kind=proactive.PROACTIVE_KIND_QUESTION,
        content="追问设定",
        condition=lambda context: True,
    )

    assert proactive.evaluate_proactive_triggers(db, workspace_id, "talk_sent_a1", {}) == []


def test_unknown_kind_and_empty_fields_are_rejected() -> None:
    with pytest.raises(NovelError) as info:
        proactive.build_proactive_payload("not_a_kind", "trigger_a1")
    assert info.value.code == ErrorCode.USAGE_ERROR

    with pytest.raises(NovelError) as info:
        proactive.register_proactive_trigger(
            trigger="trigger_a1",
            agent="写手",
            kind="not_a_kind",
            content="文案",
            condition=lambda context: True,
        )
    assert info.value.code == ErrorCode.USAGE_ERROR

    with pytest.raises(NovelError) as info:
        proactive.build_proactive_payload(proactive.PROACTIVE_KIND_REVIEW, "")
    assert info.value.code == ErrorCode.USAGE_ERROR


def test_single_evaluation_caps_same_agent_budget(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path, proactive_max_per_agent=1)
    reviewer = _agent_name(db, workspace_id, AgentRole.REVIEWER)
    proactive.register_proactive_trigger(
        trigger="style_set_budget_a1",
        agent=reviewer,
        kind=proactive.PROACTIVE_KIND_CONSISTENCY,
        content="first candidate",
        condition=lambda context: True,
    )
    proactive.register_proactive_trigger(
        trigger="style_set_budget_a1",
        agent=reviewer,
        kind=proactive.PROACTIVE_KIND_DIRECTION,
        content="second candidate",
        condition=lambda context: True,
    )

    candidates = proactive.evaluate_proactive_triggers(
        db, workspace_id, "style_set_budget_a1", {}
    )
    assert len(candidates) == 1
    assert candidates[0].agent == reviewer


def test_zero_budget_returns_no_candidates(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path, proactive_max_per_agent=0)
    writer = _agent_name(db, workspace_id, AgentRole.WRITER)
    proactive.register_proactive_trigger(
        trigger="talk_sent_budget_a1",
        agent=writer,
        kind=proactive.PROACTIVE_KIND_QUESTION,
        content="question candidate",
        condition=lambda context: True,
    )

    assert (
        proactive.evaluate_proactive_triggers(db, workspace_id, "talk_sent_budget_a1", {})
        == []
    )


def test_rebuttal_messages_do_not_consume_proactive_budget(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent_name(db, workspace_id, AgentRole.WRITER)
    with db.workspace_session(workspace_id) as session:
        session.add(
            Message(
                workspace_id=workspace_id,
                role="agent",
                actor=writer,
                content="rebuttal",
                payload=json.dumps(
                    {"initiator": "agent", "kind": "rebuttal"}, ensure_ascii=False
                ),
            )
        )
        session.commit()

    assert proactive.count_proactive_messages(db, workspace_id, writer) == 0

    _insert_proactive(
        db,
        workspace_id,
        writer,
        kind=proactive.PROACTIVE_KIND_REPORT,
        trigger="draft_revised_a1",
    )
    assert proactive.count_proactive_messages(db, workspace_id, writer) == 1


def test_count_filters_in_sql_without_materializing_rows(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent_name(db, workspace_id, AgentRole.WRITER)
    _insert_proactive(db, workspace_id, writer, kind=proactive.PROACTIVE_KIND_REPORT)
    with db.workspace_session(workspace_id) as session:
        session.add(
            Message(
                workspace_id=workspace_id,
                role="agent",
                actor=writer,
                content="rebuttal",
                payload=json.dumps(
                    {"initiator": "agent", "kind": "rebuttal"}, ensure_ascii=False
                ),
            )
        )
        session.commit()

    executed: list[tuple[str, tuple]] = []

    def capture(conn, cursor, statement, parameters, context, executemany) -> None:
        executed.append((statement, parameters))

    event.listen(Engine, "after_cursor_execute", capture)
    try:
        assert proactive.count_proactive_messages(db, workspace_id, writer) == 1
    finally:
        event.remove(Engine, "after_cursor_execute", capture)

    selects = [entry for entry in executed if entry[0].lower().startswith("select")]
    assert len(selects) == 1
    statement, parameters = selects[0]
    assert "count(*)" in statement.lower()
    assert "messages.content" not in statement.lower()
    param_values = {value for value in parameters if isinstance(value, str)}
    for kind in proactive.PROACTIVE_KINDS:
        assert f'%"kind": "{kind}"%' in param_values
    assert f'%"initiator": "{proactive.INITIATOR_AGENT}"%' in param_values


def test_record_proactive_messages_persists_message_and_event(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent_name(db, workspace_id, AgentRole.WRITER)
    proactive.register_proactive_trigger(
        trigger="record_a2",
        agent=writer,
        kind=proactive.PROACTIVE_KIND_REPORT,
        content="《$title》写完了，片段「$excerpt」",
        condition=lambda context: True,
    )

    recorded = proactive.record_proactive_messages(
        db, workspace_id, "record_a2", {"title": "第一章", "excerpt": "开头一句"}
    )
    assert len(recorded) == 1
    message = recorded[0]
    assert message.role == "agent"
    assert message.actor == writer
    assert message.content == "《第一章》写完了，片段「开头一句」"
    assert json.loads(message.payload) == {
        "initiator": proactive.INITIATOR_AGENT,
        "kind": proactive.PROACTIVE_KIND_REPORT,
        "trigger": "record_a2",
    }

    events = list_events(db, workspace_id)
    assert [event.type for event in events] == ["agent.message"]
    assert json.loads(events[0].payload) == json.loads(message.payload)


def test_record_proactive_messages_renders_missing_context_as_empty(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent_name(db, workspace_id, AgentRole.WRITER)
    proactive.register_proactive_trigger(
        trigger="render_a2",
        agent=writer,
        kind=proactive.PROACTIVE_KIND_REPORT,
        content="《$title》片段「$excerpt」",
        condition=lambda context: True,
    )

    recorded = proactive.record_proactive_messages(
        db, workspace_id, "render_a2", {"title": "第一章"}
    )
    assert len(recorded) == 1
    assert recorded[0].content == "《第一章》片段「」"


def test_record_proactive_messages_respects_disabled_switch(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path, proactive_enabled=False)
    writer = _agent_name(db, workspace_id, AgentRole.WRITER)
    proactive.register_proactive_trigger(
        trigger="disabled_a2",
        agent=writer,
        kind=proactive.PROACTIVE_KIND_REPORT,
        content="文案",
        condition=lambda context: True,
    )

    assert proactive.record_proactive_messages(db, workspace_id, "disabled_a2", {}) == []
    with db.workspace_session(workspace_id) as session:
        assert session.query(Message).count() == 0


def test_reviewer_registered_for_style_set_and_plot_planted(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)

    styled = proactive.evaluate_proactive_triggers(
        db, workspace_id, "style_set", {"description": "平实克制短句"}
    )
    assert styled == [
        proactive.ProactiveCandidate(
            agent="审稿",
            kind=proactive.PROACTIVE_KIND_CONSISTENCY,
            content=(
                "风格锚点定了：「$description」。"
                "我盯着设定看了一遍，开头那句跟「$description」会不会打架？"
            ),
        )
    ]

    planted = proactive.evaluate_proactive_triggers(db, workspace_id, "plot_planted", {})
    assert len(planted) == 1
    assert planted[0].agent == "审稿"
    assert planted[0].kind == proactive.PROACTIVE_KIND_CONSISTENCY
    assert planted[0].content == (
        "线索「$content」埋下了。我记进时间线，回头逐章对照，别让它断在半路。"
    )


def test_editor_direction_fires_only_first_round_without_style_anchor(
    tmp_path: Path,
) -> None:
    db, workspace_id = _make_db(tmp_path)

    fired = proactive.evaluate_proactive_triggers(
        db,
        workspace_id,
        "talk_first_round",
        {"first_round": True, "has_style_anchor": False},
    )
    assert fired == [
        proactive.ProactiveCandidate(
            agent="总编",
            kind=proactive.PROACTIVE_KIND_DIRECTION,
            content="这部作品的方向还没定：整体基调、核心冲突，咱们先把这些捋清楚再动笔。",
        )
    ]
    assert (
        proactive.evaluate_proactive_triggers(
            db,
            workspace_id,
            "talk_first_round",
            {"first_round": True, "has_style_anchor": True},
        )
        == []
    )
    assert (
        proactive.evaluate_proactive_triggers(
            db,
            workspace_id,
            "talk_first_round",
            {"first_round": False, "has_style_anchor": False},
        )
        == []
    )


def test_record_talk_direction_persists_payload_and_event(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    recorded = proactive.record_proactive_messages(
        db,
        workspace_id,
        "talk_first_round",
        {"first_round": True, "has_style_anchor": False},
    )
    assert len(recorded) == 1
    message = recorded[0]
    assert message.actor == "总编"
    assert message.content == "这部作品的方向还没定：整体基调、核心冲突，咱们先把这些捋清楚再动笔。"
    assert json.loads(message.payload) == {
        "initiator": proactive.INITIATOR_AGENT,
        "kind": proactive.PROACTIVE_KIND_DIRECTION,
        "trigger": "talk_first_round",
    }

    events = list_events(db, workspace_id)
    assert [event.type for event in events] == ["agent.message"]
    assert json.loads(events[0].payload) == json.loads(message.payload)
