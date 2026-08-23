"""N28-A feedback-loop tests: decide reject/accept write-backs."""

from pathlib import Path

from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.behavior import list_behavior_timeline
from novel_editorial.core.chat import get_agent
from novel_editorial.core.config import load_settings
from novel_editorial.core.decision import decide
from novel_editorial.core.motives import derive_motives, list_motives
from novel_editorial.store.db import DB
from novel_editorial.store.models import (
    Agent,
    AgentMotive,
    AgentRole,
    Draft,
    MotiveKind,
)

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "决策反馈之书", "--genre", "悬疑"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _db() -> DB:
    return DB(load_settings())


def _agent(db: DB, workspace_id: str, role: str) -> Agent:
    return get_agent(db, workspace_id, role)


def _create_draft(db: DB, workspace_id: str, title: str = "第一章") -> str:
    with db.workspace_session(workspace_id) as session:
        draft = Draft(workspace_id=workspace_id, title=title, status="draft")
        session.add(draft)
        session.commit()
        return draft.id


def test_decision_reject_creates_pending_issue_and_stubbornness_drift(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)

    draft_id = _create_draft(db, workspace_id)
    rejected = decide(db, workspace_id, draft_id, action="reject")

    assert rejected.status == "rejected"
    motives = list_motives(db, workspace_id)
    assert len(motives) == 1
    issue = motives[0]
    assert issue.agent_id == writer.id
    assert issue.kind == MotiveKind.PENDING_ISSUE.value
    assert issue.content == "被退稿了，这事还惦记着"
    assert issue.source == "decision:reject"
    assert issue.strength == 100

    traces = list_behavior_timeline(db, workspace_id)
    drift = [row for row in traces if row.source == "drift:decision:reject"]
    assert len(drift) == 1
    assert drift[0].kind == "viewpoint"
    assert drift[0].agent_id == writer.id
    assert drift[0].target == "stubbornness"
    assert drift[0].before_value == "0"
    assert drift[0].after_value == "1"
    assert "event=decision:reject" in drift[0].summary
    with db.workspace_session(workspace_id) as session:
        stored = session.query(Agent).filter_by(id=writer.id).first()
        assert stored is not None
        assert stored.drift_stubbornness == 1


def test_decision_reject_repeat_strengthens_motive_and_drift(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)

    first_id = _create_draft(db, workspace_id)
    decide(db, workspace_id, first_id, action="reject")
    with db.workspace_session(workspace_id) as session:
        stored = (
            session.query(AgentMotive)
            .filter_by(workspace_id=workspace_id, source="decision:reject")
            .first()
        )
        assert stored is not None
        stored.strength = 60
        session.commit()

    second_id = _create_draft(db, workspace_id, title="第二章")
    decide(db, workspace_id, second_id, action="reject")

    issues = [
        motive
        for motive in list_motives(db, workspace_id)
        if motive.source == "decision:reject"
    ]
    assert len(issues) == 1
    assert issues[0].strength == 70
    with db.workspace_session(workspace_id) as session:
        stored = session.query(Agent).filter_by(id=writer.id).first()
        assert stored is not None
        assert stored.drift_stubbornness == 2


def test_decision_accept_clears_draft_goal_and_boosts_proactivity(
    tmp_path: Path, monkeypatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    derive_motives(db, workspace_id, "draft_generated", {"agent_id": writer.id})
    derive_motives(db, workspace_id, "review_conflict")
    assert len(list_motives(db, workspace_id)) == 2

    draft_id = _create_draft(db, workspace_id)
    accepted = decide(db, workspace_id, draft_id, action="accept")

    assert accepted.status == "accepted"
    remaining = list_motives(db, workspace_id)
    assert [motive.kind for motive in remaining] == [MotiveKind.FORESHADOW.value]
    assert all(motive.agent_id != writer.id for motive in remaining)

    traces = list_behavior_timeline(db, workspace_id)
    drift = [row for row in traces if row.source == "drift:decision:accept"]
    assert len(drift) == 1
    assert drift[0].agent_id == writer.id
    assert drift[0].target == "proactivity"
    assert drift[0].before_value == "0"
    assert drift[0].after_value == "1"
    with db.workspace_session(workspace_id) as session:
        stored = session.query(Agent).filter_by(id=writer.id).first()
        assert stored is not None
        assert stored.drift_proactivity == 1


def test_decision_reject_survives_motive_and_drift_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("novel_editorial.core.motives.upsert_motive_feedback", boom)
    monkeypatch.setattr("novel_editorial.core.evolution.apply_param_drift", boom)
    draft_id = _create_draft(db, workspace_id)

    rejected = decide(db, workspace_id, draft_id, action="reject")

    assert rejected.status == "rejected"
    assert list_motives(db, workspace_id) == []
    with db.workspace_session(workspace_id) as session:
        stored = session.query(Agent).filter_by(id=writer.id).first()
        assert stored is not None
        assert stored.drift_stubbornness == 0
    err = capsys.readouterr().err
    assert "warning: motive feedback skipped (upsert decision:reject): boom" in err
    assert "warning: drift write skipped (decision:reject): boom" in err


def test_decision_accept_survives_clear_and_drift_failure(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    derive_motives(db, workspace_id, "draft_generated", {"agent_id": writer.id})

    def boom(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("novel_editorial.core.motives.clear_motives", boom)
    monkeypatch.setattr("novel_editorial.core.evolution.apply_param_drift", boom)
    draft_id = _create_draft(db, workspace_id)

    accepted = decide(db, workspace_id, draft_id, action="accept")

    assert accepted.status == "accepted"
    assert len(list_motives(db, workspace_id)) == 1
    err = capsys.readouterr().err
    assert "warning: motive feedback skipped (clear): boom" in err
    assert "warning: drift write skipped (decision:accept): boom" in err


def test_decision_cli_reject_end_to_end(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    draft_id = _create_draft(db, workspace_id)

    rejected = runner.invoke(app, ["decision", "reject", draft_id])
    assert rejected.exit_code == 0, rejected.output
    assert f"draft {draft_id} rejected" in rejected.output

    motives = runner.invoke(app, ["motives", "list", workspace_id])
    assert motives.exit_code == 0, motives.output
    assert "[写手] [pending_issue] strength=100 source=decision:reject" in motives.output
    assert "被退稿了，这事还惦记着" in motives.output

    timeline = runner.invoke(app, ["behavior", "timeline", workspace_id])
    assert timeline.exit_code == 0, timeline.output
    assert "source=drift:decision:reject" in timeline.output
    assert "stubbornness drift +0 -> +1" in timeline.output


def test_decision_cli_accept_end_to_end(tmp_path: Path, monkeypatch) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    derive_motives(db, workspace_id, "draft_generated", {"agent_id": writer.id})
    draft_id = _create_draft(db, workspace_id)

    accepted = runner.invoke(app, ["decision", "accept", draft_id])
    assert accepted.exit_code == 0, accepted.output
    assert f"draft {draft_id} accepted" in accepted.output

    motives = runner.invoke(app, ["motives", "list", workspace_id])
    assert motives.exit_code == 0, motives.output
    assert motives.output.strip() == "no motives yet"

    timeline = runner.invoke(app, ["behavior", "timeline", workspace_id])
    assert timeline.exit_code == 0, timeline.output
    assert "source=drift:decision:accept" in timeline.output
    assert "proactivity drift +0 -> +1" in timeline.output
