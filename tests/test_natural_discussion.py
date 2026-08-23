"""N29 tests: pool-bottom candidates, cooldown, triggers and natural summon.

The natural discussion trigger judgment (N29) reads the patience pool and the
kind=cooldown timeline markers lazily - no timer, no background scan (09
design). S1 judges and hints only: candidates are partners whose pool is 0
and whose pending topic is not cooling, the proactive_enabled switch silences
everything, and the three accumulation paths (decision reject, talk override,
summarize divergence) call the safe check once after the state accumulated.
S2 adds the actual summon: ``summon_natural_discussion`` opens the full N4
discussion shape around the candidate's pending topic (点将分歧双方 + 主编
总结), appends the kind=natural_discussion marker event, writes no prose and
never decides for the author, and degrades to a warning on any failure.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import literal_column
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.chat import list_messages
from novel_editorial.core.config import load_settings
from novel_editorial.core.decision import decide
from novel_editorial.core.discussion import (
    CONTRIBUTION_TEMPLATES,
    SUMMARY_LEAD,
    conclude_discussion,
    contribute_to_discussion,
    open_discussion,
    summarize_discussion,
)
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.natural_discussion import (
    COOLDOWN_PERIOD_DAYS,
    SUMMON_KIND,
    SUMMON_TRIGGER,
    check_summon_trigger_safe,
    is_summon_candidate,
    summon_candidates,
    summon_natural_discussion,
    within_cooldown,
)
from novel_editorial.core.patience import patience_pool
from novel_editorial.store.db import DB
from novel_editorial.store.events import list_events
from novel_editorial.store.models import (
    Agent,
    AgentRole,
    BehaviorTimeline,
    Draft,
    DraftVersion,
    Message,
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


def test_summarize_trigger_check_silent_after_author_concluded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """拍板即收敛: conclude 后再 summarize 不再对已解决分歧提示自然召集."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id, count=3)
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
    conclude_discussion(
        db, workspace_id, discussion_id=discussion_id, topic=topic, outcome="接受审稿意见"
    )
    summary = summarize_discussion(
        db,
        workspace_id,
        discussion_id=discussion_id,
        topic=topic,
        summarizer=summarizer,
    )

    # 已存在 discussion_decision 时直接跳过触发检查，池底伙伴也不得提示。
    assert "natural discussion candidate" not in capsys.readouterr().err
    # 摘要本身仍然真实产出，守卫只拦触发提示，不拦总结。
    assert "围绕「放行，忽略矛盾」，各方的表态汇总如下：" in summary.content


def test_summon_candidates_reject_cooldown_key_matches_decision_trigger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """被拒池底写手的 pending topic 取最近一次 decision:reject 的章节标题.

    decide reject 的触发键是章节标题（decision.py 的 reject_target），S3 的
    cooldown 写回也用同一把键；summon_candidates 必须查同一把键，否则两入口
    防风暴口径不一致。
    """
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    now = datetime(2026, 8, 24, 12, 0, 0, tzinfo=UTC)
    for title in ["第一章", "第二章", "第三章", "第四章"]:
        draft = _create_draft(db, workspace_id, writer.id, title=title)
        decide(db, workspace_id, draft.id, action="reject")

    candidates = summon_candidates(db, workspace_id, now=now)
    writer_candidates = [
        candidate for candidate in candidates if candidate["agent_id"] == writer.id
    ]
    assert len(writer_candidates) == 1
    # 纯被拒池底伙伴的 pending topic = 最近一条 decision:reject 的 target。
    assert writer_candidates[0]["topic"] == "第四章"

    # 对同一把键写 cooldown 后，summon_candidates 不再列出该写手。
    _insert_entry(
        db,
        workspace_id,
        agent_id=writer.id,
        kind="cooldown",
        target="第四章",
        source="discussion:summoned",
        created_at=now - timedelta(hours=1),
    )
    candidates = summon_candidates(db, workspace_id, now=now)
    assert writer.id not in [candidate["agent_id"] for candidate in candidates]


def _create_draft_version(
    db: DB, workspace_id: str, draft_id: str, content: str
) -> DraftVersion:
    with db.workspace_session(workspace_id) as session:
        version = DraftVersion(
            draft_id=draft_id,
            version=1,
            content=content,
        )
        session.add(version)
        session.commit()
        return version


def _draft_version_content(db: DB, workspace_id: str, draft_id: str) -> str:
    with db.workspace_session(workspace_id) as session:
        row = (
            session.query(DraftVersion)
            .filter_by(draft_id=draft_id)
            .order_by(DraftVersion.version.desc())
            .first()
        )
    assert row is not None
    return row.content


def _messages_in_order(db: DB, workspace_id: str) -> list[Message]:
    with db.workspace_session(workspace_id) as session:
        return (
            session.query(Message)
            .filter_by(workspace_id=workspace_id)
            .order_by(literal_column("rowid"))
            .all()
        )


def test_summon_natural_discussion_full_round_with_reviewer_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """池底审稿（override×3）：召集 = 点将写手 + 主编总结，记录与事件齐全."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    draft = _create_draft(db, workspace_id, writer.id, title="第一章")
    _create_draft_version(db, workspace_id, draft.id, content="正文原样")
    topic = "reviewer_consistency"

    result = summon_natural_discussion(db, workspace_id, reviewer)

    assert result is not None
    assert result["discussion_id"]
    assert result["topic"] == topic
    assert result["agent_id"] == reviewer.id
    assert result["counterpart"] == writer.name
    writer_template = CONTRIBUTION_TEMPLATES[AgentRole.WRITER].format(topic=topic)
    reviewer_template = CONTRIBUTION_TEMPLATES[AgentRole.REVIEWER].format(topic=topic)
    assert result["summary"] == (
        f"{SUMMARY_LEAD.format(topic=topic)}\n"
        f"审稿：{reviewer_template}\n"
        f"写手：{writer_template}"
    )

    messages = _messages_in_order(db, workspace_id)
    assert [json.loads(m.payload)["kind"] for m in messages if m.role != "system"] == [
        "discussion_open",
        "discussion_contribution",
        "discussion_contribution",
        "discussion_summary",
    ]
    assert [m.actor for m in messages if m.role != "system"] == [
        "作者",
        "审稿",
        "写手",
        "总编",
    ]
    # 作者未拍板：讨论是协作链，创作链仍由作者把守。
    assert not any(
        json.loads(m.payload).get("kind") == "discussion_decision" for m in messages
    )
    # 不写正文。
    assert _draft_version_content(db, workspace_id, draft.id) == "正文原样"

    events = list_events(db, workspace_id)
    # 两次发言 + 一次总结各带 agent.message 事件，另追加一条自然召集标记。
    assert [json.loads(e.payload).get("kind") for e in reversed(events)] == [
        "discussion_contribution",
        "discussion_contribution",
        "discussion_summary",
        SUMMON_KIND,
    ]
    marker = events[0]
    assert marker.type == "agent.message"
    assert marker.actor == reviewer.name
    assert json.loads(marker.payload) == {
        "initiator": "agent",
        "kind": SUMMON_KIND,
        "trigger": SUMMON_TRIGGER,
        "agent_id": reviewer.id,
        "topic": topic,
        "discussion_id": result["discussion_id"],
    }


def test_summon_natural_discussion_writer_candidate_pairs_with_reviewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """纯被拒池底写手：议题取最近 reject 章节，对方默认点将审稿."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    for title in ["第一章", "第二章", "第三章", "第四章"]:
        draft = _create_draft(db, workspace_id, writer.id, title=title)
        decide(db, workspace_id, draft.id, action="reject")
    assert patience_pool(db, workspace_id, writer.id)["pool"] == 0

    result = summon_natural_discussion(db, workspace_id, writer)

    assert result is not None
    assert result["topic"] == "第四章"
    assert result["agent_id"] == writer.id
    assert result["counterpart"] == reviewer.name


def test_summon_natural_discussion_skips_when_pool_not_bottom(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id, count=2)
    assert patience_pool(db, workspace_id, reviewer.id)["pool"] == 1

    result = summon_natural_discussion(db, workspace_id, reviewer)

    assert result is None
    assert list_messages(db, workspace_id) == []
    assert list_events(db, workspace_id) == []


def test_summon_natural_discussion_skips_when_topic_in_cooldown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id)
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="cooldown",
        target="reviewer_consistency",
        source="discussion:summoned",
        created_at=datetime.now(UTC) - timedelta(hours=1),
    )

    result = summon_natural_discussion(db, workspace_id, reviewer)

    assert result is None
    assert list_messages(db, workspace_id) == []
    assert list_events(db, workspace_id) == []


def test_summon_natural_discussion_silent_when_switch_off(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    monkeypatch.setenv("NOVEL_PROACTIVE_ENABLED", "0")
    db = _db()
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id)

    result = summon_natural_discussion(db, workspace_id, reviewer)

    assert result is None
    assert "natural discussion summon" not in capsys.readouterr().err
    assert list_messages(db, workspace_id) == []
    assert list_events(db, workspace_id) == []


def test_summon_natural_discussion_skips_without_pending_topic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    # pool==0 但没有任何 override/conflict/reject 记录，拿不出议题。
    with db.workspace_session(workspace_id) as session:
        row = session.query(Agent).filter_by(id=reviewer.id).first()
        assert row is not None
        row.patience = 0
        session.commit()
    assert patience_pool(db, workspace_id, reviewer.id)["pool"] == 0

    result = summon_natural_discussion(db, workspace_id, reviewer)

    assert result is None
    assert "no pending topic" in capsys.readouterr().err
    assert list_messages(db, workspace_id) == []


def test_summon_natural_discussion_degrades_on_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("novel_editorial.core.discussion.open_discussion", _boom)
    result = summon_natural_discussion(db, workspace_id, reviewer)

    assert result is None
    captured = capsys.readouterr()
    assert "warning: natural discussion summon skipped" in captured.err
    assert "boom" in captured.err
    assert list_messages(db, workspace_id) == []
    assert list_events(db, workspace_id) == []


def test_summon_natural_discussion_partial_write_failure_warns(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id)

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("summary boom")

    monkeypatch.setattr("novel_editorial.core.discussion.summarize_discussion", _boom)
    result = summon_natural_discussion(db, workspace_id, reviewer)

    assert result is None
    assert "summary boom" in capsys.readouterr().err
    # 开场与双方发言已各自提交（N4 每步独立事务）；失败只告警，不反噬业务。
    messages = _messages_in_order(db, workspace_id)
    assert len(messages) == 3
    assert len(list_events(db, workspace_id)) == 2
    assert "discussion_decision" not in [
        json.loads(m.payload).get("kind") for m in messages
    ]


def test_summon_natural_discussion_conflict_topic_recalls_other_participant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """分歧议题按 override/conflict 记录取对方：另一方的讨论沉积分明."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id)
    summarizer = _agent(db, workspace_id, AgentRole.EDITOR_IN_CHIEF)
    topic = "放行，忽略矛盾"

    previous_id, _ = open_discussion(
        db, workspace_id, topic=topic, participants=[writer, reviewer]
    )
    contribute_to_discussion(
        db, workspace_id, discussion_id=previous_id, topic=topic, agent=writer
    )
    contribute_to_discussion(
        db, workspace_id, discussion_id=previous_id, topic=topic, agent=reviewer
    )
    summarize_discussion(
        db,
        workspace_id,
        discussion_id=previous_id,
        topic=topic,
        summarizer=summarizer,
    )

    result = summon_natural_discussion(db, workspace_id, reviewer)

    assert result is not None
    assert result["topic"] == topic
    assert result["counterpart"] == writer.name
    assert result["discussion_id"] != previous_id


def test_summon_natural_discussion_editor_in_chief_candidate_skipped(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """池底总编候选：总编主持讨论、不作分歧一方，召集跳过且无自我总结."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    editor = _agent(db, workspace_id, AgentRole.EDITOR_IN_CHIEF)
    with db.workspace_session(workspace_id) as session:
        row = session.query(Agent).filter_by(id=editor.id).first()
        assert row is not None
        row.patience = 0
        session.commit()
    _insert_entry(
        db,
        workspace_id,
        agent_id=editor.id,
        kind="viewpoint",
        target="主线基调",
        source="override:主线基调",
        summary="作者推翻后调整",
    )
    assert patience_pool(db, workspace_id, editor.id)["pool"] == 0

    result = summon_natural_discussion(db, workspace_id, editor)

    assert result is None
    assert "editor-in-chief" in capsys.readouterr().err
    assert list_messages(db, workspace_id) == []
    assert list_events(db, workspace_id) == []


def test_summon_natural_discussion_counterpart_never_editor_in_chief(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """对方点将排除总编：议题沉淀只指向总编时回退默认配对（审稿↔写手）."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _bottom_reviewer_by_overrides(db, workspace_id)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    editor = _agent(db, workspace_id, AgentRole.EDITOR_IN_CHIEF)
    topic = "reviewer_consistency"
    # 前一轮讨论中总编作为参与方在议题命名空间留过 viewpoint 沉淀。
    _insert_entry(
        db,
        workspace_id,
        agent_id=editor.id,
        kind="viewpoint",
        target=topic,
        source="discussion:previous",
        summary="表达了立场",
        after_value="表达了立场",
    )

    result = summon_natural_discussion(db, workspace_id, reviewer)

    assert result is not None
    assert result["topic"] == topic
    assert result["agent_id"] == reviewer.id
    # 总编不作分歧一方：回退默认配对点将写手，总编只负责通气总结。
    assert result["counterpart"] == writer.name
    messages = _messages_in_order(db, workspace_id)
    contributions = [
        m
        for m in messages
        if json.loads(m.payload).get("kind") == "discussion_contribution"
    ]
    assert [m.actor for m in contributions] == [reviewer.name, writer.name]
    summaries = [
        m
        for m in messages
        if json.loads(m.payload).get("kind") == "discussion_summary"
    ]
    assert len(summaries) == 1
    assert summaries[0].actor == editor.name


def test_summon_natural_discussion_no_topic_contract_visible_but_not_summoned(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """no-topic 契约：候选列表保留可见性，召集侧跳过并告警、不写任何记录."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    with db.workspace_session(workspace_id) as session:
        row = session.query(Agent).filter_by(id=writer.id).first()
        assert row is not None
        row.patience = 0
        session.commit()
    assert patience_pool(db, workspace_id, writer.id)["pool"] == 0

    # 可见性：无议题池底伙伴仍被候选列表列出，topic=None。
    candidates = summon_candidates(db, workspace_id)
    writer_entries = [
        candidate for candidate in candidates if candidate["agent_id"] == writer.id
    ]
    assert len(writer_entries) == 1
    assert writer_entries[0]["topic"] is None

    # 召集侧：无议题无法开 N4 轮次，跳过并告警，不写消息与事件。
    result = summon_natural_discussion(db, workspace_id, writer)

    assert result is None
    assert "no pending topic" in capsys.readouterr().err
    assert list_messages(db, workspace_id) == []
    assert list_events(db, workspace_id) == []


def test_summon_natural_discussion_cli_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI 冒烟：池底审稿（override×3）召集后记录与事件齐全、正文无变化."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    draft = _create_draft(db, workspace_id, writer.id, title="第一章")
    _create_draft_version(db, workspace_id, draft.id, content="正文原样")
    for _ in range(3):
        result = runner.invoke(
            app, ["talk", "send", workspace_id, "@审稿 以老板身份，放行，忽略矛盾"]
        )
        assert result.exit_code == 0, result.output
    assert patience_pool(db, workspace_id, reviewer.id)["pool"] == 0

    summoned = summon_natural_discussion(db, workspace_id, reviewer)

    assert summoned is not None
    listed = runner.invoke(app, ["talk", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    for mark in ("[author·讨论·开场]", "[agent·讨论·发言]", "[agent·讨论·总结]"):
        assert mark in listed.output
    assert "[author·讨论·拍板]" not in listed.output

    events_listed = runner.invoke(app, ["events", "list", workspace_id])
    assert events_listed.exit_code == 0, events_listed.output
    assert '"kind": "natural_discussion"' in events_listed.output
    assert '"initiator": "agent"' in events_listed.output

    # 输出真实摘要：自然召集的总结走 N4 确定性模板。
    assert SUMMARY_LEAD.format(topic="reviewer_consistency") in summoned["summary"]
    assert _draft_version_content(db, workspace_id, draft.id) == "正文原样"


def test_summon_natural_discussion_cli_smoke_editor_in_chief_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """CLI 冒烟：池底总编召集被跳过，不产生任何讨论记录或召集事件."""
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    editor = _agent(db, workspace_id, AgentRole.EDITOR_IN_CHIEF)
    with db.workspace_session(workspace_id) as session:
        row = session.query(Agent).filter_by(id=editor.id).first()
        assert row is not None
        row.patience = 0
        session.commit()
    _insert_entry(
        db,
        workspace_id,
        agent_id=editor.id,
        kind="viewpoint",
        target="主线基调",
        source="override:主线基调",
        summary="作者推翻后调整",
    )
    assert patience_pool(db, workspace_id, editor.id)["pool"] == 0

    summoned = summon_natural_discussion(db, workspace_id, editor)

    assert summoned is None
    listed = runner.invoke(app, ["talk", "list", workspace_id])
    assert listed.exit_code == 0, listed.output
    assert "[author·讨论·开场]" not in listed.output
    assert "[agent·讨论·总结]" not in listed.output
    events_listed = runner.invoke(app, ["events", "list", workspace_id])
    assert events_listed.exit_code == 0, events_listed.output
    assert '"kind": "natural_discussion"' not in events_listed.output
