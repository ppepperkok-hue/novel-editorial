"""N28-E S4 tests: patience pool three-state counts, pool value, CLI visibility.

The pool is computed read-only from behavior_timeline (no new table):
rejected counts decision:reject / delegation:refused relationship rows,
overridden counts override:* viewpoint rows, conflict counts kind=conflict
rows. Pool value = clamp(effective patience - weighted consumption, 0, 10),
and the event-driven "ignored" judgment recalls whole pending days at query
time only - no countdown, no scan, no automatic action (N29).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from novel_editorial.cli.app import app
from novel_editorial.core.config import load_settings
from novel_editorial.core.discussion import (
    contribute_to_discussion,
    open_discussion,
    summarize_discussion,
)
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.evolution import apply_param_drift
from novel_editorial.core.patience import (
    CONFLICT_WEIGHT,
    OVERRIDDEN_WEIGHT,
    REJECTED_WEIGHT,
    PatienceStateCounts,
    count_patience_states,
    patience_consumption,
    patience_pool,
    pending_ignore_days,
)
from novel_editorial.store.db import DB
from novel_editorial.store.models import Agent, AgentRole, BehaviorTimeline

runner = CliRunner()


def _create_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))
    result = runner.invoke(app, ["works", "create", "耐心之书"])
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
    created_at: datetime | None = None,
) -> BehaviorTimeline:
    with db.workspace_session(workspace_id) as session:
        row = BehaviorTimeline(
            workspace_id=workspace_id,
            agent_id=agent_id,
            kind=kind,
            target=target,
            summary=summary,
            source=source,
            created_at=created_at or datetime.now(UTC),
        )
        session.add(row)
        session.commit()
        return row


def test_rejected_counts_relationship_reject_sources_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    for source in ("decision:reject", "decision:reject", "delegation:refused"):
        _insert_entry(
            db,
            workspace_id,
            agent_id=writer.id,
            kind="relationship",
            target="作者",
            source=source,
            summary="被拒绝",
        )
    # Acceptance relationships, impressions and other kinds must not count.
    _insert_entry(
        db,
        workspace_id,
        agent_id=writer.id,
        kind="relationship",
        target="作者",
        source="decision:accept",
        summary="被认可",
    )
    _insert_entry(
        db,
        workspace_id,
        agent_id=writer.id,
        kind="impression",
        target="作者",
        source="decision:reject",
        summary="对我的要求高",
    )

    assert count_patience_states(db, workspace_id, writer.id) == {
        "rejected": 3,
        "overridden": 0,
        "conflict": 0,
    }


def test_overridden_counts_viewpoint_override_prefix_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    for rule in ("reviewer_consistency", "editor_hooks"):
        _insert_entry(
            db,
            workspace_id,
            agent_id=reviewer.id,
            kind="viewpoint",
            target=rule,
            source=f"override:{rule}",
            summary="作者推翻后调整",
        )
    # A refusal viewpoint and a relationship with the same prefix do not count.
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="viewpoint",
        target="reviewer_consistency",
        source="refusal:reviewer_consistency",
        summary="坚持立场",
    )
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="relationship",
        target="作者",
        source="override:reviewer_consistency",
        summary="作者拍板优先",
    )

    assert count_patience_states(db, workspace_id, reviewer.id) == {
        "rejected": 0,
        "overridden": 2,
        "conflict": 0,
    }


def test_conflict_counts_conflict_kind_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    for _ in range(2):
        _insert_entry(
            db,
            workspace_id,
            agent_id=reviewer.id,
            kind="conflict",
            target="放行",
            source="discussion:unresolved",
            summary="分歧未决",
        )
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="viewpoint",
        target="放行",
        source="discussion:x",
        summary="表达了立场",
    )

    assert count_patience_states(db, workspace_id, reviewer.id) == {
        "rejected": 0,
        "overridden": 0,
        "conflict": 2,
    }


def test_consumption_uses_documented_weights() -> None:
    assert REJECTED_WEIGHT == 1
    assert OVERRIDDEN_WEIGHT == 3
    assert CONFLICT_WEIGHT == 1
    states: PatienceStateCounts = {"rejected": 2, "overridden": 1, "conflict": 3}
    assert patience_consumption(states) == 2 * 1 + 1 * 3 + 3 * 1


def test_pool_uses_effective_patience_and_bottoms_on_three_overrides(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)

    pool = patience_pool(db, workspace_id, reviewer.id)
    assert pool["effective_patience"] == 7
    assert pool["consumption"] == 0
    assert pool["pool"] == 7

    for _ in range(3):
        _insert_entry(
            db,
            workspace_id,
            agent_id=reviewer.id,
            kind="viewpoint",
            target="reviewer_consistency",
            source="override:reviewer_consistency",
            summary="作者推翻后调整",
        )
    pool = patience_pool(db, workspace_id, reviewer.id)
    assert pool["states"]["overridden"] == 3
    assert pool["consumption"] == 9
    assert pool["pool"] == 0


def test_pool_follows_patience_drift_and_clamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    assert patience_pool(db, workspace_id, writer.id)["pool"] == 4

    apply_param_drift(db, workspace_id, writer.id, "patience", 3)
    assert patience_pool(db, workspace_id, writer.id)["pool"] == 7

    apply_param_drift(db, workspace_id, writer.id, "patience", 100)
    assert patience_pool(db, workspace_id, writer.id)["effective_patience"] == 10
    assert patience_pool(db, workspace_id, writer.id)["pool"] == 10

    apply_param_drift(db, workspace_id, writer.id, "patience", -100)
    assert patience_pool(db, workspace_id, writer.id)["effective_patience"] == 0
    assert patience_pool(db, workspace_id, writer.id)["pool"] == 0


def test_pool_is_per_partner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    _insert_entry(
        db,
        workspace_id,
        agent_id=writer.id,
        kind="relationship",
        target="作者",
        source="decision:reject",
        summary="稿子被退回",
    )

    assert patience_pool(db, workspace_id, writer.id)["states"]["rejected"] == 1
    assert patience_pool(db, workspace_id, reviewer.id)["states"]["rejected"] == 0


def test_pending_ignore_days_recalls_whole_days_since_latest_pending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    now = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)

    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="viewpoint",
        target="放行",
        source="override:reviewer_consistency",
        summary="作者推翻后调整",
        created_at=now - timedelta(days=2, hours=5),
    )
    assert pending_ignore_days(db, workspace_id, reviewer.id, "放行", now=now) == 2

    # A newer conflict for the same target wins: only one day pending.
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="conflict",
        target="放行",
        source="discussion:unresolved",
        summary="分歧未决",
        created_at=now - timedelta(days=1),
    )
    assert pending_ignore_days(db, workspace_id, reviewer.id, "放行", now=now) == 1
    assert pending_ignore_days(db, workspace_id, reviewer.id, "别的议题", now=now) == 0


def test_pending_ignore_days_none_or_future_means_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    now = datetime(2026, 8, 23, 12, 0, 0, tzinfo=UTC)
    assert pending_ignore_days(db, workspace_id, reviewer.id, "议题", now=now) == 0

    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="conflict",
        target="议题",
        source="discussion:unresolved",
        summary="分歧未决",
        created_at=now + timedelta(days=1),
    )
    assert pending_ignore_days(db, workspace_id, reviewer.id, "议题", now=now) == 0


def test_pending_ignore_days_blank_target_usage_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    reviewer = _agent(_db(), workspace_id, AgentRole.REVIEWER)
    with pytest.raises(NovelError) as excinfo:
        pending_ignore_days(_db(), workspace_id, reviewer.id, "  ")
    assert excinfo.value.code is ErrorCode.USAGE_ERROR


def test_patience_show_lists_pools_counts_and_real_summaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    _insert_entry(
        db,
        workspace_id,
        agent_id=writer.id,
        kind="relationship",
        target="作者",
        source="decision:reject",
        summary="稿子被退回",
    )
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="viewpoint",
        target="reviewer_consistency",
        source="override:reviewer_consistency",
        summary="作者推翻后调整",
    )
    _insert_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="conflict",
        target="放行",
        source="discussion:unresolved",
        summary=(
            "讨论「放行」分歧未决：审稿 坚持立场"
            "（reviewer_consistency：连贯性与一致性优先，前后矛盾必须退稿）"
        ),
    )

    result = runner.invoke(app, ["patience", "show", workspace_id])

    assert result.exit_code == 0, result.output
    lines = result.output.strip().splitlines()
    writer_line = next(line for line in lines if line.startswith("[写手]"))
    reviewer_line = next(line for line in lines if line.startswith("[审稿]"))
    assert writer_line == (
        "[写手] pool=3 patience=4 consumed=1 "
        "rejected=1 overridden=0 conflict=0"
    )
    assert reviewer_line == (
        "[审稿] pool=3 patience=7 consumed=4 "
        "rejected=0 overridden=1 conflict=1"
    )
    assert "rejected: 作者: 稿子被退回 (source=decision:reject)" in result.output
    assert (
        "overridden: reviewer_consistency: 作者推翻后调整 "
        "(source=override:reviewer_consistency)" in result.output
    )
    assert "conflict: 放行: 讨论「放行」分歧未决" in result.output
    assert "(source=discussion:unresolved)" in result.output


def test_patience_show_missing_workspace_raises_business_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NOVEL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("NOVEL_CONFIG", str(tmp_path / "config.toml"))

    result = runner.invoke(app, ["patience", "show", "nope"])

    assert result.exit_code == 1
    assert "workspace not found" in result.output


def test_discussion_divergence_end_to_end_drains_pool(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace_id = _create_workspace(tmp_path, monkeypatch)
    db = _db()
    topic = "放行，忽略矛盾"
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    summarizer = _agent(db, workspace_id, AgentRole.EDITOR_IN_CHIEF)
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

    pool = patience_pool(db, workspace_id, reviewer.id)
    assert pool["states"]["conflict"] == 1
    assert pool["consumption"] == 1
    assert pool["pool"] == 6
