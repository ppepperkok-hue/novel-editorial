"""N29-A S1 tests: pool-bottom summon candidates, topic cooldown, triggers.

The natural discussion trigger judgment (N29) reads the patience pool and the
kind=cooldown timeline markers lazily - no timer, no background scan (09
design). S1 judges and hints only: candidates are partners whose pool is 0
and whose pending topic is not cooling, the proactive_enabled switch silences
everything, and the three accumulation paths (decision reject, talk override,
summarize divergence) call the safe check once after the state accumulated.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.decision import decide
from novel_editorial.core.discussion import (
    contribute_to_discussion,
    open_discussion,
    summarize_discussion,
)
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.natural_discussion import (
    COOLDOWN_PERIOD_DAYS,
    check_summon_trigger_safe,
    is_summon_candidate,
    summon_candidates,
    within_cooldown,
)
from novel_editorial.store.db import DB
from novel_editorial.store.models import (
    Agent,
    AgentRole,
    BehaviorTimeline,
    Draft,
)

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "自然讨论之书"])
    assert result.exit_code == 0, result.output
    return result.output.split()[2].rstrip(":")


def _db() -> DB:
    return DB(load_settings())


def _agent(db: DB, workspace_id: str, role: str) -> Agent:
    with db.workspace_session(workspace_id) as session:
        agent = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, role=role)
            .first()
        )
    assert agent is not None
    return agent


def _insert_entry(
    db: DB,
    workspace_id: str,
    *,
    agent_id: str,
    kind: str,
    target: str,
    source: str,
    summary: str = "",
    after_value: str | None = None,
    created_at: datetime | None = None,
) -> BehaviorTimeline:
    with db.workspace_session(workspace_id) as session:
        row = BehaviorTimeline(
            workspace_id=workspace_id,
            agent_id=agent_id,
            kind=kind,
            target=target,
            summary=summary,
            after_value=after_value,
            source=source,
            created_at=created_at or datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        return row


def _bottom_reviewer_by_overrides(
    db: DB, workspace_id: str, *, count: int = 3
) -> Agent:
    """Bottom the reviewer's pool with override rows (weight 3 each)."""
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    for _ in range(count):
        _insert_entry(
            db,
            workspace_id,
            agent_id=reviewer.id,
            kind="viewpoint",
            target="reviewer_consistency",
            source="override:reviewer_consistency",
            summary="作者推翻后调整",
        )
    return reviewer


def _bottom_writer_by_rejections(
    db: DB, workspace_id: str, *, count: int = 4
) -> Agent:
    """Bottom the writer's pool with rejection rows (weight 1 each)."""
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    for _ in range(count):
        _insert_entry(
            db,
            workspace_id,
            agent_id=writer.id,
            kind="relationship",
            target="作者",
            source="decision:reject",
            summary="稿子被退回",
        )
    return writer


def _create_draft(
    db: DB, workspace_id: str, writer_id: str, title: str = "第一章"
) -> Draft:
    with db.workspace_session(workspace_id) as session:
        draft = Draft(
            workspace_id=workspace_id,
            writer_id=writer_id,
            title=title,
            status="draft",
        )
        session.add(draft)
        session.commit()
        return draft


def test_summon_candidates_empty_when_no_pool_bottom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    assert summon_candidates(_db(), workspace_id) == []


def test_summon_candidates_lists_pool_bottom_partners_deterministically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _bottom_writer_by_rejections(db, workspace_id)
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id)

    candidates = summon_candidates(db, workspace_id)

    # Band creation order (总编, 责编, 写手, 审稿); the editor keeps pool 3.
    assert [candidate["agent_name"] for candidate in candidates] == [
        "写手",
        "审稿",
    ]
    writer_entry = candidates[0]
    reviewer_entry = candidates[1]
    assert writer_entry["agent_id"] == writer.id
    assert writer_entry["pool"] == 0
    # Rejections carry no issue namespace, so the writer has no pending topic.
    assert writer_entry["topic"] is None
    assert reviewer_entry["agent_id"] == reviewer.id
    assert reviewer_entry["pool"] == 0
    # The newest pressure is the override row, whose target is the rule id.
    assert reviewer_entry["topic"] == "reviewer_consistency"


def test_summon_candidates_skips_pool_above_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    _bottom_reviewer_by_overrides(db, workspace_id, count=2)

    assert summon_candidates(db, workspace_id) == []


def test_summon_candidates_gated_by_proactive_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("NOVEL_PROACTIVE_ENABLED", "0")
    db = _db()
    _bottom_reviewer_by_overrides(db, workspace_id)

    assert db.settings.proactive_enabled is False
    assert summon_candidates(db, workspace_id) == []


def test_within_cooldown_recalls_newest_marker_lazily(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)
    topic = "放行，忽略矛盾"

    assert not within_cooldown(db, workspace_id, reviewer.id, topic, now=now)

    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="cooldown",
        target=topic,
        source="discussion:summoned",
        summary="议题进入冷却",
        after_value="pool=0",
        created_at=now - timedelta(days=1),
    )
    assert within_cooldown(db, workspace_id, reviewer.id, topic, now=now)

    # Exactly the whole-day period: the window has passed, the topic may
    # re-accumulate (冷却过期重新候选).
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="cooldown",
        target=topic,
        source="discussion:summoned",
        summary="再次进入冷却",
        created_at=now - timedelta(days=COOLDOWN_PERIOD_DAYS),
    )
    assert not within_cooldown(db, workspace_id, reviewer.id, topic, now=now)

    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="cooldown",
        target=topic,
        source="discussion:summoned",
        summary="第三次冷却",
        created_at=now - timedelta(days=5),
    )
    assert not within_cooldown(db, workspace_id, reviewer.id, topic, now=now)

    # A future-dated marker is never within cooldown.
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="cooldown",
        target=topic,
        source="discussion:summoned",
        summary="未来冷却",
        created_at=now + timedelta(days=1),
    )
    assert not within_cooldown(db, workspace_id, reviewer.id, topic, now=now)


def test_within_cooldown_is_per_agent_and_per_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="cooldown",
        target="议题A",
        source="discussion:summoned",
        created_at=now - timedelta(hours=1),
    )

    assert within_cooldown(db, workspace_id, reviewer.id, "议题A", now=now)
    # Another topic for the same partner is not cooling.
    assert not within_cooldown(db, workspace_id, reviewer.id, "议题B", now=now)
    # The same topic for another partner is not cooling.
    assert not within_cooldown(db, workspace_id, writer.id, "议题A", now=now)


@pytest.mark.parametrize(
    ("agent_id", "target"),
    [("", "议题"), ("审稿", "")],
)
def test_within_cooldown_rejects_blank_arguments_as_usage_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    agent_id: str,
    target: str,
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    with pytest.raises(NovelError) as excinfo:
        within_cooldown(_db(), workspace_id, agent_id, target)
    assert excinfo.value.code is ErrorCode.USAGE_ERROR


def test_summon_candidates_respects_topic_cooldown_and_recandidates_after_expiry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _bottom_writer_by_rejections(db, workspace_id)
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id)
    now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="cooldown",
        target="reviewer_consistency",
        source="discussion:summoned",
        created_at=now - timedelta(hours=1),
    )

    # 冷却期内跳过: the reviewer is excluded, the writer (no topic key) stays.
    candidates = summon_candidates(db, workspace_id, now=now)
    assert [candidate["agent_name"] for candidate in candidates] == ["写手"]
    assert candidates[0]["agent_id"] == writer.id

    # A cooldown on a different topic does not exclude the same partner
    # (per-topic granularity, 同议题冷却).
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="cooldown",
        target="别的议题",
        source="discussion:summoned",
        created_at=now - timedelta(hours=1),
    )
    candidates = summon_candidates(db, workspace_id, now=now)
    assert [candidate["agent_name"] for candidate in candidates] == ["写手"]

    # 冷却过期重新候选: after the whole-day period the reviewer is back.
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="cooldown",
        target="reviewer_consistency",
        source="discussion:summoned",
        created_at=now - timedelta(days=COOLDOWN_PERIOD_DAYS),
    )
    candidates = summon_candidates(db, workspace_id, now=now)
    assert [candidate["agent_name"] for candidate in candidates] == [
        "写手",
        "审稿",
    ]
    assert candidates[1]["agent_id"] == reviewer.id


def test_pending_topic_prefers_newest_unresolved_conflict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)
    _bottom_reviewer_by_overrides(db, workspace_id)
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="conflict",
        target="放行，忽略矛盾",
        source="discussion:unresolved",
        summary="分歧未决",
        created_at=now - timedelta(hours=2),
    )

    candidates = summon_candidates(db, workspace_id, now=now)
    assert len(candidates) == 1
    assert candidates[0]["agent_id"] == reviewer.id
    # The newer conflict topic wins over the older override rule id.
    assert candidates[0]["topic"] == "放行，忽略矛盾"

    # A newer resolution closes the conflict group; the pending topic falls
    # back to the newest active override.
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="conflict",
        target="放行，忽略矛盾",
        source="discussion:resolved",
        summary="分歧已解决",
        created_at=now - timedelta(hours=1),
    )
    candidates = summon_candidates(db, workspace_id, now=now)
    assert candidates[0]["topic"] == "reviewer_consistency"


def test_is_summon_candidate_gates_on_pool_and_cooldown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    topic = "放行，忽略矛盾"

    assert not is_summon_candidate(
        db, workspace_id, agent_id=reviewer.id, target=topic
    )

    _bottom_reviewer_by_overrides(db, workspace_id)
    assert is_summon_candidate(
        db, workspace_id, agent_id=reviewer.id, target=topic
    )

    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="cooldown",
        target=topic,
        source="discussion:summoned",
    )
    assert not is_summon_candidate(
        db, workspace_id, agent_id=reviewer.id, target=topic
    )


def test_check_summon_trigger_safe_hints_when_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id)

    assert check_summon_trigger_safe(
        db, workspace_id, agent_id=reviewer.id, target="放行，忽略矛盾"
    )
    captured = capsys.readouterr()
    assert "natural discussion candidate" in captured.err
    assert reviewer.id in captured.err
    assert "放行，忽略矛盾" in captured.err


def test_check_summon_trigger_safe_silent_when_not_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)

    assert not check_summon_trigger_safe(
        db, workspace_id, agent_id=reviewer.id, target="放行，忽略矛盾"
    )
    assert "natural discussion candidate" not in capsys.readouterr().err


def test_check_summon_trigger_safe_silent_when_switch_off(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("NOVEL_PROACTIVE_ENABLED", "0")
    db = _db()
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id)

    assert not check_summon_trigger_safe(
        db, workspace_id, agent_id=reviewer.id, target="放行，忽略矛盾"
    )
    assert "natural discussion candidate" not in capsys.readouterr().err


def test_check_summon_trigger_safe_degrades_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)

    def _boom(
        _db_: DB,
        _workspace_id: str,
        *,
        agent_id: str,
        target: str,
        now: datetime | None = None,
    ) -> bool:
        raise RuntimeError("boom")

    monkeypatch.setattr(
        "novel_editorial.core.natural_discussion.is_summon_candidate", _boom
    )
    assert not check_summon_trigger_safe(
        db, workspace_id, agent_id=reviewer.id, target="放行，忽略矛盾"
    )
    captured = capsys.readouterr()
    assert "warning: natural discussion check skipped" in captured.err
    assert "boom" in captured.err
    assert "natural discussion candidate" not in captured.err


def test_decision_reject_trigger_check_when_writer_bottomed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _bottom_writer_by_rejections(db, workspace_id)
    draft = _create_draft(db, workspace_id, writer.id, title="第一章")

    decide(db, workspace_id, draft.id, action="reject")

    captured = capsys.readouterr()
    assert "natural discussion candidate" in captured.err
    assert writer.id in captured.err
    assert "第一章" in captured.err


def test_decision_reject_trigger_check_silent_without_pool_bottom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    draft = _create_draft(db, workspace_id, writer.id, title="第一章")

    decide(db, workspace_id, draft.id, action="reject")

    assert "natural discussion candidate" not in capsys.readouterr().err


def test_talk_override_trigger_check_when_reviewer_bottomed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id, count=2)

    result = runner.invoke(
        app, ["talk", "send", workspace_id, "@审稿 以老板身份，放行，忽略矛盾"]
    )

    assert result.exit_code == 0, result.output
    assert "natural discussion candidate" in result.output
    assert reviewer.id in result.output
    assert "reviewer_consistency" in result.output


def test_talk_override_trigger_check_silent_without_pool_bottom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)

    result = runner.invoke(
        app, ["talk", "send", workspace_id, "@审稿 以老板身份，放行，忽略矛盾"]
    )

    assert result.exit_code == 0, result.output
    assert "natural discussion candidate" not in result.output


def test_summarize_divergence_trigger_check_when_reviewer_bottomed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id, count=2)
    summarizer = _agent(db, workspace_id, AgentRole.EDITOR_IN_CHIEF)
    topic = "放行，忽略矛盾"

    discussion_id, _ = open_discussion(
        db, workspace_id, topic=topic, participants=[writer, reviewer]
    )
    contribute_to_discussion(
        db, workspace_id, discussion_id=discussion_id, topic=topic, agent=writer
    )
    contribute_to_discussion(
        db, workspace_id, discussion_id=discussion_id, topic=topic, agent=reviewer
    )
    summarize_discussion(
        db,
        workspace_id,
        discussion_id=discussion_id,
        topic=topic,
        summarizer=summarizer,
    )

    captured = capsys.readouterr()
    assert "natural discussion candidate" in captured.err
    assert reviewer.id in captured.err
    assert topic in captured.err


def test_summarize_divergence_trigger_check_silent_without_pool_bottom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    summarizer = _agent(db, workspace_id, AgentRole.EDITOR_IN_CHIEF)
    topic = "放行，忽略矛盾"

    discussion_id, _ = open_discussion(
        db, workspace_id, topic=topic, participants=[writer, reviewer]
    )
    contribute_to_discussion(
        db, workspace_id, discussion_id=discussion_id, topic=topic, agent=writer
    )
    contribute_to_discussion(
        db, workspace_id, discussion_id=discussion_id, topic=topic, agent=reviewer
    )
    summarize_discussion(
        db,
        workspace_id,
        discussion_id=discussion_id,
        topic=topic,
        summarizer=summarizer,
    )

    assert "natural discussion candidate" not in capsys.readouterr().err
