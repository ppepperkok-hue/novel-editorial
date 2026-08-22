"""N27 S3 tests: free-will behavior selector (coarse filter, weights, pick)."""

from pathlib import Path

import pytest
from sqlalchemy import func

from novel_editorial.core.behavior import record_behavior_entry
from novel_editorial.core.choice import (
    DEFAULT_MIN_WEIGHT,
    FEEDBACK_FLOOR,
    ChoiceCandidate,
    FeedbackCounts,
    PersonalityParams,
    coarse_filter,
    compute_weights,
    evaluate_choice,
    load_feedback_counts,
    pick_candidate,
)
from novel_editorial.core.config import Settings
from novel_editorial.core.errors import ErrorCode, NovelError
from novel_editorial.core.workspace import create_workspace
from novel_editorial.store.db import DB
from novel_editorial.store.models import (
    Agent,
    AgentMotive,
    AgentRole,
    BehaviorTimeline,
    MotiveKind,
)


def _make_db(tmp_path: Path) -> tuple[DB, str]:
    settings = Settings(data_dir=tmp_path / "data", config_path=tmp_path / "config.toml")
    db = DB(settings)
    db.init_schema()
    workspace = create_workspace(db, title="选择之书", genre="悬疑")
    return db, workspace.id


def _agent(db: DB, workspace_id: str, role: str) -> Agent:
    with db.workspace_session(workspace_id) as session:
        agent = (
            session.query(Agent)
            .filter_by(workspace_id=workspace_id, role=role)
            .first()
        )
    assert agent is not None
    return agent


def _motive(
    agent_id: str,
    kind: str,
    content: str,
    *,
    strength: int = 100,
) -> AgentMotive:
    """A detached AgentMotive object: motives enter the selector as arguments."""
    return AgentMotive(
        workspace_id="w",
        agent_id=agent_id,
        kind=kind,
        content=content,
        strength=strength,
    )


def _params(*, value: int = 5) -> PersonalityParams:
    return PersonalityParams(
        proactivity=value,
        stubbornness=value,
        talkativeness=value,
        patience=value,
    )


def test_choice_constants_are_sane() -> None:
    assert 0.0 < DEFAULT_MIN_WEIGHT < 1.0
    assert 0.0 < FEEDBACK_FLOOR < 1.0


def test_candidate_carries_agent_kind_content_template() -> None:
    candidate = ChoiceCandidate(agent="writer", kind="proactive_report", content="《$title》写完了")
    assert candidate.agent == "writer"
    assert candidate.kind == "proactive_report"
    assert candidate.content == "《$title》写完了"


def test_coarse_filter_keeps_writer_for_draft_drops_reviewer(
    tmp_path: Path,
) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    writer_candidate = ChoiceCandidate(
        agent=writer.id,
        kind="proactive_report",
        content="《$title》初稿写完了",
    )
    reviewer_candidate = ChoiceCandidate(
        agent=reviewer.id,
        kind="proactive_consistency",
        content="风格锚点检查",
    )
    agents = {writer.id: writer.role, reviewer.id: reviewer.role}

    kept = coarse_filter(
        "draft_generated",
        [writer_candidate, reviewer_candidate],
        agents,
        [],
    )

    assert kept == [writer_candidate]


def test_coarse_filter_motive_hit_keeps_partner_outside_role_duty(
    tmp_path: Path,
) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    candidate = ChoiceCandidate(agent=writer.id, kind="proactive_question", content="这事还惦记着")
    pending = _motive(writer.id, MotiveKind.PENDING_ISSUE.value, "被拒了，这事还惦记着")

    kept = coarse_filter(
        "review_conflict",
        [candidate],
        {writer.id: writer.role},
        [pending],
    )

    assert kept == [candidate]


def test_coarse_filter_unrelated_partner_is_skipped(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    candidate = ChoiceCandidate(agent=writer.id, kind="proactive_report", content="交稿")

    kept = coarse_filter(
        "plot_planted",
        [candidate],
        {writer.id: writer.role},
        [],
    )

    assert kept == []


def test_coarse_filter_motive_content_keyword_hit(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    editor = _agent(db, workspace_id, AgentRole.EDITOR)
    candidate = ChoiceCandidate(agent=editor.id, kind="proactive_review", content="风格问题")
    impression = _motive(editor.id, MotiveKind.IMPRESSION.value, "对作者风格有印象")

    kept = coarse_filter(
        "style_set",
        [candidate],
        {editor.id: editor.role},
        [impression],
    )

    assert kept == [candidate]


def test_coarse_filter_empty_candidates_returns_empty(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)

    assert (
        coarse_filter(
            "draft_generated",
            [],
            {writer.id: writer.role},
            [],
        )
        == []
    )


def test_coarse_filter_unknown_trigger_is_usage_error(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)

    with pytest.raises(NovelError) as exc:
        coarse_filter(
            "mystery_trigger",
            [ChoiceCandidate(agent=writer.id, kind="proactive_report", content="x")],
            {writer.id: writer.role},
            [],
        )
    assert exc.value.code == ErrorCode.USAGE_ERROR
    assert "unknown choice trigger" in exc.value.message


def test_coarse_filter_unknown_role_still_kept_by_motive(tmp_path: Path) -> None:
    writer = ChoiceCandidate(agent="w1", kind="proactive_question", content="惦记")
    pending = _motive("w1", MotiveKind.PENDING_ISSUE.value, "被拒了")

    kept = coarse_filter(
        "decision_reject",
        [writer],
        {"w1": "mystery_role"},
        [pending],
    )

    assert kept == [writer]


def test_compute_weights_relevance_grades(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    both = ChoiceCandidate(agent=reviewer.id, kind="proactive_consistency", content="矛盾检查")
    motive_only = ChoiceCandidate(agent=writer.id, kind="proactive_question", content="惦记")
    foreshadow = _motive(reviewer.id, MotiveKind.FORESHADOW.value, "审稿时发现前后矛盾")
    pending = _motive(writer.id, MotiveKind.PENDING_ISSUE.value, "被拒了")
    agents = {writer.id: writer.role, reviewer.id: reviewer.role}
    params = {
        writer.id: _params(),
        reviewer.id: _params(),
    }

    role_and_motive = compute_weights(
        [both],
        [foreshadow, pending],
        params,
        agents=agents,
        trigger="review_conflict",
    )
    motive_only_weight = compute_weights(
        [motive_only],
        [foreshadow, pending],
        params,
        agents=agents,
        trigger="review_conflict",
    )[0]
    role_only_weight = compute_weights(
        [both],
        [pending],
        params,
        agents=agents,
        trigger="review_conflict",
    )[0]

    # relevance 1.0 / 0.8 / 0.6 x neutral personality 0.5
    assert role_and_motive == pytest.approx([0.5])
    assert role_only_weight == pytest.approx(0.4)
    assert motive_only_weight == pytest.approx(0.3)


def test_compute_weights_motive_strength_scales(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    weak = ChoiceCandidate(agent=writer.id, kind="proactive_report", content="交稿")
    strong = ChoiceCandidate(agent=writer.id, kind="proactive_report", content="交稿")
    neutral = ChoiceCandidate(agent=writer.id, kind="proactive_report", content="交稿")
    weak_goal = _motive(writer.id, MotiveKind.GOAL.value, "新章已交", strength=50)
    strong_goal = _motive(writer.id, MotiveKind.GOAL.value, "新章已交", strength=100)
    agents = {writer.id: writer.role}
    params = {writer.id: _params()}

    weak_weight = compute_weights(
        [weak],
        [weak_goal],
        params,
        agents=agents,
        trigger="draft_generated",
    )[0]
    strong_weight = compute_weights(
        [strong],
        [strong_goal],
        params,
        agents=agents,
        trigger="draft_generated",
    )[0]
    neutral_weight = compute_weights(
        [neutral],
        [],
        params,
        agents=agents,
        trigger="draft_generated",
    )[0]

    assert weak_weight == pytest.approx(0.25)
    assert strong_weight == pytest.approx(0.5)
    # no motive -> neutral 1.0 motive factor, role-only relevance 0.8
    assert neutral_weight == pytest.approx(0.4)
    assert strong_weight > weak_weight


def test_compute_weights_personality_scales(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    candidate = ChoiceCandidate(agent=writer.id, kind="proactive_report", content="交稿")
    goal = _motive(writer.id, MotiveKind.GOAL.value, "新章已交")
    agents = {writer.id: writer.role}

    loud = compute_weights(
        [candidate],
        [goal],
        {writer.id: _params(value=10)},
        agents=agents,
        trigger="draft_generated",
    )[0]
    quiet = compute_weights(
        [candidate],
        [goal],
        {writer.id: _params(value=0)},
        agents=agents,
        trigger="draft_generated",
    )[0]
    missing = compute_weights(
        [candidate],
        [goal],
        {},
        agents=agents,
        trigger="draft_generated",
    )[0]

    assert loud == pytest.approx(1.0)
    assert quiet == pytest.approx(0.0)
    assert missing == pytest.approx(0.5)


def test_compute_weights_rejections_lower_tendency_monotonically(
    tmp_path: Path,
) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    candidate = ChoiceCandidate(agent=writer.id, kind="proactive_report", content="交稿")
    goal = _motive(writer.id, MotiveKind.GOAL.value, "新章已交")
    agents = {writer.id: writer.role}
    params = {writer.id: _params()}

    weights = [
        compute_weights(
            [candidate],
            [goal],
            params,
            {writer.id: FeedbackCounts(rejected=rejected)},
            agents=agents,
            trigger="draft_generated",
        )[0]
        for rejected in range(6)
    ]

    assert weights == sorted(weights, reverse=True)
    assert len(set(weights)) == len(weights)
    assert weights[5] < weights[0]


def test_compute_weights_acceptances_restore_tendency(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    candidate = ChoiceCandidate(agent=writer.id, kind="proactive_report", content="交稿")
    goal = _motive(writer.id, MotiveKind.GOAL.value, "新章已交")
    agents = {writer.id: writer.role}
    params = {writer.id: _params()}

    weights = [
        compute_weights(
            [candidate],
            [goal],
            params,
            {writer.id: FeedbackCounts(rejected=4, accepted=accepted)},
            agents=agents,
            trigger="draft_generated",
        )[0]
        for accepted in range(6)
    ]

    assert weights == sorted(weights)
    assert weights[-1] == pytest.approx(0.5)
    # rejected=4 x penalty 0.25 halves the tendency; acceptances restore it
    assert weights[0] == pytest.approx(0.25)
    assert weights[-1] > weights[0]


def test_compute_weights_feedback_floor_never_silences_fully(
    tmp_path: Path,
) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    candidate = ChoiceCandidate(agent=writer.id, kind="proactive_report", content="交稿")
    goal = _motive(writer.id, MotiveKind.GOAL.value, "新章已交")
    agents = {writer.id: writer.role}
    params = {writer.id: _params()}

    weight = compute_weights(
        [candidate],
        [goal],
        params,
        {writer.id: FeedbackCounts(rejected=99)},
        agents=agents,
        trigger="draft_generated",
    )[0]

    assert weight == pytest.approx(0.5 * FEEDBACK_FLOOR)


def test_compute_weights_without_trigger_is_neutral(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    candidate = ChoiceCandidate(agent=writer.id, kind="proactive_report", content="交稿")

    weights = compute_weights([candidate], [], {writer.id: _params()})

    assert weights == pytest.approx([0.5])


def test_compute_weights_output_stays_in_unit_range(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    candidate = ChoiceCandidate(agent=writer.id, kind="proactive_report", content="交稿")
    goal = _motive(writer.id, MotiveKind.GOAL.value, "新章已交")
    agents = {writer.id: writer.role}

    weights = compute_weights(
        [candidate, candidate],
        [goal],
        {writer.id: _params(value=10)},
        {writer.id: FeedbackCounts(rejected=0, accepted=99)},
        agents=agents,
        trigger="draft_generated",
    )

    assert all(0.0 <= weight <= 1.0 for weight in weights)


def test_compute_weights_empty_candidates_returns_empty() -> None:
    assert compute_weights([], [], {}) == []


def test_pick_candidate_dial_out_of_range_raises_usage_error() -> None:
    for dial in (-0.1, 1.01):
        with pytest.raises(NovelError) as exc:
            pick_candidate([0.5, 0.5], dial, seed=1)
        assert exc.value.code == ErrorCode.USAGE_ERROR
        assert "dial" in exc.value.message


def test_pick_candidate_empty_and_all_zero_return_none() -> None:
    assert pick_candidate([], dial=0.5, seed=1) is None
    assert pick_candidate([0.0, 0.0], dial=0.5, seed=1) is None


def test_pick_candidate_negative_weight_is_usage_error() -> None:
    with pytest.raises(NovelError) as exc:
        pick_candidate([0.5, -0.1], dial=0.5, seed=1)
    assert exc.value.code == ErrorCode.USAGE_ERROR


def test_pick_candidate_dial_zero_always_argmax() -> None:
    weighted = [0.1, 0.8, 0.05, 0.05]
    picks = {pick_candidate(weighted, dial=0.0, seed=seed) for seed in range(60)}
    assert picks == {1}


def test_pick_candidate_same_seed_reproduces_exact_pick() -> None:
    weighted = [0.6, 0.3, 0.1]
    assert pick_candidate(weighted, dial=0.5, seed=42) == pick_candidate(
        weighted, dial=0.5, seed=42
    )


def test_pick_candidate_different_seeds_produce_variants() -> None:
    weighted = [0.6, 0.3, 0.1]
    picks = {pick_candidate(weighted, dial=0.5, seed=seed) for seed in range(300)}
    assert len(picks) >= 2


def test_pick_candidate_dial_one_can_pick_low_weight_candidate() -> None:
    weighted = [0.8, 0.1, 0.1]
    picks = {pick_candidate(weighted, dial=1.0, seed=seed) for seed in range(200)}
    assert 0 in picks
    assert picks - {0} != set()


def test_evaluate_choice_empty_candidates_returns_empty(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)

    picked = evaluate_choice(
        "draft_generated",
        [],
        {writer.id: writer.role},
        [],
        {writer.id: _params()},
    )

    assert picked == []


def test_evaluate_choice_below_threshold_returns_empty(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    candidate = ChoiceCandidate(agent=writer.id, kind="proactive_report", content="交稿")

    picked = evaluate_choice(
        "draft_generated",
        [candidate],
        {writer.id: writer.role},
        [],
        {writer.id: _params()},
        min_weight=0.99,
    )

    assert picked == []


def test_evaluate_choice_returns_the_picked_candidate(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    candidate = ChoiceCandidate(
        agent=writer.id,
        kind="proactive_report",
        content="《$title》初稿写完了",
    )
    goal = _motive(writer.id, MotiveKind.GOAL.value, "新章已交")

    picked = evaluate_choice(
        "draft_generated",
        [candidate],
        {writer.id: writer.role},
        [goal],
        {writer.id: _params()},
        dial=0.0,
    )

    assert picked == [candidate]


def test_evaluate_choice_dial_zero_is_seed_independent(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    editor = _agent(db, workspace_id, AgentRole.EDITOR)
    weak = ChoiceCandidate(agent=editor.id, kind="proactive_review", content="弱候选")
    strong = ChoiceCandidate(agent=writer.id, kind="proactive_report", content="强候选")
    strong_goal = _motive(writer.id, MotiveKind.GOAL.value, "新章已交", strength=100)
    weak_goal = _motive(editor.id, MotiveKind.GOAL.value, "新章已交", strength=10)

    picks = {
        evaluate_choice(
            "draft_generated",
            [weak, strong],
            {writer.id: writer.role, editor.id: editor.role},
            [weak_goal, strong_goal],
            {writer.id: _params(), editor.id: _params()},
            dial=0.0,
            seed=seed,
        )[0].content
        for seed in range(30)
    }

    assert picks == {"强候选"}


def test_evaluate_choice_min_weight_out_of_range_is_usage_error(
    tmp_path: Path,
) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)

    with pytest.raises(NovelError) as exc:
        evaluate_choice(
            "draft_generated",
            [ChoiceCandidate(agent=writer.id, kind="proactive_report", content="x")],
            {writer.id: writer.role},
            [],
            {writer.id: _params()},
            min_weight=1.5,
        )
    assert exc.value.code == ErrorCode.USAGE_ERROR
    assert "min_weight" in exc.value.message


def test_load_feedback_counts_counts_only_verdict_sources(
    tmp_path: Path,
) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    editor = _agent(db, workspace_id, AgentRole.EDITOR)
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    for _ in range(2):
        record_behavior_entry(
            db,
            workspace_id,
            agent_id=writer.id,
            kind="relationship",
            target="作者",
            summary="稿子被退回",
            source="decision:reject",
        )
    record_behavior_entry(
        db,
        workspace_id,
        agent_id=writer.id,
        kind="relationship",
        target="作者",
        summary="稿子被认可",
        source="decision:accept",
    )
    record_behavior_entry(
        db,
        workspace_id,
        agent_id=editor.id,
        kind="relationship",
        target="写手",
        summary="委托被拒绝",
        source="delegation:refused",
    )
    record_behavior_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="relationship",
        target="写手",
        summary="被退过稿",
        source="review:add",
    )
    record_behavior_entry(
        db,
        workspace_id,
        agent_id=reviewer.id,
        kind="viewpoint",
        target="rule:x",
        summary="拒绝了违背立场的指令",
        source="refusal:rule:x",
    )

    counts = load_feedback_counts(db, workspace_id)

    assert counts[writer.id] == FeedbackCounts(rejected=2, accepted=1)
    assert counts[editor.id] == FeedbackCounts(rejected=1, accepted=0)
    assert reviewer.id not in counts


def test_load_feedback_counts_is_read_only(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    record_behavior_entry(
        db,
        workspace_id,
        agent_id=writer.id,
        kind="relationship",
        target="作者",
        summary="稿子被退回",
        source="decision:reject",
    )
    with db.workspace_session(workspace_id) as session:
        before = session.query(func.count()).select_from(BehaviorTimeline).scalar()

    load_feedback_counts(db, workspace_id)

    with db.workspace_session(workspace_id) as session:
        after = session.query(func.count()).select_from(BehaviorTimeline).scalar()
    assert after == before


def test_load_feedback_counts_empty_timeline(tmp_path: Path) -> None:
    db, workspace_id = _make_db(tmp_path)

    assert load_feedback_counts(db, workspace_id) == {}


@pytest.mark.smoke
def test_smoke_selector_pipeline_reproducible_and_evolving(
    tmp_path: Path,
) -> None:
    db, workspace_id = _make_db(tmp_path)
    writer = _agent(db, workspace_id, AgentRole.WRITER)
    reviewer = _agent(db, workspace_id, AgentRole.REVIEWER)
    editor = _agent(db, workspace_id, AgentRole.EDITOR)
    candidates = [
        ChoiceCandidate(agent=writer.id, kind="proactive_report", content="交稿候选"),
        ChoiceCandidate(agent=reviewer.id, kind="proactive_consistency", content="审稿候选"),
        ChoiceCandidate(agent=editor.id, kind="proactive_direction", content="方向候选"),
    ]
    agents = {agent.id: agent.role for agent in (writer, reviewer, editor)}
    params = {agent.id: _params() for agent in (writer, reviewer, editor)}
    goal = _motive(writer.id, MotiveKind.GOAL.value, "新章已交")

    first = evaluate_choice(
        "draft_generated",
        candidates,
        agents,
        [goal],
        params,
        dial=0.5,
        seed=42,
    )
    second = evaluate_choice(
        "draft_generated",
        candidates,
        agents,
        [goal],
        params,
        dial=0.5,
        seed=42,
    )
    assert first == second
    assert len(first) == 1

    variants = {
        evaluate_choice(
            "draft_generated",
            candidates,
            agents,
            [goal],
            params,
            dial=0.5,
            seed=seed,
        )[0].agent
        for seed in range(80)
    }
    assert len(variants) >= 2

    feedback = {writer.id: FeedbackCounts(rejected=0)}
    no_history = compute_weights(
        candidates,
        [goal],
        params,
        feedback,
        agents=agents,
        trigger="draft_generated",
    )
    feedback = {writer.id: FeedbackCounts(rejected=4)}
    rejected_four = compute_weights(
        candidates,
        [goal],
        params,
        feedback,
        agents=agents,
        trigger="draft_generated",
    )
    assert rejected_four[0] < no_history[0]

    summary = (
        "seed=42 pick: "
        f"{first[0].agent} ({first[0].kind}); "
        "variants across 80 seeds: "
        f"{len(variants)} distinct agents; "
        "writer tendency after 4 refusals: "
        f"{rejected_four[0]:.3f} (was {no_history[0]:.3f})"
    )
    print(summary)
