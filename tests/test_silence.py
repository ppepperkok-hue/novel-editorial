"""N28-D S3 acceptance: silence traces after multi-candidate choice evaluations.

Silence is only a trace for a partner who was relevant to the trigger, stayed
quiet, crossed the significance line with a tendency, and whose tendency
actually changed since their last silence row for the same trigger (09 design
silence-definition gates). Unrelated partners, the picked partner, single-
candidate evaluations and unchanged tendencies never produce a row.
"""

from __future__ import annotations

import re
from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core import proactive
from novel_editorial.core.behavior import list_behavior_timeline
from novel_editorial.core.config import Settings, load_settings
from novel_editorial.core.evolution import apply_param_drift
from novel_editorial.core.workspace import create_workspace
from novel_editorial.store.db import DB
from novel_editorial.store.models import (
    Agent,
    AgentMotive,
    AgentRole,
    BehaviorTimeline,
    MotiveKind,
)

runner = CliRunner()


def _make_db(
    tmp_path: Path,
    *,
    proactive_enabled: bool = True,
    proactive_max_per_agent: int = 3,
    freedom_dial: float = 0.0,
    freedom_seed: int = 42,
) -> tuple[DB, str]:
    settings = Settings(
        data_dir=tmp_path / "data",
        config_path=tmp_path / "config.toml",
        proactive_enabled=proactive_enabled,
        proactive_max_per_agent=proactive_max_per_agent,
        freedom_dial=freedom_dial,
        freedom_seed=freedom_seed,
        motive_llm_enabled=False,
    )
    db = DB(settings)
    db.init_schema()
    workspace = create_workspace(db, title="沉默之书", genre="悬疑")
    return db, workspace.id


def _agent_name(db: DB, workspace_id: str, role: str) -> str:
    return _agent_row(db, workspace_id, role).name


def _agent_row(db: DB, workspace_id: str, role: str) -> Agent:
    with db.workspace_session(workspace_id) as session:
        agent = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, role=role)
            .first()
        )
    assert agent is not None
    return agent


def _isolate_trigger_registry(monkeypatch) -> None:
    """Give one test its own registry copy so wired-trigger extras never leak."""
    monkeypatch.setattr(
        proactive,
        "_PROACTIVE_TRIGGERS",
        {
            trigger: list(specs)
            for trigger, specs in proactive._PROACTIVE_TRIGGERS.items()
        },
    )


def _register_talk_contestants(db: DB, workspace_id: str) -> None:
    """Add editor/writer contestants to talk_first_round besides the built-in 总编."""
    editor = _agent_name(db, workspace_id, AgentRole.EDITOR)
    writer = _agent_name(db, workspace_id, AgentRole.WRITER)
    proactive.register_proactive_trigger(
        trigger="talk_first_round",
        agent=editor,
        kind=proactive.PROACTIVE_KIND_REVIEW,
        content="责编候选",
        condition=lambda context: True,
    )
    proactive.register_proactive_trigger(
        trigger="talk_first_round",
        agent=writer,
        kind=proactive.PROACTIVE_KIND_QUESTION,
        content="写手候选",
        condition=lambda context: True,
    )


def _silence_rows(db: DB, workspace_id: str) -> list[BehaviorTimeline]:
    return list_behavior_timeline(db, workspace_id, kind="silence")


def test_relevant_silent_partners_record_silence_with_tendency(
    tmp_path: Path, monkeypatch
) -> None:
    _isolate_trigger_registry(monkeypatch)
    db, workspace_id = _make_db(tmp_path)
    _register_talk_contestants(db, workspace_id)
    editor = _agent_row(db, workspace_id, AgentRole.EDITOR)
    writer = _agent_row(db, workspace_id, AgentRole.WRITER)

    fired = proactive.evaluate_proactive_triggers(
        db,
        workspace_id,
        "talk_first_round",
        {"first_round": True, "has_style_anchor": False},
    )
    assert [candidate.agent for candidate in fired] == ["总编"]

    rows = _silence_rows(db, workspace_id)
    assert {row.agent_id for row in rows} == {editor.id, writer.id}
    by_agent = {row.agent_id: row for row in rows}
    for row in rows:
        assert row.kind == "silence"
        assert row.target == "talk_first_round"
        assert row.source == "talk_first_round"
        assert row.summary.startswith("评估「talk_first_round」相关议题")
        assert "选择不开口" in row.summary
        assert row.before_value is None
    assert by_agent[editor.id].after_value == "倾向 0.48"
    assert by_agent[writer.id].after_value == "倾向 0.40"


def test_unchanged_tendency_does_not_repeat_silence(
    tmp_path: Path, monkeypatch
) -> None:
    _isolate_trigger_registry(monkeypatch)
    db, workspace_id = _make_db(tmp_path)
    _register_talk_contestants(db, workspace_id)
    context = {"first_round": True, "has_style_anchor": False}

    for _ in range(2):
        fired = proactive.evaluate_proactive_triggers(
            db, workspace_id, "talk_first_round", context
        )
        assert [candidate.agent for candidate in fired] == ["总编"]

    rows = _silence_rows(db, workspace_id)
    assert len(rows) == 2


def test_changed_tendency_records_new_silence_with_before_value(
    tmp_path: Path, monkeypatch
) -> None:
    _isolate_trigger_registry(monkeypatch)
    db, workspace_id = _make_db(tmp_path)
    _register_talk_contestants(db, workspace_id)
    editor = _agent_row(db, workspace_id, AgentRole.EDITOR)
    context = {"first_round": True, "has_style_anchor": False}

    proactive.evaluate_proactive_triggers(db, workspace_id, "talk_first_round", context)
    apply_param_drift(
        db, workspace_id, editor.id, "proactivity", -10, event="rejected"
    )
    proactive.evaluate_proactive_triggers(db, workspace_id, "talk_first_round", context)

    rows = _silence_rows(db, workspace_id)
    assert len(rows) == 3
    editor_rows = [row for row in rows if row.agent_id == editor.id]
    assert len(editor_rows) == 2
    assert editor_rows[0].before_value is None
    assert editor_rows[0].after_value == "倾向 0.48"
    assert editor_rows[1].before_value == "倾向 0.48"
    assert editor_rows[1].after_value == "倾向 0.32"


def test_unrelated_partner_gets_no_silence(tmp_path: Path, monkeypatch) -> None:
    _isolate_trigger_registry(monkeypatch)
    db, workspace_id = _make_db(tmp_path)
    editor = _agent_name(db, workspace_id, AgentRole.EDITOR)
    writer = _agent_name(db, workspace_id, AgentRole.WRITER)
    proactive.register_proactive_trigger(
        trigger="style_set",
        agent=editor,
        kind=proactive.PROACTIVE_KIND_DIRECTION,
        content="责编候选",
        condition=lambda context: True,
    )
    proactive.register_proactive_trigger(
        trigger="style_set",
        agent=writer,
        kind=proactive.PROACTIVE_KIND_QUESTION,
        content="写手候选",
        condition=lambda context: True,
    )

    fired = proactive.evaluate_proactive_triggers(
        db, workspace_id, "style_set", {"description": "平实克制短句"}
    )
    assert [candidate.agent for candidate in fired] == ["审稿"]
    # Editor and writer are role-irrelevant for style_set and carry no
    # matching motive, so the coarse filter drops them: no trace at all.
    assert _silence_rows(db, workspace_id) == []


def test_motive_hit_makes_otherwise_irrelevant_partner_silent(
    tmp_path: Path, monkeypatch
) -> None:
    _isolate_trigger_registry(monkeypatch)
    db, workspace_id = _make_db(tmp_path)
    writer = _agent_name(db, workspace_id, AgentRole.WRITER)
    reviewer = _agent_row(db, workspace_id, AgentRole.REVIEWER)
    proactive.register_proactive_trigger(
        trigger="draft_generated",
        agent=reviewer.name,
        kind=proactive.PROACTIVE_KIND_CONSISTENCY,
        content="审稿候选",
        condition=lambda context: context.get("current_version") == 1,
    )
    with db.workspace_session(workspace_id) as session:
        session.add(
            AgentMotive(
                workspace_id=workspace_id,
                agent_id=reviewer.id,
                kind=MotiveKind.GOAL.value,
                content="想确认新章节奏",
                strength=100,
                source="event:draft_generated",
            )
        )
        session.commit()

    fired = proactive.evaluate_proactive_triggers(
        db,
        workspace_id,
        "draft_generated",
        {"title": "第一章", "current_version": 1, "passed": True},
    )
    # Writer is role-relevant and heavier (0.50) than the motive-only reviewer
    # (0.33), so the writer speaks and the reviewer stays silent. The writer's
    # own goal motive comes from the trigger's derive rule, not this test.
    assert [candidate.agent for candidate in fired] == [writer]
    rows = _silence_rows(db, workspace_id)
    assert [row.agent_id for row in rows] == [reviewer.id]
    assert rows[0].after_value == "倾向 0.33"


def test_single_candidate_branch_records_no_silence(
    tmp_path: Path, monkeypatch
) -> None:
    db, workspace_id = _make_db(tmp_path)

    fired = proactive.evaluate_proactive_triggers(
        db, workspace_id, "style_set", {"description": "平实克制短句"}
    )
    assert [candidate.agent for candidate in fired] == ["审稿"]
    # A sole candidate is the deterministic N1 template, not a choice: the
    # silence gate deliberately never runs (N1 compatibility path).
    assert _silence_rows(db, workspace_id) == []


def test_below_threshold_partner_gets_no_silence(
    tmp_path: Path, monkeypatch
) -> None:
    _isolate_trigger_registry(monkeypatch)
    db, workspace_id = _make_db(tmp_path)
    _register_talk_contestants(db, workspace_id)
    editor = _agent_row(db, workspace_id, AgentRole.EDITOR)
    writer = _agent_row(db, workspace_id, AgentRole.WRITER)
    with db.workspace_session(workspace_id) as session:
        row = session.query(Agent).filter_by(id=editor.id).first()
        assert row is not None
        for field in ("proactivity", "stubbornness", "talkativeness", "patience"):
            setattr(row, field, 0)
        session.commit()

    fired = proactive.evaluate_proactive_triggers(
        db,
        workspace_id,
        "talk_first_round",
        {"first_round": True, "has_style_anchor": False},
    )
    assert [candidate.agent for candidate in fired] == ["总编"]
    # Editor's tendency is 0.0 < the significance line: no "想说没说" to
    # trace. Writer stays at 0.40 and does get the trace.
    assert [row.agent_id for row in _silence_rows(db, workspace_id)] == [writer.id]


def test_repeated_evaluations_keep_silence_bounded(
    tmp_path: Path, monkeypatch
) -> None:
    _isolate_trigger_registry(monkeypatch)
    db, workspace_id = _make_db(tmp_path)
    _register_talk_contestants(db, workspace_id)
    context = {"first_round": True, "has_style_anchor": False}

    for _ in range(6):
        fired = proactive.evaluate_proactive_triggers(
            db, workspace_id, "talk_first_round", context
        )
        assert [candidate.agent for candidate in fired] == ["总编"]

    # Unchanged tendencies deduplicate, so the timeline never grows past the
    # first evaluation's rows (N28-G2: 账本不刷屏).
    assert len(_silence_rows(db, workspace_id)) == 2


def test_silence_write_failure_does_not_break_evaluation(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    _isolate_trigger_registry(monkeypatch)
    db, workspace_id = _make_db(tmp_path)
    _register_talk_contestants(db, workspace_id)

    def _boom(*args, **kwargs):
        raise RuntimeError("trace write exploded")

    monkeypatch.setattr(proactive, "record_behavior_entry_safe", _boom)
    fired = proactive.evaluate_proactive_triggers(
        db,
        workspace_id,
        "talk_first_round",
        {"first_round": True, "has_style_anchor": False},
    )
    assert [candidate.agent for candidate in fired] == ["总编"]
    assert "warning: silence trace skipped: trace write exploded" in capsys.readouterr().err


def test_cli_timeline_kind_silence_shows_records_and_dedup(
    tmp_path: Path, monkeypatch
) -> None:
    _isolate_trigger_registry(monkeypatch)
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    created = runner.invoke(app, ["works", "create", "沉默之书", "--genre", "悬疑"])
    assert created.exit_code == 0, created.output
    match = re.search(r"created workspace (\w+):", created.output)
    assert match is not None
    workspace_id = match.group(1)
    db = DB(load_settings())
    _register_talk_contestants(db, workspace_id)
    context = {"first_round": True, "has_style_anchor": False}

    proactive.evaluate_proactive_triggers(
        db, workspace_id, "talk_first_round", context
    )
    shown = runner.invoke(
        app, ["behavior", "timeline", workspace_id, "--kind", "silence"]
    )
    assert shown.exit_code == 0, shown.output
    lines = shown.output.strip().splitlines()
    assert len(lines) == 2
    for line in lines:
        assert "[silence]" in line
        assert "-> talk_first_round:" in line
        assert "倾向" in line
        assert "选择不开口" in line
        assert "source=talk_first_round" in line

    proactive.evaluate_proactive_triggers(
        db, workspace_id, "talk_first_round", context
    )
    shown_again = runner.invoke(
        app, ["behavior", "timeline", workspace_id, "--kind", "silence"]
    )
    assert shown_again.exit_code == 0, shown_again.output
    assert len(shown_again.output.strip().splitlines()) == 2
